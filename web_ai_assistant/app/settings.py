"""Server-only configuration. Browser requests cannot choose providers or secrets."""

from typing import Literal
from urllib.parse import urlsplit
import ipaddress

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SYSTEM_PROMPT = "你是網站的友善助手。請使用繁體中文，清楚、誠實地回答。遇到不確定的資訊，請說明限制。"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True,
    )

    llm_mode: Literal["mock", "openai"] = "mock"
    llm_base_url: str = "http://localhost:4000/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    public_base_url: str | None = None
    system_prompt: str = Field(
        default=DEFAULT_SYSTEM_PROMPT,
        min_length=1, max_length=8000,
    )
    allowed_frame_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8080", "http://127.0.0.1:8080"]
    )
    trusted_proxy_ips: list[str] = Field(default_factory=list)
    max_concurrent_requests: int = Field(default=4, ge=1, le=100)
    requests_per_minute: int = Field(default=20, ge=1, le=10000)
    request_timeout_seconds: float = Field(default=90, gt=0, le=600)
    max_body_bytes: int = Field(default=65536, ge=256, le=1048576)
    max_messages: int = Field(default=20, ge=1, le=200)
    max_message_chars: int = Field(default=4000, ge=1, le=100000)
    max_total_chars: int = Field(default=24000, ge=1, le=200000)

    @field_validator("system_prompt", mode="before")
    @classmethod
    def default_blank_prompt(cls, value):
        return DEFAULT_SYSTEM_PROMPT if value is None or value == "" else value

    @field_validator("allowed_frame_origins")
    @classmethod
    def validate_frame_origins(cls, origins: list[str]) -> list[str]:
        normalized = []
        for origin in origins:
            parts = urlsplit(origin)
            if (parts.scheme not in {"http", "https"} or not parts.hostname
                    or parts.username is not None or parts.password is not None
                    or parts.path not in {"", "/"} or parts.query or parts.fragment
                    or any(c.isspace() for c in origin) or "*" in origin):
                raise ValueError("ALLOWED_FRAME_ORIGINS must contain exact HTTP(S) origins")
            # Accessing port also rejects malformed port values.
            parts.port
            normalized.append(f"{parts.scheme.lower()}://{parts.netloc.lower()}")
        return list(dict.fromkeys(normalized))

    @field_validator("trusted_proxy_ips")
    @classmethod
    def validate_proxy_ips(cls, values: list[str]) -> list[str]:
        return [str(ipaddress.ip_address(value)) for value in values]

    @field_validator("public_base_url", mode="before")
    @classmethod
    def validate_public_url(cls, value):
        if value is None or value == "":
            return None
        return cls.validate_frame_origins([value])[0]

    @field_validator("llm_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or any(c.isspace() for c in value)):
            raise ValueError("LLM_BASE_URL must be an HTTP(S) base URL without credentials")
        parts.port
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_provider(self):
        if self.llm_mode == "openai" and (
            not self.llm_api_key.get_secret_value().strip() or not self.llm_model.strip()
        ):
            raise ValueError("OpenAI mode requires LLM_API_KEY and LLM_MODEL")
        return self

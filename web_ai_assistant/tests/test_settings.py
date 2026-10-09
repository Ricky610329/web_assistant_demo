from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.settings import Settings


def test_openai_mode_requires_model_and_api_key(settings_factory):
    with pytest.raises(ValidationError):
        settings_factory(llm_mode="openai", llm_model="", llm_api_key=None)

    with pytest.raises(ValidationError):
        settings_factory(llm_mode="openai", llm_model="model", llm_api_key="")


def test_mock_mode_does_not_require_secret(settings_factory):
    settings = settings_factory(llm_mode="mock", llm_api_key="")
    assert settings.llm_mode == "mock"
    assert settings.llm_api_key.get_secret_value() == ""


def test_example_env_bootstraps_demo_without_editing():
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / ".env.example"
    settings = Settings(_env_file=example)
    assert settings.llm_mode == "mock"
    assert settings.system_prompt.strip()


def test_invalid_configuration_never_prints_api_key(settings_factory):
    with pytest.raises(ValidationError) as caught:
        settings_factory(llm_mode="openai", llm_model="", llm_api_key="DO-NOT-PRINT-THIS")
    assert "DO-NOT-PRINT-THIS" not in str(caught.value)


def test_environment_names_are_supported(monkeypatch):
    monkeypatch.setenv("LLM_MODE", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_MODEL", "school-model")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv(
        "ALLOWED_FRAME_ORIGINS",
        '["https://school.example","https://portal.example"]',
    )

    settings = Settings(_env_file=None)

    assert settings.llm_mode == "openai"
    assert settings.llm_base_url == "https://gateway.example/v1"
    assert settings.llm_model == "school-model"
    assert settings.llm_api_key.get_secret_value() == "secret"
    assert settings.allowed_frame_origins == [
        "https://school.example",
        "https://portal.example",
    ]

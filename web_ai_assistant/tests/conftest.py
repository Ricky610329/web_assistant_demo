from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.main import create_app
from app.settings import Settings


@dataclass
class FakeClock:
    now: float = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class RecordingProvider:
    chunks: tuple[str, ...] = ("Hello", " world")
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    closed: int = 0

    async def stream(
        self, messages: list[dict[str, str]]
    ) -> AsyncIterator[str]:
        self.calls.append(messages)
        try:
            for chunk in self.chunks:
                await asyncio.sleep(0)
                yield chunk
        finally:
            self.closed += 1


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    def build(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "llm_mode": "mock",
            "llm_base_url": "http://localhost:4000/v1",
            "llm_model": "test-model",
            "system_prompt": "SYSTEM INSTRUCTIONS",
            "allowed_frame_origins": [
                "http://localhost:8080",
                "http://127.0.0.1:8080",
            ],
            "max_concurrent_requests": 4,
            "requests_per_minute": 20,
            "request_timeout_seconds": 1.0,
            "max_body_bytes": 65_536,
            "max_messages": 20,
            "max_message_chars": 4_000,
            "max_total_chars": 24_000,
            "trusted_proxy_ips": [],
        }
        values.update(overrides)
        return Settings(**values)

    return build


@pytest.fixture
def app_factory(settings_factory, clock):
    def build(*, provider=None, **setting_overrides):
        settings = settings_factory(**setting_overrides)
        return create_app(settings=settings, provider=provider, clock=clock)

    return build


def as_dict(message: Any) -> dict[str, str]:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump()
    return {"role": message.role, "content": message.content}


def parse_sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    assert response.headers["content-type"].startswith("text/event-stream")
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    data_lines: list[str] = []

    for line in response.text.splitlines() + [""]:
        if not line:
            if event_name is not None:
                events.append((event_name, json.loads("\n".join(data_lines))))
            event_name = None
            data_lines = []
        elif line.startswith("event:"):
            event_name = line.partition(":")[2].strip()
        elif line.startswith("data:"):
            data_lines.append(line.partition(":")[2].lstrip())

    return events


def assert_error_response(response: httpx.Response, status: int, code: str) -> str:
    assert response.status_code == status
    payload = response.json()
    assert set(payload) == {"error", "request_id"}
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]
    assert isinstance(payload["request_id"], str)
    assert payload["request_id"]
    return payload["request_id"]


def transport_for(app, ip: str = "127.0.0.1") -> httpx.ASGITransport:
    return httpx.ASGITransport(app=app, client=(ip, 40_000))

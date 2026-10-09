from __future__ import annotations

import asyncio
import json
import time

import pytest

import app.main as main_module
from app.limiter import RequestGuard
from app.main import LeasedStreamingResponse, RequestBoundary
from app.provider import bounded_close


def http_scope(*, method: str = "GET", path: str = "/") -> dict:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 40_000),
        "server": ("testserver", 80),
        "state": {},
    }


@pytest.mark.asyncio
async def test_asgi_24_disconnect_cancels_stalled_stream_and_releases_lease():
    guard = RequestGuard(concurrency=1, per_minute=20)
    lease = guard.acquire("127.0.0.1")
    started = asyncio.Event()
    closed = asyncio.Event()
    never = asyncio.Event()
    sent = []

    async def stalled_body():
        try:
            started.set()
            await never.wait()
            yield b"unreachable"
        finally:
            closed.set()

    async def receive():
        await started.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    response = LeasedStreamingResponse(
        stalled_body(), lease, time_budget=10, media_type="text/event-stream"
    )
    began = time.monotonic()
    await asyncio.wait_for(
        response(http_scope(), receive, send),
        timeout=0.5,
    )

    assert time.monotonic() - began < 0.5
    assert sent[0]["type"] == "http.response.start"
    assert closed.is_set()
    assert guard.active == 0


@pytest.mark.asyncio
async def test_slow_chat_body_returns_408_without_calling_downstream(settings_factory):
    downstream_called = False
    sent = []
    never = asyncio.Event()

    async def downstream(scope, receive, send):
        nonlocal downstream_called
        downstream_called = True

    async def stalled_receive():
        await never.wait()
        raise AssertionError("unreachable")

    async def protected_send(message):
        sent.append(message)

    boundary = RequestBoundary(
        downstream,
        settings_factory(body_read_timeout_seconds=0.02),
    )
    scope = http_scope(method="POST", path="/api/chat")
    scope["headers"] = [(b"content-type", b"application/json")]

    await asyncio.wait_for(
        boundary(scope, stalled_receive, protected_send),
        timeout=0.5,
    )

    assert downstream_called is False
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    assert start["status"] == 408
    assert json.loads(body)["error"]["code"] == "request_timeout"


@pytest.mark.asyncio
async def test_hanging_send_is_capped_by_budget_plus_final_send_grace():
    guard = RequestGuard(concurrency=1, per_minute=20)
    lease = guard.acquire("127.0.0.1")
    closed = asyncio.Event()
    never = asyncio.Event()
    response_started = asyncio.Event()

    async def body():
        try:
            yield b"first"
        finally:
            closed.set()

    async def receive():
        await never.wait()
        raise AssertionError("unreachable")

    async def hanging_send(message):
        if message["type"] == "http.response.start":
            response_started.set()
            return
        await never.wait()

    response = LeasedStreamingResponse(
        body(), lease, time_budget=0.01, media_type="text/event-stream"
    )
    began = time.monotonic()
    await asyncio.wait_for(
        response(http_scope(), receive, hanging_send),
        timeout=1.8,
    )
    elapsed = time.monotonic() - began

    assert response_started.is_set()
    assert 0.85 <= elapsed < 1.6
    assert closed.is_set()
    assert guard.active == 0


class HangingCloseIterator:
    def __init__(self):
        self.close_started = asyncio.Event()
        self.close_cancelled = asyncio.Event()
        self.never = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def aclose(self):
        self.close_started.set()
        try:
            await self.never.wait()
        finally:
            self.close_cancelled.set()


@pytest.mark.asyncio
async def test_hanging_iterator_close_does_not_hold_released_lease(monkeypatch):
    async def fast_bounded_close(close):
        await bounded_close(close, grace=0.02)

    monkeypatch.setattr(main_module, "bounded_close", fast_bounded_close)
    guard = RequestGuard(concurrency=1, per_minute=20)
    lease = guard.acquire("127.0.0.1")
    iterator = HangingCloseIterator()
    never = asyncio.Event()

    async def receive():
        await never.wait()
        raise AssertionError("unreachable")

    async def send(message):
        return None

    response = LeasedStreamingResponse(iterator, lease, time_budget=1)
    task = asyncio.create_task(response(http_scope(), receive, send))
    await asyncio.wait_for(iterator.close_started.wait(), timeout=0.3)

    # Release precedes best-effort provider cleanup, so another request can be admitted.
    assert guard.active == 0
    await asyncio.wait_for(task, timeout=0.3)
    assert iterator.close_cancelled.is_set()


@pytest.mark.asyncio
async def test_cleanup_exception_logs_only_type_and_never_secret(caplog):
    secret = "provider-key-MUST-NOT-APPEAR"

    async def failing_close():
        raise RuntimeError(f"failed to close Authorization: Bearer {secret}")

    with caplog.at_level("WARNING", logger="assistant"):
        await bounded_close(failing_close, grace=0.02)

    output = caplog.text
    assert "stream_cleanup error_type=RuntimeError" in output
    assert secret not in output
    assert "Authorization" not in output

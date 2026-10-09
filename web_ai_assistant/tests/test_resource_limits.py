from __future__ import annotations

import asyncio
from contextlib import suppress

import httpx
import pytest

from conftest import RecordingProvider, assert_error_response, parse_sse, transport_for


class GateProvider:
    def __init__(self, expected_starts: int = 1):
        self.expected_starts = expected_starts
        self.started_count = 0
        self.all_started = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = 0

    async def stream(self, messages):
        self.started_count += 1
        if self.started_count >= self.expected_starts:
            self.all_started.set()
        try:
            await self.release.wait()
            yield "released"
        finally:
            self.closed += 1


@pytest.mark.asyncio
async def test_concurrency_saturation_does_not_queue_and_slots_are_reusable(
    app_factory,
):
    provider = GateProvider(expected_starts=2)
    app = app_factory(
        provider=provider,
        max_concurrent_requests=2,
        requests_per_minute=20,
    )
    payload = {"messages": [{"role": "user", "content": "hold"}]}

    async with httpx.AsyncClient(
        transport=transport_for(app), base_url="http://testserver"
    ) as client:
        first = asyncio.create_task(client.post("/api/chat", json=payload))
        second = asyncio.create_task(client.post("/api/chat", json=payload))
        await asyncio.wait_for(provider.all_started.wait(), timeout=1)
        assert app.state.guard.active == 2

        rejected = await asyncio.wait_for(
            client.post("/api/chat", json=payload), timeout=0.5
        )
        assert_error_response(rejected, 503, "busy")

        provider.release.set()
        first_response, second_response = await asyncio.gather(first, second)
        assert first_response.status_code == second_response.status_code == 200
        assert app.state.guard.active == 0

        reused = await client.post("/api/chat", json=payload)

    assert reused.status_code == 200
    assert provider.closed == 3
    assert app.state.guard.active == 0


@pytest.mark.asyncio
async def test_rate_limit_uses_rolling_clock_and_sets_retry_after(app_factory, clock):
    provider = RecordingProvider(chunks=("ok",))
    app = app_factory(
        provider=provider,
        requests_per_minute=2,
        max_concurrent_requests=4,
    )
    payload = {"messages": [{"role": "user", "content": "hi"}]}

    async with httpx.AsyncClient(
        transport=transport_for(app, "198.51.100.8"),
        base_url="http://testserver",
    ) as client:
        assert (await client.post("/api/chat", json=payload)).status_code == 200
        assert (await client.post("/api/chat", json=payload)).status_code == 200
        limited = await client.post("/api/chat", json=payload)
        assert_error_response(limited, 429, "rate_limited")
        assert int(limited.headers["Retry-After"]) > 0

        clock.advance(59.9)
        still_limited = await client.post("/api/chat", json=payload)
        assert_error_response(still_limited, 429, "rate_limited")

        clock.advance(0.2)
        allowed = await client.post("/api/chat", json=payload)

    assert allowed.status_code == 200
    assert len(provider.calls) == 3
    assert app.state.guard.active == 0


@pytest.mark.asyncio
async def test_untrusted_forwarded_for_cannot_evade_rate_limit(app_factory):
    app = app_factory(
        provider=RecordingProvider(chunks=("ok",)),
        requests_per_minute=1,
        trusted_proxy_ips=[],
    )
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    async with httpx.AsyncClient(
        transport=transport_for(app, "198.51.100.20"),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/api/chat", headers={"X-Forwarded-For": "203.0.113.1"}, json=payload
        )
        second = await client.post(
            "/api/chat", headers={"X-Forwarded-For": "203.0.113.2"}, json=payload
        )

    assert first.status_code == 200
    assert_error_response(second, 429, "rate_limited")


@pytest.mark.asyncio
async def test_trusted_proxy_uses_valid_forwarded_client_addresses(app_factory):
    app = app_factory(
        provider=RecordingProvider(chunks=("ok",)),
        requests_per_minute=1,
        trusted_proxy_ips=["192.0.2.10"],
    )
    payload = {"messages": [{"role": "user", "content": "hi"}]}
    async with httpx.AsyncClient(
        transport=transport_for(app, "192.0.2.10"), base_url="http://testserver"
    ) as client:
        first = await client.post(
            "/api/chat", headers={"X-Forwarded-For": "203.0.113.1"}, json=payload
        )
        second = await client.post(
            "/api/chat", headers={"X-Forwarded-For": "203.0.113.2"}, json=payload
        )

    assert first.status_code == second.status_code == 200


class TimeoutThenSuccessProvider:
    def __init__(self):
        self.calls = 0
        self.closed = 0
        self.started = asyncio.Event()

    async def stream(self, messages):
        self.calls += 1
        try:
            if self.calls == 1:
                self.started.set()
                await asyncio.Event().wait()
            yield "ok"
        finally:
            self.closed += 1


@pytest.mark.asyncio
async def test_timeout_closes_stream_and_releases_slot(app_factory):
    provider = TimeoutThenSuccessProvider()
    app = app_factory(
        provider=provider,
        request_timeout_seconds=0.05,
        max_concurrent_requests=1,
    )
    payload = {"messages": [{"role": "user", "content": "hi"}]}

    async with httpx.AsyncClient(
        transport=transport_for(app), base_url="http://testserver"
    ) as client:
        timed_out = await client.post("/api/chat", json=payload)
        timeout_events = parse_sse(timed_out)
        assert timeout_events[0][0] == "error"
        assert timeout_events[0][1]["code"] == "timeout"
        assert provider.closed == 1
        assert app.state.guard.active == 0

        next_response = await client.post("/api/chat", json=payload)

    assert parse_sse(next_response) == [("delta", {"text": "ok"}), ("done", {})]
    assert provider.closed == 2
    assert app.state.guard.active == 0


@pytest.mark.asyncio
async def test_cancelled_client_closes_provider_and_releases_slot(app_factory):
    provider = GateProvider()
    app = app_factory(
        provider=provider,
        max_concurrent_requests=1,
        request_timeout_seconds=10,
    )
    payload = {"messages": [{"role": "user", "content": "hold"}]}

    async with httpx.AsyncClient(
        transport=transport_for(app), base_url="http://testserver"
    ) as client:
        request_task = asyncio.create_task(client.post("/api/chat", json=payload))
        await asyncio.wait_for(provider.all_started.wait(), timeout=1)
        assert app.state.guard.active == 1

        request_task.cancel()
        with suppress(asyncio.CancelledError):
            await request_task

        for _ in range(20):
            if provider.closed == 1 and app.state.guard.active == 0:
                break
            await asyncio.sleep(0)

    assert provider.closed == 1
    assert app.state.guard.active == 0

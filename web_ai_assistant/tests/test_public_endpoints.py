from __future__ import annotations

import httpx
import pytest

from conftest import transport_for


class MustNotRunProvider:
    async def stream(self, messages):
        raise AssertionError("health/config/widget must not call the provider")
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_health_is_exact_and_independent_of_provider(app_factory):
    app = app_factory(provider=MustNotRunProvider())
    async with httpx.AsyncClient(
        transport=transport_for(app), base_url="http://testserver"
    ) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_public_config_reveals_mode_but_no_provider_secrets(app_factory):
    secret = "NOT-FOR-THE-BROWSER"
    app = app_factory(provider=MustNotRunProvider(), llm_api_key=secret)
    async with httpx.AsyncClient(
        transport=transport_for(app), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/config")

    assert response.status_code == 200
    assert response.json() == {"demo_mode": True}
    assert secret not in response.text
    assert "llm_api_key" not in response.text
    assert "llm_base_url" not in response.text


@pytest.mark.asyncio
async def test_widget_allows_configured_embedding_origins(app_factory):
    origins = ["https://school.example", "https://portal.example:8443"]
    app = app_factory(provider=MustNotRunProvider(), allowed_frame_origins=origins)
    async with httpx.AsyncClient(
        transport=transport_for(app), base_url="http://testserver"
    ) as client:
        response = await client.get("/widget/")

    assert response.status_code == 200
    policy = response.headers["content-security-policy"]
    assert "frame-ancestors" in policy
    for origin in origins:
        assert origin in policy


@pytest.mark.asyncio
async def test_public_base_url_allows_external_https_origin_behind_http_proxy(
    app_factory,
):
    app = app_factory(
        provider=MustNotRunProvider(),
        public_base_url="https://assistant.school.example",
    )
    payload = {"messages": [{"role": "user", "content": "hello"}]}
    async with httpx.AsyncClient(
        transport=transport_for(app, "192.0.2.30"),
        base_url="http://internal-service:8000",
    ) as client:
        accepted = await client.post(
            "/api/chat",
            headers={
                "Origin": "https://assistant.school.example",
                "X-Forwarded-Proto": "https",
            },
            json=payload,
        )
        rejected = await client.post(
            "/api/chat",
            headers={
                "Origin": "https://attacker.example",
                "X-Forwarded-Proto": "https",
            },
            json=payload,
        )

    # The configured canonical URL, rather than an untrusted forwarded header,
    # defines the accepted browser origin.
    assert accepted.status_code == 200
    assert rejected.status_code == 403

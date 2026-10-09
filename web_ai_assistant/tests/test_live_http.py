"""Actual HTTP/SDK checks against a local compatible gateway, never a paid API."""

from contextlib import contextmanager
import json
import socket
import threading
import time
import asyncio

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from app.main import create_app
from app.settings import Settings


@contextmanager
def serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical",
                            proxy_headers=False, timeout_graceful_shutdown=2)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "local test server did not start"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive(), "local test server did not stop"


@pytest.fixture
def live_assistant():
    gateway = FastAPI()
    record = {"calls": [], "closed": 0}

    @gateway.post("/v1/chat/completions")
    async def completions(request: Request):
        payload = await request.json()
        record["calls"].append(payload)
        record["auth"] = request.headers.get("authorization")
        question = payload["messages"][-1]["content"]

        async def generate():
            try:
                texts = ["你好，", "這是實際 HTTP 測試。"]
                for index, text in enumerate(texts):
                    chunk = {
                        "id": "local-test", "object": "chat.completion.chunk", "created": 0,
                        "model": "local-model",
                        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                    }
                    frame = ("data: " + json.dumps(chunk, ensure_ascii=False) + "\r\n\r\n").encode()
                    # Split inside UTF-8 and across frames: SDK must buffer correctly.
                    for offset in range(0, len(frame), 7):
                        yield frame[offset:offset + 7]
                    if question == "hold" and index == 0:
                        await asyncio.sleep(30)
                if question != "truncated":
                    chunk["choices"][0] = {"index": 0, "delta": {}, "finish_reason": "stop"}
                    yield ("data: " + json.dumps(chunk) + "\n\n").encode()
                    yield b"data: [DONE]\n\n"
            finally:
                record["closed"] += 1

        return StreamingResponse(generate(), media_type="text/event-stream")

    with serve(gateway) as gateway_url:
        settings = Settings(
            _env_file=None, llm_mode="openai", llm_base_url=gateway_url + "/v1",
            llm_api_key="local-test-key", llm_model="local-model",
            max_concurrent_requests=1, request_timeout_seconds=2,
        )
        assistant = create_app(settings)
        with serve(assistant) as assistant_url:
            yield assistant_url, assistant, record


def test_actual_sdk_http_stream_has_correct_dialogue_and_safe_finish(live_assistant):
    url, app, record = live_assistant
    response = httpx.post(url + "/api/chat", json={
        "messages": [{"role": "user", "content": "hello"}]
    })
    assert response.status_code == 200
    assert "你好，" in response.text
    assert "這是實際 HTTP 測試。" in response.text
    assert "event: done" in response.text
    assert "event: error" not in response.text
    assert record["auth"] == "Bearer local-test-key"
    assert record["calls"][0]["messages"][0]["role"] == "system"
    assert record["calls"][0]["model"] == "local-model"
    assert app.state.guard.active == 0


def test_actual_sdk_rejects_truncated_stream(live_assistant):
    url, app, record = live_assistant
    response = httpx.post(url + "/api/chat", json={
        "messages": [{"role": "user", "content": "truncated"}]
    })
    assert "event: error" in response.text
    assert "incomplete_stream" in response.text
    assert "event: done" not in response.text
    assert app.state.guard.active == 0


def test_socket_disconnect_cancels_stalled_upstream_without_waiting_for_timeout(live_assistant):
    url, app, record = live_assistant
    with httpx.stream("POST", url + "/api/chat", json={
        "messages": [{"role": "user", "content": "hold"}]
    }) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data:"):
                break
        assert app.state.guard.active == 1
    deadline = time.monotonic() + 0.8
    while app.state.guard.active and time.monotonic() < deadline:
        time.sleep(0.01)
    assert app.state.guard.active == 0, "disconnected client retained the inference slot"
    assert record["closed"] >= 1

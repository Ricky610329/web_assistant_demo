from __future__ import annotations

import asyncio
from contextlib import suppress
from types import SimpleNamespace

import pytest

from app.provider import IncompleteStreamError, OpenAIProvider


def chunk(
    content: str | None = None,
    *,
    finish_reason: str | None = None,
    index: int = 0,
):
    choice = SimpleNamespace(
        index=index,
        delta=SimpleNamespace(content=content),
        finish_reason=finish_reason,
    )
    return SimpleNamespace(choices=[choice])


class FakeSDKStream:
    def __init__(self, chunks):
        self._chunks = iter(chunks)
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration

    async def close(self):
        self.closed = True


class FakeCompletions:
    def __init__(self, stream):
        self.stream = stream
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.stream


class FakeClient:
    def __init__(self, stream):
        self.chat = SimpleNamespace(completions=FakeCompletions(stream))
        self.closed = False

    async def close(self):
        self.closed = True


def provider_with_stream(settings_factory, stream):
    provider = OpenAIProvider(
        settings_factory(
            llm_mode="openai",
            llm_model="approved-model",
            llm_api_key="test-key",
        )
    )
    provider.client = FakeClient(stream)
    return provider


@pytest.mark.asyncio
async def test_openai_adapter_yields_primary_text_and_closes_sdk_stream(
    settings_factory,
):
    stream = FakeSDKStream(
        [
            chunk("first"),
            SimpleNamespace(choices=[]),  # usage-only chunks are valid
            chunk(" second"),
            chunk(finish_reason="stop"),
        ]
    )
    provider = provider_with_stream(settings_factory, stream)
    messages = [{"role": "user", "content": "hello"}]

    output = [text async for text in provider.stream(messages)]

    assert output == ["first", " second"]
    assert stream.closed is True
    assert provider.client.chat.completions.calls == [
        {"model": "approved-model", "messages": messages, "stream": True}
    ]

    await provider.close()
    assert provider.client.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks",
    [
        [chunk("partial"), chunk(finish_reason="length")],
        [chunk("partial")],
        [chunk("ignored", index=1), chunk(finish_reason="stop", index=1)],
    ],
)
async def test_openai_adapter_rejects_cutoff_or_missing_primary_stop(
    settings_factory, chunks
):
    stream = FakeSDKStream(chunks)
    provider = provider_with_stream(settings_factory, stream)

    with pytest.raises(IncompleteStreamError):
        _ = [text async for text in provider.stream([])]

    assert stream.closed is True


class BlockingSDKStream:
    def __init__(self):
        self.started = asyncio.Event()
        self.never = asyncio.Event()
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.started.set()
        await self.never.wait()
        raise StopAsyncIteration

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_openai_adapter_closes_sdk_stream_when_cancelled(settings_factory):
    stream = BlockingSDKStream()
    provider = provider_with_stream(settings_factory, stream)

    async def consume():
        async for _ in provider.stream([]):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(stream.started.wait(), timeout=1)
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    assert stream.closed is True

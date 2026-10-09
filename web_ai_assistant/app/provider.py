"""Translate provider streams into text, leaving browser events provider-neutral."""

from collections.abc import AsyncIterator
from typing import Protocol
import asyncio

from openai import AsyncOpenAI
from .settings import Settings


class Provider(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


class IncompleteStreamError(Exception):
    pass


class OpenAIProvider:
    def __init__(self, settings: Settings):
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            timeout=settings.request_timeout_seconds,
            max_retries=0,
        )
        self.model = settings.llm_model

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        stream = await self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True,
        )
        finished = False
        try:
            async for chunk in stream:
                # Usage-only chunks may have no choices.
                for choice in chunk.choices:
                    if choice.index != 0:
                        continue
                    if choice.delta.content:
                        yield choice.delta.content
                    if choice.finish_reason is not None:
                        # A cutoff is an incomplete answer, not successful completion.
                        if choice.finish_reason != "stop":
                            raise IncompleteStreamError()
                        finished = True
            if not finished:
                raise IncompleteStreamError()
        finally:
            await stream.close()

    async def close(self) -> None:
        await self.client.close()


class DemoProvider:
    """Clearly labeled offline demo; never pretends to make a model request."""

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        answer = (
            "這是**離線示範回覆**，尚未連接語言模型。\n\n"
            "嵌入、串流與對話操作已啟用。請由管理者在後端設定 "
            "`LLM_MODE=openai`、服務網址、模型名稱及金鑰，以使用真正的模型。\n\n"
            "你的訊息：\n\n" + messages[-1]["content"]
        )
        for offset in range(0, len(answer), 6):
            await asyncio.sleep(0.015)
            yield answer[offset:offset + 6]

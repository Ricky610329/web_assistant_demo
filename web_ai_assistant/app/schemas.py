"""The public chat contract intentionally has no model, URL, or system fields."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictStr


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: StrictStr = Field(min_length=1)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[Message] = Field(min_length=1)

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, NonNegativeInt

ModelFinishReason = Literal[
    "stop",
    "tool_calls",
    "length",
    "content_filter",
    "unknown",
]


class ModelToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, JsonValue]


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_calls: list[ModelToolCall] = Field(default_factory=list, alias="toolCalls")


class ModelTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, JsonValue]


class ModelTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ModelMessage]
    tools: list[ModelTool]
    maxOutputTokens: int = Field(gt=0)


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promptTokens: NonNegativeInt
    cachedTokens: NonNegativeInt = 0
    completionTokens: NonNegativeInt
    totalTokens: NonNegativeInt


class ModelTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    toolCalls: list[ModelToolCall]
    usage: ModelUsage
    finishReason: ModelFinishReason
    rawFinishReason: str | None = None


class ModelProvider(Protocol):
    billable: bool
    provider_name: str
    model_name: str

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult: ...

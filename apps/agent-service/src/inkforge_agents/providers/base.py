from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, NonNegativeInt


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")


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


class ModelToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    name: str
    arguments: dict[str, JsonValue]


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


class ModelProvider(Protocol):
    billable: bool

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult: ...

from __future__ import annotations

from typing import Literal, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    NonNegativeInt,
    model_validator,
)

ModelFinishReason = Literal[
    "stop",
    "tool_calls",
    "length",
    "content_filter",
    "insufficient_system_resource",
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
    reasoningContent: str | None = Field(default=None, alias="reasoning_content")
    name: str | None = None
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    tool_calls: list[ModelToolCall] = Field(default_factory=list, alias="toolCalls")


class ModelTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters: dict[str, JsonValue]


class ModelExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policyId: str = Field(min_length=1)
    thinkingMode: Literal["provider_default", "enabled", "disabled"]
    reasoningEffort: Literal["high", "max"] | None = None
    requiredToolName: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_thinking(self) -> Self:
        if self.thinkingMode == "disabled" and self.reasoningEffort is not None:
            raise ValueError("关闭思考时不能设置推理强度")
        if self.thinkingMode == "enabled" and self.reasoningEffort is None:
            raise ValueError("启用思考时必须设置推理强度")
        return self


class ModelTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ModelMessage]
    tools: list[ModelTool]
    maxOutputTokens: int = Field(gt=0)
    policy: ModelExecutionPolicy


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    promptTokens: NonNegativeInt
    cachedTokens: NonNegativeInt = 0
    completionTokens: NonNegativeInt
    totalTokens: NonNegativeInt


class ModelUsageDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    promptCacheMissTokens: int | None = Field(default=None, ge=0)
    reasoningTokens: int | None = Field(default=None, ge=0)
    providerUsageKeys: list[str] = Field(default_factory=list)


class ModelTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    toolCalls: list[ModelToolCall]
    usage: ModelUsage
    finishReason: ModelFinishReason
    rawFinishReason: str | None = None
    reasoningContent: str | None = None
    providerResponseId: str | None = None
    diagnostics: ModelUsageDiagnostics = Field(default_factory=ModelUsageDiagnostics)


class ModelProvider(Protocol):
    billable: bool
    provider_name: str
    model_name: str

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult: ...

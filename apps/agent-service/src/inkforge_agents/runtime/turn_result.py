from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ..providers.base import ModelUsage


class RuntimeToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    toolKind: str
    arguments: dict[str, Any]


class RuntimeToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    result: dict[str, Any]


class AgentTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visibleContent: str
    controlEvents: list[dict[str, Any]]
    toolCalls: list[RuntimeToolCall]
    toolResults: list[RuntimeToolResult]
    usage: ModelUsage
    finishReason: str


def aggregate_visible_content(parts: list[str]) -> str:
    return "\n\n".join(part for part in parts if part)


def empty_usage() -> ModelUsage:
    return ModelUsage(
        promptTokens=0,
        cachedTokens=0,
        completionTokens=0,
        totalTokens=0,
    )


def add_usage(total: ModelUsage, current: ModelUsage) -> ModelUsage:
    return ModelUsage(
        promptTokens=total.promptTokens + current.promptTokens,
        cachedTokens=total.cachedTokens + current.cachedTokens,
        completionTokens=total.completionTokens + current.completionTokens,
        totalTokens=total.totalTokens + current.totalTokens,
    )

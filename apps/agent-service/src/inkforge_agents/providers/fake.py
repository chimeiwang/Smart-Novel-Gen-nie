from __future__ import annotations

from .base import (
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)


class FakeModelProvider:
    billable = False
    provider_name = "fake"
    model_name = "fake"

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        content = "模拟模型已完成本轮处理。"
        prompt_tokens = sum(len(message.content) for message in request.messages)
        completion_tokens = len(content)
        tool_calls = []
        if request.tools:
            tool_calls.append(
                ModelToolCall(
                    id="fake-tool-call-1",
                    name=request.tools[0].name,
                    arguments={},
                )
            )
        return ModelTurnResult(
            content=content,
            toolCalls=tool_calls,
            usage=ModelUsage(
                promptTokens=prompt_tokens,
                cachedTokens=0,
                completionTokens=completion_tokens,
                totalTokens=prompt_tokens + completion_tokens,
            ),
        )

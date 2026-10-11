"""V1 真实工具网关读取和完整候选回传的受控供应商夹具。"""

from __future__ import annotations

import json

from inkforge_agents.providers.base import (
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
    ModelUsageDiagnostics,
)
from inkforge_agents.providers.fake import FakeModelProvider


class ToolReadingProvider(FakeModelProvider):
    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        names = {tool.name for tool in request.tools}
        if "begin_artifact_output" in names:
            if any(message.role == "tool" for message in request.messages):
                return _legacy_artifact_turn(request)
            return _legacy_outline_read_turn(request)
        return await super().complete_turn(request)


def _legacy_outline_read_turn(request: ModelTurnRequest) -> ModelTurnResult:
    prompt_tokens = sum(len(message.content) for message in request.messages)
    return ModelTurnResult(
        content="",
        toolCalls=[
            ModelToolCall(
                id="legacy-fake-outline-read",
                name="list_outline_summary",
                arguments={},
            )
        ],
        finishReason="tool_calls",
        rawFinishReason="tool_calls",
        usage=ModelUsage(
            promptTokens=prompt_tokens,
            cachedTokens=0,
            completionTokens=0,
            totalTokens=prompt_tokens,
        ),
        diagnostics=ModelUsageDiagnostics(),
        effectiveMaxOutputTokens=request.maxOutputTokens,
    )


def _legacy_artifact_turn(request: ModelTurnRequest) -> ModelTurnResult:
    prompt_tokens = sum(len(message.content) for message in request.messages)
    arguments = {
        "kind": "chapter_draft",
        "summary": "模拟章节正文草案。",
        "content": "这是模拟模型生成的完整章节正文，用于验证待审核草案流程。",
        "artifactKey": "fake-chapter-draft",
        "submitForReview": True,
    }
    completion_tokens = len(json.dumps(arguments, ensure_ascii=False))
    return ModelTurnResult(
        content="",
        toolCalls=[
            ModelToolCall(
                id="legacy-fake-artifact-output",
                name="begin_artifact_output",
                arguments=arguments,
            )
        ],
        finishReason="tool_calls",
        rawFinishReason="tool_calls",
        usage=ModelUsage(
            promptTokens=prompt_tokens,
            cachedTokens=0,
            completionTokens=completion_tokens,
            totalTokens=prompt_tokens + completion_tokens,
        ),
        diagnostics=ModelUsageDiagnostics(),
        effectiveMaxOutputTokens=request.maxOutputTokens,
    )

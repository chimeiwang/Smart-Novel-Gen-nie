from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_agents.providers.openai_compatible import OpenAICompatibleProvider
from langchain_core.messages import AIMessage


class StubModel:
    def __init__(self, response: AIMessage) -> None:
        self._response = response

    def bind_tools(self, tools: list[dict[str, object]]) -> StubModel:
        del tools
        return self

    async def ainvoke(self, messages: object, **kwargs: object) -> AIMessage:
        del messages, kwargs
        return self._response


def provider_with_response(response: AIMessage) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider.__new__(OpenAICompatibleProvider)
    provider._model = StubModel(response)  # type: ignore[attr-defined]
    provider.model_name = "test-model"
    return provider


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_reason", "expected_reason", "expected_raw"),
    [
        ("stop", "stop", "stop"),
        ("function_call", "tool_calls", "function_call"),
        ("max_tokens", "length", "max_tokens"),
        ("future_provider_reason", "unknown", "future_provider_reason"),
        (None, "unknown", None),
        (["length"], "unknown", "['length']"),
    ],
)
async def test_complete_turn_normalizes_provider_finish_reason(
    raw_reason: Any,
    expected_reason: str,
    expected_raw: str | None,
) -> None:
    response = AIMessage(
        content="完整响应",
        response_metadata={"finish_reason": raw_reason},
    )

    result = await provider_with_response(response).complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[],
            maxOutputTokens=128,
        )
    )

    assert result.finishReason == expected_reason
    assert result.rawFinishReason == expected_raw


@pytest.mark.asyncio
async def test_complete_turn_treats_missing_finish_reason_as_unknown() -> None:
    result = await provider_with_response(AIMessage(content="完整响应")).complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[],
            maxOutputTokens=128,
        )
    )

    assert result.finishReason == "unknown"
    assert result.rawFinishReason is None

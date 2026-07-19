from __future__ import annotations

from typing import Any

import pytest
from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_agents.providers.openai_compatible import OpenAICompatibleProvider
from inkforge_agents.tools.registry import build_default_registry
from langchain_core.messages import AIMessage


class StubModel:
    def __init__(self, response: AIMessage) -> None:
        self._response = response
        self.bound_tools: list[dict[str, object]] = []
        self.tool_choice: str | None = None
        self.invoke_kwargs: dict[str, object] = {}

    def bind_tools(
        self,
        tools: list[dict[str, object]],
        *,
        tool_choice: str | None = None,
    ) -> StubModel:
        self.bound_tools = tools
        self.tool_choice = tool_choice
        return self

    async def ainvoke(self, messages: object, **kwargs: object) -> AIMessage:
        del messages
        self.invoke_kwargs = kwargs
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


@pytest.mark.asyncio
async def test_complete_turn_passes_object_schema_to_provider() -> None:
    provider = provider_with_response(
        AIMessage(content="", response_metadata={"finish_reason": "stop"})
    )
    tool = build_default_registry().require("submit_short_story_outline").as_model_tool()

    await provider.complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[tool],
            maxOutputTokens=128,
        )
    )

    model = provider._model  # type: ignore[attr-defined]
    parameters = model.bound_tools[0]["function"]["parameters"]
    assert parameters["type"] == "object"


@pytest.mark.asyncio
async def test_complete_turn_forces_explicit_required_tool() -> None:
    provider = provider_with_response(
        AIMessage(content="", response_metadata={"finish_reason": "tool_calls"})
    )
    tool = build_default_registry().require("submit_evaluation").as_model_tool()

    await provider.complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "复审"}],
            tools=[tool],
            requiredToolName="submit_evaluation",
            maxOutputTokens=128,
        )
    )

    model = provider._model  # type: ignore[attr-defined]
    assert model.tool_choice == "submit_evaluation"
    assert model.invoke_kwargs["extra_body"] == {
        "thinking": {"type": "disabled"}
    }


@pytest.mark.asyncio
async def test_complete_turn_repairs_invalid_tool_call_json() -> None:
    response = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "id": "call-outline",
                "name": "submit_short_story_outline",
                "args": '{"mode":"full" "corePremise":"接受失去"}',
                "error": "缺少逗号",
                "type": "invalid_tool_call",
            }
        ],
        response_metadata={"finish_reason": "tool_calls"},
    )

    result = await provider_with_response(response).complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "测试"}],
            tools=[],
            maxOutputTokens=128,
        )
    )

    assert result.toolCalls[0].id == "call-outline"
    assert result.toolCalls[0].name == "submit_short_story_outline"
    assert result.toolCalls[0].arguments == {
        "mode": "full",
        "corePremise": "接受失去",
    }

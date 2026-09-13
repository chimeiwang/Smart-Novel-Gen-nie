from __future__ import annotations

import inspect

import pytest
from inkforge_agents.providers.base import (
    ModelExecutionPolicy,
    ModelMessage,
    ModelTool,
    ModelTurnRequest,
)

from . import run_e2e


def test_legacy_langgraph_phase_has_explicit_v1_rollback_gate() -> None:
    assert "legacy-langgraph" in run_e2e.E2E_PHASES
    assert run_e2e.phase_config("legacy-langgraph") == {
        "routeMode": "off",
        "schemaReady": True,
        "v1FreshStartsEnabled": True,
    }


def test_legacy_langgraph_scenario_uses_old_web_body_and_real_gateway() -> None:
    from .legacy_langgraph import scenarios

    source = inspect.getsource(scenarios)
    assert '"selectedAgents"' in source
    assert '"userMessage"' in source
    assert "get_writing_context" in source
    assert "engineVersion" in source
    assert "outline" in source


@pytest.mark.asyncio
async def test_v1_fake_provider_reads_outline_before_artifact_tool() -> None:
    from .controlled_provider import ControlledFakeModelProvider

    provider = ControlledFakeModelProvider(control_url="http://unused", control_token="t" * 40)
    tools = [
        ModelTool(name="list_outline_summary", description="", parameters={}),
        ModelTool(name="begin_artifact_output", description="", parameters={}),
    ]
    request = ModelTurnRequest(
        messages=[ModelMessage(role="user", content="请生成正文")],
        tools=tools,
        maxOutputTokens=2000,
        policy=ModelExecutionPolicy(
            policyId="legacy:provider-default", thinkingMode="provider_default"
        ),
    )
    first = await provider.complete_turn(request)
    assert [call.name for call in first.toolCalls] == ["list_outline_summary"]
    second = await provider.complete_turn(
        request.model_copy(update={
            "messages": [
                *request.messages,
                ModelMessage(role="assistant", content="", toolCalls=first.toolCalls),
                    ModelMessage(
                        role="tool",
                        name="list_outline_summary",
                        content="{}",
                        toolCallId=first.toolCalls[0].id,
                    ),
            ]
        })
    )
    assert [call.name for call in second.toolCalls] == ["begin_artifact_output"]
    await provider.aclose()

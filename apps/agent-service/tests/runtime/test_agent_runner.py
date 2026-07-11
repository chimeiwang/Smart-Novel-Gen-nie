from __future__ import annotations

import pytest
from inkforge_agents.definitions.agents import AGENT_DEFINITIONS
from inkforge_agents.providers.base import ModelTurnRequest, ModelTurnResult, ModelUsage
from inkforge_agents.runtime.agent_runner import AgentRunner, AgentRunRequest
from inkforge_agents.runtime.agent_runtime import AgentRuntime
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_agents.tools.registry import ToolContext, build_default_registry


class CapturingProvider:
    billable = False

    def __init__(self) -> None:
        self.request: ModelTurnRequest | None = None

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.request = request
        return ModelTurnResult(
            content="已完成",
            toolCalls=[],
            usage=ModelUsage(
                promptTokens=1,
                cachedTokens=0,
                completionTokens=1,
                totalTokens=2,
            ),
        )


@pytest.mark.asyncio
async def test_runner_builds_prompt_and_exposes_only_agent_tools() -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    runner = AgentRunner(
        AgentRuntime(ModelRuntime(provider), registry),
        registry,
    )
    result = await runner.run(
        AgentRunRequest(
            agentId="写作",
            userMessage="续写本章",
            contextMessages=["当前章节目标：主角逃离围城"],
            toolContext=ToolContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                agentId="写作",
            ),
        )
    )

    assert result.agentId == "写作"
    assert provider.request is not None
    assert provider.request.messages[0].role == "system"
    assert "小说正文创作者" in provider.request.messages[0].content
    tool_names = {tool.name for tool in provider.request.tools}
    assert "begin_artifact_output" in tool_names
    assert "get_recent_chapters" in tool_names
    assert "submit_evaluation" not in tool_names
    assert "propose_updates" not in tool_names


def test_all_five_agents_use_single_output_protocol() -> None:
    assert set(AGENT_DEFINITIONS) == {"设定", "剧情", "写作", "校验", "编辑"}
    assert {definition.outputMode for definition in AGENT_DEFINITIONS.values()} == {
        "paragraph_text_with_control_tools"
    }

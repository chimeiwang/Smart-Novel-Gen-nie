from __future__ import annotations

import asyncio

import pytest
from inkforge_agents.providers.base import (
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.runtime.agent_runtime import AgentRuntime
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_agents.tools.registry import ToolContext, build_default_registry


def turn(
    content: str,
    *tool_calls: tuple[str, str, dict[str, object]],
) -> ModelTurnResult:
    return ModelTurnResult(
        content=content,
        toolCalls=[
            ModelToolCall(id=call_id, name=name, arguments=arguments)
            for call_id, name, arguments in tool_calls
        ],
        usage=ModelUsage(
            promptTokens=10,
            cachedTokens=2,
            completionTokens=5,
            totalTokens=15,
        ),
    )


class ScriptedProvider:
    billable = False

    def __init__(self, responses: list[ModelTurnResult | Exception]) -> None:
        self.responses = responses
        self.requests: list[ModelTurnRequest] = []

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0

    async def execute(
        self,
        tool_name: str,
        context: ToolContext,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        del context, arguments
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.calls.append(tool_name)
        self.active -= 1
        return {"tool": tool_name, "ok": True}


def context(agent_id: str = "设定") -> ToolContext:
    return ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId=agent_id,
    )


@pytest.mark.asyncio
async def test_runtime_accumulates_full_text_and_parallelizes_safe_reads() -> None:
    long_text = "正文" * 20_000
    provider = ScriptedProvider(
        [
            turn(
                long_text,
                ("call-1", "get_novel_info", {}),
                ("call-2", "list_characters_summary", {}),
            ),
            turn("最终结论"),
        ]
    )
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = AgentRuntime(ModelRuntime(provider), registry)

    result = await runtime.run(
        messages=[{"role": "user", "content": "分析设定"}],
        exposed_tools=registry.for_agent(
            agent_id="设定",
            capabilities={"novel.read", "character.read"},
        ),
        context=context(),
    )

    assert result.visibleContent == long_text + "\n\n最终结论"
    assert gateway.max_active == 2
    assert len(provider.requests) == 2
    assert result.usage.totalTokens == 30


@pytest.mark.asyncio
async def test_runtime_captures_control_events_in_model_order() -> None:
    provider = ScriptedProvider(
        [
            turn(
                "复审完成",
                (
                    "call-1",
                    "submit_validation_report",
                    {"hasConflicts": False, "conflicts": []},
                ),
                (
                    "call-2",
                    "submit_evaluation",
                    {
                        "artifactKey": "task-1:write_chapter",
                        "verdict": "pass",
                        "summary": "一致性通过",
                    },
                ),
            )
        ]
    )
    registry = build_default_registry(RecordingGateway())
    runtime = AgentRuntime(ModelRuntime(provider), registry)

    result = await runtime.run(
        messages=[{"role": "user", "content": "复审"}],
        exposed_tools=registry.for_agent(
            agent_id="校验",
            capabilities={"control.validation", "control.evaluation"},
        ),
        context=context("校验"),
        terminal_control_tools={"submit_evaluation"},
    )

    assert [event["type"] for event in result.controlEvents] == [
        "submit_validation_report",
        "submit_evaluation",
    ]
    assert result.finishReason == "terminal_control_tool"


@pytest.mark.asyncio
async def test_runtime_constrains_update_builder_lifecycle() -> None:
    provider = ScriptedProvider(
        [
            turn(
                "开始整理",
                (
                    "call-1",
                    "start_update_builder",
                    {"artifactKey": "task-1:sync_lore", "summary": "同步设定"},
                ),
            ),
            turn(
                "重复开始",
                (
                    "call-2",
                    "start_update_builder",
                    {"artifactKey": "task-1:sync_lore", "summary": "同步设定"},
                ),
            ),
            turn(
                "整理完成",
                (
                    "call-3",
                    "append_update_batch",
                    {
                        "artifactKey": "task-1:sync_lore",
                        "updates": {"storyBackground": "新增事实"},
                    },
                ),
                (
                    "call-4",
                    "finish_update_builder",
                    {"artifactKey": "task-1:sync_lore", "summary": "同步设定"},
                ),
            ),
        ]
    )
    registry = build_default_registry(RecordingGateway())
    runtime = AgentRuntime(ModelRuntime(provider), registry)

    result = await runtime.run(
        messages=[{"role": "user", "content": "同步设定"}],
        exposed_tools=registry.for_agent(
            agent_id="设定",
            capabilities={"control.builder"},
        ),
        context=context(),
        terminal_control_tools={"finish_update_builder"},
    )

    assert "start_update_builder" not in {
        tool.name for tool in provider.requests[1].tools
    }
    assert [event["type"] for event in result.controlEvents] == [
        "start_update_builder",
        "append_update_batch",
        "finish_update_builder",
    ]
    assert result.finishReason == "terminal_control_tool"


@pytest.mark.asyncio
async def test_runtime_rejects_unexposed_tool_and_invalid_arguments() -> None:
    registry = build_default_registry(RecordingGateway())
    unauthorized = AgentRuntime(
        ModelRuntime(
            ScriptedProvider([turn("", ("call-1", "submit_evaluation", {"verdict": "pass"}))])
        ),
        registry,
    )

    result = await unauthorized.run(
        messages=[{"role": "user", "content": "越权调用"}],
        exposed_tools=[],
        context=context(),
    )
    assert result.finishReason == "tool_authorization_error"
    assert "未向当前智能体暴露" in result.visibleContent

    invalid = AgentRuntime(
        ModelRuntime(ScriptedProvider([turn("", ("call-2", "get_character_detail", {}))])),
        registry,
    )
    result = await invalid.run(
        messages=[{"role": "user", "content": "读取角色"}],
        exposed_tools=registry.for_agent(agent_id="设定", capabilities={"character.read"}),
        context=context(),
    )
    assert result.finishReason == "tool_validation_error"
    assert "工具参数校验失败" in result.visibleContent


@pytest.mark.asyncio
async def test_runtime_stops_at_max_iterations_and_surfaces_provider_failure() -> None:
    looping = ScriptedProvider(
        [turn("", (f"call-{index}", "get_novel_info", {})) for index in range(3)]
    )
    registry = build_default_registry(RecordingGateway())
    runtime = AgentRuntime(ModelRuntime(looping), registry)
    result = await runtime.run(
        messages=[{"role": "user", "content": "循环"}],
        exposed_tools=registry.for_agent(agent_id="设定", capabilities={"novel.read"}),
        context=context(),
        max_iterations=2,
    )
    assert result.finishReason == "max_iterations"

    failing = AgentRuntime(ModelRuntime(ScriptedProvider([RuntimeError("供应商不可用")])), registry)
    with pytest.raises(RuntimeError, match="供应商不可用"):
        await failing.run(
            messages=[{"role": "user", "content": "失败"}],
            exposed_tools=[],
            context=context(),
        )

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import Any

import jsonschema_rs
import pytest
from inkforge_agents.definitions.agents import AGENT_DEFINITIONS
from inkforge_agents.operations.definitions import OPERATION_DEFINITIONS
from inkforge_agents.providers.base import (
    ModelExecutionPolicy,
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.runtime.agent_runner import AgentRunner, AgentRunRequest
from inkforge_agents.runtime.agent_runtime import AgentRuntime
from inkforge_agents.runtime.execution import (
    QUALITY_AGENT_ID,
    resolve_execution_contract,
    validate_execution_agent,
)
from inkforge_agents.runtime.model_policy import (
    CREATIVE_HIGH,
    QUALITY_NO_THINKING,
    REVIEWER_NO_THINKING,
)
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_agents.tools.registry import ToolContext, build_default_registry
from pydantic import ValidationError

USAGE = ModelUsage(
    promptTokens=1,
    cachedTokens=0,
    completionTokens=1,
    totalTokens=2,
)


class CapturingProvider:
    billable = False

    def __init__(self) -> None:
        self.requests: list[ModelTurnRequest] = []

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        return ModelTurnResult(
            content="已完成",
            toolCalls=[],
            finishReason="stop",
            rawFinishReason="stop",
            usage=USAGE,
        )


class TerminalProvider:
    billable = False

    def __init__(self, tool_name: str, arguments: Mapping[str, Any]) -> None:
        self.tool_name = tool_name
        self.arguments = dict(arguments)
        self.calls = 0
        self.requests: list[ModelTurnRequest] = []

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.calls += 1
        self.requests.append(request)
        if self.calls > 1:
            raise AssertionError("终止控制工具成功后不应再次调用模型")
        assert self.tool_name in {tool.name for tool in request.tools}
        return ModelTurnResult(
            content="草案正文",
            toolCalls=[
                ModelToolCall(id="call-1", name=self.tool_name, arguments=self.arguments)
            ],
            finishReason="tool_calls",
            rawFinishReason="tool_calls",
            usage=USAGE,
        )


def tool_context(agent_id: str) -> ToolContext:
    return ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId=agent_id,
    )


def make_agent_runtime(
    model_runtime: ModelRuntime,
    registry: object,
) -> AgentRuntime:
    return AgentRuntime(  # type: ignore[arg-type]
        model_runtime,
        registry,
        max_output_tokens=16_384,
    )


def request(
    *,
    agent_id: str = "写作",
    mode: str = "primary",
    operation_kind: str | None = "write_chapter",
) -> AgentRunRequest:
    return AgentRunRequest(
        agentId=agent_id,
        executionMode=mode,
        operationKind=operation_kind,
        userMessage="处理当前任务",
        contextMessages=["当前章节目标：主角逃离围城"],
        executionInstructions=["上次缺少草案事件，本次必须提交。"],
        toolContext=tool_context(agent_id),
    )  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_runner_keeps_server_instruction_system_and_context_low_privilege() -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)

    await runner.run(request())

    messages = provider.requests[0].messages
    assert [item.role for item in messages].count("system") == 2
    assert "上次缺少草案事件" in messages[1].content
    context = next(item for item in messages if item.name == "project_context")
    assert context.role == "user"
    assert "主角逃离围城" in context.content
    assert [item.content for item in messages].count("处理当前任务") == 1


@pytest.mark.asyncio
async def test_reviser_keeps_required_changes_out_of_system_messages() -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)
    reviser_request = request(mode="reviser", operation_kind="write_chapter")
    reviser_request.contextMessages = [
        '权威草案：{"artifactKey":"authority-key","requiredChanges":"补足冲突"}'
    ]

    await runner.run(reviser_request)

    messages = provider.requests[0].messages
    system_text = "\n".join(item.content for item in messages if item.role == "system")
    context = next(item for item in messages if item.name == "project_context")
    assert "begin_artifact_output" in system_text
    assert "权威 artifactKey" in system_text
    assert "完整重写" in system_text
    assert "requiredChanges" not in system_text
    assert "requiredChanges" in context.content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "agent_id",
        "mode",
        "operation_kind",
        "expected",
        "expected_policy",
    ),
    [
        (
            "写作",
            "primary",
            "write_chapter",
            OPERATION_DEFINITIONS["write_chapter"].allowedToolNames,
            CREATIVE_HIGH,
        ),
        (
            "校验",
            "reviewer",
            "write_chapter",
            frozenset({"submit_evaluation"}),
            REVIEWER_NO_THINKING,
        ),
        (
            "写作",
            "reviser",
            "write_chapter",
            OPERATION_DEFINITIONS["write_chapter"].allowedToolNames,
            CREATIVE_HIGH,
        ),
        (
            QUALITY_AGENT_ID,
            "quality",
            None,
            frozenset({"submit_quality_report"}),
            QUALITY_NO_THINKING,
        ),
    ],
)
async def test_runner_exposes_exact_execution_mode_tools(
    agent_id: str,
    mode: str,
    operation_kind: str | None,
    expected: frozenset[str],
    expected_policy: ModelExecutionPolicy,
) -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)

    await runner.run(
        request(agent_id=agent_id, mode=mode, operation_kind=operation_kind)
    )

    assert len(provider.requests) == 1
    assert {tool.name for tool in provider.requests[0].tools} == expected
    actual_policy = provider.requests[0].policy
    assert actual_policy.policyId == expected_policy.policyId
    assert actual_policy.thinkingMode == expected_policy.thinkingMode
    assert actual_policy.reasoningEffort == expected_policy.reasoningEffort
    assert actual_policy.requiredToolName == expected_policy.requiredToolName


@pytest.mark.asyncio
async def test_runner_rejects_required_policy_tool_before_provider() -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    registry.for_execution = lambda **kwargs: []  # type: ignore[method-assign]
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)

    with pytest.raises(ValueError, match="模型策略要求的终止工具未暴露"):
        await runner.run(
            request(agent_id="校验", mode="reviewer", operation_kind="write_chapter")
        )

    assert provider.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation_kind", "expected", "unexpected"),
    [
        ("plan_chapter", "submit_beat_plan", "begin_artifact_output"),
        ("write_chapter", "begin_artifact_output", "submit_beat_plan"),
    ],
)
async def test_primary_artifact_operations_do_not_expose_wrong_artifact_tool(
    operation_kind: str,
    expected: str,
    unexpected: str,
) -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)
    agent_id = OPERATION_DEFINITIONS[operation_kind].primaryAgent  # type: ignore[index]

    await runner.run(
        request(agent_id=agent_id, mode="primary", operation_kind=operation_kind)
    )

    names = {tool.name for tool in provider.requests[0].tools}
    assert expected in names
    assert unexpected not in names
    assert "submit_evaluation" not in names


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["primary", "reviser"])
@pytest.mark.parametrize("operation_kind", [
    "write_chapter", "rewrite_scene", "rewrite_chapter_selection", "rewrite_outline_selection",
])
async def test_实际模型请求按操作约束产物且注册工具保持不变(
    mode: str, operation_kind: str,
) -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    tool = registry.require("begin_artifact_output")
    original_schema = tool.as_model_tool().parameters
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)
    is_selection = operation_kind.endswith("_selection")
    is_outline = operation_kind == "rewrite_outline_selection"
    agent_id = "剧情" if is_outline else "写作"
    selection = {
        "kind": "outline_draft" if is_outline else "chapter_draft",
        "summary": "选区草案",
        "operation": "rewrite_outline_selection" if is_outline else "rewrite_chapter_selection",
        "resourceType": "outline_node_content" if is_outline else "chapter_content",
        "resourceId": "resource-1", "baseUpdatedAt": "2026-09-30T00:00:00Z",
        "baseContentHash": "a" * 64, "selectionStart": 1, "selectionEnd": 2,
        "selectedTextHash": "b" * 64, "replacement": "完整替换文本",
    }
    full = {"kind": "chapter_draft", "summary": "章节草案", "content": "完整正文"}
    run_request = AgentRunRequest(
        agentId=agent_id, executionMode=mode, operationKind=operation_kind,
        userMessage="处理当前任务", toolContext=tool_context(agent_id),
        selectionSnapshot=selection if is_selection else None,
    )  # type: ignore[arg-type]

    await runner.run(run_request)

    model_tool = next(
        item for item in provider.requests[0].tools if item.name == "begin_artifact_output"
    )
    validator = jsonschema_rs.validator_for(model_tool.parameters)
    assert validator.is_valid(selection if is_selection else full)
    assert not validator.is_valid(full if is_selection else selection)
    assert not validator.is_valid({**selection, "content": "混入全文"})
    assert registry.require("begin_artifact_output") is tool
    assert tool.as_model_tool().parameters == original_schema


@pytest.mark.asyncio
async def test_章节计划模型无需填写数量而控制事件保留数量() -> None:
    provider = TerminalProvider("submit_beat_plan", {
        "title": "章节计划", "summary": "章节摘要", "chapterGoal": "完成目标",
        "sceneBeats": [{"goal": "第一个节拍"}, {"goal": "第二个节拍"}],
    })
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)

    result = await runner.run(request(agent_id="剧情", operation_kind="plan_chapter"))

    model_tool = next(
        item for item in provider.requests[0].tools if item.name == "submit_beat_plan"
    )
    assert "beatCount" not in model_tool.parameters["properties"]
    assert result.controlEvents[0]["beatCount"] == 2
    assert len(result.controlEvents[0]["sceneBeats"]) == 2


@pytest.mark.asyncio
async def test_旧正文参数的显式空选区字段仍等价于省略() -> None:
    provider = TerminalProvider("begin_artifact_output", {
        "kind": "chapter_draft", "summary": "章节草案", "content": "完整正文",
        "operation": None, "resourceType": None, "resourceId": None,
        "baseUpdatedAt": None, "baseContentHash": None, "selectionStart": None,
        "selectionEnd": None, "selectedTextHash": None, "replacement": None,
    })
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)

    result = await runner.run(request())

    assert provider.calls == 1
    assert result.controlEvents == [{
        "type": "begin_artifact_output", "kind": "chapter_draft",
        "summary": "章节草案", "content": "完整正文",
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_id", "mode", "operation_kind"),
    [
        ("编辑", "primary", "write_chapter"),
        ("设定", "reviser", "write_chapter"),
        ("设定", "reviewer", "write_chapter"),
        ("编辑", "quality", None),
        ("编辑", "primary", "sync_lore"),
    ],
)
async def test_runner_rejects_invalid_agent_mode_operation_combination(
    agent_id: str,
    mode: str,
    operation_kind: str | None,
) -> None:
    provider = CapturingProvider()
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)

    with pytest.raises(ValueError, match="AGENT_EXECUTION_MODE_INVALID"):
        await runner.run(
            request(agent_id=agent_id, mode=mode, operation_kind=operation_kind)
        )

    assert provider.requests == []


@pytest.mark.parametrize(
    ("mode", "operation_kind", "message"),
    [
        ("quality", "write_chapter", "质量模式不能绑定 CreativeOperation"),
        ("primary", None, "创作执行模式缺少 Operation"),
        ("reviewer", None, "创作执行模式缺少 Operation"),
        ("reviser", None, "创作执行模式缺少 Operation"),
    ],
)
def test_request_rejects_invalid_mode_operation_scope(
    mode: str,
    operation_kind: str | None,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        request(mode=mode, operation_kind=operation_kind)


def test_request_rejects_agent_context_mismatch_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="运行智能体与工具上下文智能体不一致"):
        AgentRunRequest(
            agentId="写作",
            executionMode="primary",
            operationKind="write_chapter",
            userMessage="续写本章",
            toolContext=tool_context("编辑"),
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        AgentRunRequest(
            agentId="写作",
            executionMode="primary",
            operationKind="write_chapter",
            userMessage="续写本章",
            toolMode="all",
            toolContext=tool_context("写作"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_id", "mode", "operation_kind", "tool_name", "arguments"),
    [
        (
            "写作",
            "primary",
            "write_chapter",
            "begin_artifact_output",
            {"kind": "chapter_draft", "summary": "正文草案", "content": "草案正文"},
        ),
        (
            "校验",
            "reviewer",
            "write_chapter",
            "submit_evaluation",
            {"artifactKey": "task-1:chapter", "verdict": "pass", "summary": "通过"},
        ),
        (
            "写作",
            "reviser",
            "write_chapter",
            "begin_artifact_output",
            {"kind": "chapter_draft", "summary": "返工正文", "content": "返工正文"},
        ),
        (
            QUALITY_AGENT_ID,
            "quality",
            None,
            "submit_quality_report",
            {
                "scores": {
                    "characterConsistency": 90.0,
                    "worldRuleConsistency": 90.0,
                    "timelineConsistency": 90.0,
                    "causalityConsistency": 90.0,
                    "foreshadowingConsistency": 90.0,
                },
                "qualityGate": "pass",
                "issues": [],
                "report": "一致性终检通过。",
                "rewriteBrief": None,
            },
        ),
    ],
)
async def test_runtime_stops_on_call_level_terminal_tool(
    agent_id: str,
    mode: str,
    operation_kind: str | None,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> None:
    provider = TerminalProvider(tool_name, arguments)
    registry = build_default_registry()
    runner = AgentRunner(make_agent_runtime(ModelRuntime(provider), registry), registry)

    result = await runner.run(
        request(agent_id=agent_id, mode=mode, operation_kind=operation_kind)
    )

    assert provider.calls == 1
    assert result.finishReason == "terminal_control_tool"
    assert [event["type"] for event in result.controlEvents] == [tool_name]
    if mode == "quality":
        assert {tool.name for tool in provider.requests[0].tools} == {"submit_quality_report"}
        assert provider.requests[0].tools[0].strict is True


def test_execution_tool_contract_is_immutable() -> None:
    contract = resolve_execution_contract("primary", "write_chapter")

    with pytest.raises(FrozenInstanceError):
        contract.mode = "reviewer"  # type: ignore[misc]


def test_quality_execution_uses_single_authoritative_agent_identity() -> None:
    contract = resolve_execution_contract("quality", None)

    validate_execution_agent(contract, QUALITY_AGENT_ID)
    for agent_id in AGENT_DEFINITIONS:
        if agent_id != QUALITY_AGENT_ID:
            with pytest.raises(ValueError, match="AGENT_EXECUTION_MODE_INVALID"):
                validate_execution_agent(contract, agent_id)  # type: ignore[arg-type]


def test_agent_definition_no_longer_declares_global_terminal_tools() -> None:
    assert set(AGENT_DEFINITIONS) == {"设定", "剧情", "写作", "校验", "编辑"}
    assert all(
        not hasattr(definition, "terminalControlTools")
        for definition in AGENT_DEFINITIONS.values()
    )

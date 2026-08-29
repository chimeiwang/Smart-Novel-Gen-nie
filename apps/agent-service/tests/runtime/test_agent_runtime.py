from __future__ import annotations

import asyncio
from typing import Any

import pytest
from inkforge_agents.providers.base import (
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.queue.cancellation import JobCancelledError
from inkforge_agents.runtime.agent_runtime import (
    AgentRuntime,
    ModelToolProtocolRecoveryFailedError,
)
from inkforge_agents.runtime.model_policy import CREATIVE_HIGH, LEGACY_PROVIDER_DEFAULT
from inkforge_agents.runtime.model_runtime import ModelCallContext, ModelRuntime
from inkforge_agents.tools.registry import (
    ToolContext,
    ToolDefinition,
    build_default_registry,
)


def turn(
    content: str,
    *tool_calls: tuple[str, str, dict[str, object]],
    finish_reason: str | None = None,
) -> ModelTurnResult:
    resolved_finish_reason = finish_reason or ("tool_calls" if tool_calls else "stop")
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
        finishReason=resolved_finish_reason,
        rawFinishReason=resolved_finish_reason,
    )


def invalid_tool_turn(
    *,
    content: str = "",
    valid_calls: tuple[tuple[str, str, dict[str, object]], ...] = (),
    name: str = "get_character_detail",
    code: str = "json_decode_error",
    argument_character_count: int = 17,
) -> ModelTurnResult:
    return ModelTurnResult(
        content=content,
        toolCalls=[
            ModelToolCall(id=call_id, name=tool_name, arguments=arguments)
            for call_id, tool_name, arguments in valid_calls
        ],
        invalidToolCallCount=1,
        invalidToolCallNames=[name],
        invalidToolCallCodes=[code],
        invalidToolCallArgumentCharacterCounts=[argument_character_count],
        usage=ModelUsage(
            promptTokens=10,
            cachedTokens=2,
            completionTokens=5,
            totalTokens=15,
        ),
        finishReason="tool_calls",
        rawFinishReason="tool_calls",
    )


class ScriptedProvider:
    billable = False
    provider_name = "openai_compatible"
    model_name = "deepseek-v4-flash"

    def __init__(self, responses: list[ModelTurnResult | Exception]) -> None:
        self.responses = responses
        self.requests: list[ModelTurnRequest] = []

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RecordingBilling:
    def __init__(self) -> None:
        self.authorizations: list[dict[str, Any]] = []
        self.usages: list[dict[str, Any]] = []

    async def authorize(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> dict[str, Any]:
        del context
        self.authorizations.append({**payload, "requestId": request_id})
        return {
            "requestId": request_id,
            "grantToken": f"grant-{len(self.authorizations)}",
            "maxOutputTokens": payload["requestedMaxOutputTokens"],
        }

    async def report(
        self,
        context: ModelCallContext,
        payload: dict[str, Any],
        request_id: str,
    ) -> None:
        del context
        self.usages.append({**payload, "reportedRequestId": request_id})


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


def make_agent_runtime(
    model_runtime: ModelRuntime,
    registry: object,
    **kwargs: object,
) -> AgentRuntime:
    return AgentRuntime(  # type: ignore[arg-type]
        model_runtime,
        registry,
        max_output_tokens=16_384,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_fake_provider_plan_chapter_uses_valid_strict_arguments() -> None:
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(FakeModelProvider()), registry)

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
        messages=[{"role": "user", "content": "规划当前章节"}],
        exposed_tools=registry.for_agent(
            agent_id="剧情", capabilities={"control.beat"}
        ),
        context=context("剧情"),
        terminal_control_tools={"submit_beat_plan"},
    )

    assert result.finishReason == "terminal_control_tool"
    assert result.controlEvents == [
        {
            "type": "submit_beat_plan",
            "title": "模拟章节计划",
            "beatCount": 1,
            "summary": "模拟章节计划草案。",
            "chapterGoal": "推进当前章节。",
            "totalEstimatedWords": 1000,
            "sceneBeats": [
                {
                    "order": 1,
                    "goal": "推进当前章节。",
                    "characters": [],
                    "estimatedWords": 1000,
                }
            ],
        }
    ]


class Cancellation:
    def __init__(self, cancel_on_check: int) -> None:
        self.cancel_on_check = cancel_on_check
        self.checks = 0

    async def ensure_active(self, job_id: str | None) -> None:
        assert job_id == "job-1"
        self.checks += 1
        if self.checks >= self.cancel_on_check:
            raise JobCancelledError()


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
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    result = await runtime.run(
        policy=CREATIVE_HIGH,
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
    assert [request.policy for request in provider.requests] == [
        CREATIVE_HIGH,
        CREATIVE_HIGH,
    ]


@pytest.mark.asyncio
async def test_runtime_stops_after_model_cancellation_without_recording_content_or_tools() -> None:
    provider = ScriptedProvider(
        [turn("不应保留的正文", ("call-1", "get_novel_info", {}))]
    )
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    cancellation = Cancellation(cancel_on_check=2)
    runtime = make_agent_runtime(
        ModelRuntime(provider), registry, cancellation=cancellation
    )

    with pytest.raises(JobCancelledError):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "分析设定"}],
            exposed_tools=registry.for_agent(
                agent_id="设定", capabilities={"novel.read"}
            ),
            context=ToolContext(
                userId="user-1",
                novelId="novel-1",
                taskId="task-1",
                runId="run-1",
                jobId="job-1",
                agentId="设定",
            ),
        )

    assert len(provider.requests) == 1
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_运行时保留超过旧输出边界的完整正文() -> None:
    sentinel = "【正文尾部哨兵】"
    long_text = "长正文" * 9_000 + sentinel
    provider = ScriptedProvider([turn(long_text, finish_reason="stop")])
    registry = build_default_registry(RecordingGateway())
    runtime = AgentRuntime(
        ModelRuntime(provider),
        registry,
        max_output_tokens=384_000,
    )

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
        messages=[{"role": "user", "content": "生成长正文"}],
        exposed_tools=[],
        context=context("写作"),
    )

    assert len(result.visibleContent) > 8_192
    assert result.visibleContent == long_text
    assert result.visibleContent.endswith(sentinel)
    assert provider.requests[0].maxOutputTokens == 384_000


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
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
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
                "整理完成",
                (
                    "call-2",
                    "append_update_batch",
                    {
                        "artifactKey": "task-1:sync_lore",
                        "updates": {"storyBackground": "新增事实"},
                    },
                ),
                (
                    "call-3",
                    "finish_update_builder",
                    {"artifactKey": "task-1:sync_lore", "summary": "同步设定"},
                ),
            ),
        ]
    )
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
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
    unauthorized = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider([turn("", ("call-1", "submit_evaluation", {"verdict": "pass"}))])
        ),
        registry,
    )

    with pytest.raises(RuntimeError, match="MODEL_TOOL_NOT_EXPOSED"):
        await unauthorized.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "越权调用"}],
            exposed_tools=[],
            context=context(),
        )

    invalid_response = turn("", ("call-2", "get_character_detail", {}))
    invalid = make_agent_runtime(
        ModelRuntime(ScriptedProvider([invalid_response, invalid_response])),
        registry,
    )
    with pytest.raises(
        ModelToolProtocolRecoveryFailedError,
        match="MODEL_TOOL_PROTOCOL_RECOVERY_FAILED",
    ):
        await invalid.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "读取角色"}],
            exposed_tools=registry.for_agent(
                agent_id="设定", capabilities={"character.read"}
            ),
            context=context(),
        )


@pytest.mark.asyncio
async def test_runtime_reports_bounded_validation_paths_without_argument_values() -> None:
    raw_model_value = "绝不能进入异常或日志的模型原始值"
    registry = build_default_registry(RecordingGateway())
    invalid_arguments: dict[str, object] = {
        "scores": {},
        "qualityGate": raw_model_value,
        "issues": [{}],
        "report": {"raw": raw_model_value},
        "rewriteBrief": [raw_model_value],
    }
    invalid_response = turn(
        "",
        (
            "call-quality-invalid",
            "submit_quality_report",
            invalid_arguments,
        ),
    )
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider([invalid_response, invalid_response])
        ),
        registry,
    )

    with pytest.raises(ModelToolProtocolRecoveryFailedError) as caught:
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "质量检查"}],
            exposed_tools=[registry.require("submit_quality_report")],
            context=context("校验"),
            terminal_control_tools={"submit_quality_report"},
        )

    error = caught.value
    assert error.code == "MODEL_TOOL_PROTOCOL_RECOVERY_FAILED"
    assert error.protocol_issues == (
        "tool=submit_quality_report code=schema_validation chars=0",
    )
    assert len(error.validation_issues) == 10
    assert "loc=scores.characterConsistency type=missing" in error.validation_issues
    assert all(issue.startswith("loc=") and " type=" in issue for issue in error.validation_issues)
    assert raw_model_value not in str(error)
    assert raw_model_value not in repr(error.validation_issues)
    assert "input_value" not in str(error)
    assert error.__cause__ is None
    assert error.__suppress_context__ is True


@pytest.mark.asyncio
async def test_runtime_discards_whole_invalid_tool_package_and_corrects_once() -> None:
    discarded_content = "首轮不能保留的正文"
    provider = ScriptedProvider(
        [
            invalid_tool_turn(
                content=discarded_content,
                valid_calls=(("call-must-not-run", "get_novel_info", {}),),
            ),
            turn(
                "纠正后的工具说明",
                (
                    "call-corrected",
                    "get_character_detail",
                    {"character_name": "林澈"},
                ),
            ),
            turn("最终完成"),
        ]
    )
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
        messages=[
            {"role": "system", "content": "原始系统指令"},
            {"role": "user", "content": "读取角色"},
        ],
        exposed_tools=registry.for_agent(
            agent_id="设定",
            capabilities={"novel.read", "character.read"},
        ),
        context=context(),
    )

    assert gateway.calls == ["get_character_detail"]
    assert result.visibleContent == "纠正后的工具说明\n\n最终完成"
    assert discarded_content not in result.visibleContent
    assert result.usage.totalTokens == 45
    assert len(provider.requests) == 3
    correction_request = provider.requests[1]
    assert [message.role for message in correction_request.messages] == [
        "system",
        "system",
        "user",
    ]
    assert "工具协议校验" in correction_request.messages[1].content
    assert discarded_content not in correction_request.model_dump_json()
    assert correction_request.tools == provider.requests[0].tools
    assert correction_request.policy == provider.requests[0].policy


@pytest.mark.asyncio
async def test_runtime_corrects_pydantic_invalid_arguments_without_replaying_values() -> None:
    raw_model_value = "绝不能回放给模型的参数值"
    provider = ScriptedProvider(
        [
            turn(
                "不能保留",
                (
                    "call-invalid",
                    "get_character_detail",
                    {"unexpected": raw_model_value},
                ),
            ),
            turn(
                "",
                (
                    "call-corrected",
                    "get_character_detail",
                    {"character_name": "林澈"},
                ),
            ),
            turn("已完成"),
        ]
    )
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
        messages=[{"role": "user", "content": "读取角色"}],
        exposed_tools=registry.for_agent(
            agent_id="设定", capabilities={"character.read"}
        ),
        context=context(),
    )

    assert gateway.calls == ["get_character_detail"]
    assert result.visibleContent == "已完成"
    assert result.usage.totalTokens == 45
    assert raw_model_value not in provider.requests[1].model_dump_json()


@pytest.mark.asyncio
async def test_runtime_protocol_correction_uses_separate_authorization_and_usage() -> None:
    class BillableScriptedProvider(ScriptedProvider):
        billable = True

    provider = BillableScriptedProvider(
        [
            invalid_tool_turn(name="submit_validation_report"),
            turn(
                "",
                (
                    "call-corrected",
                    "submit_validation_report",
                    {"hasConflicts": False, "conflicts": []},
                ),
            ),
        ]
    )
    billing = RecordingBilling()
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(
        ModelRuntime(provider, billing=billing),
        registry,
    )
    model_context = ModelCallContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="校验",
    )

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
        messages=[{"role": "user", "content": "校验"}],
        exposed_tools=registry.for_agent(
            agent_id="校验", capabilities={"control.validation"}
        ),
        context=context("校验"),
        terminal_control_tools={"submit_validation_report"},
        model_context=model_context,
    )

    authorization_ids = [item["requestId"] for item in billing.authorizations]
    assert len(authorization_ids) == 2
    assert len(set(authorization_ids)) == 2
    assert [item["requestId"] for item in billing.usages] == authorization_ids
    assert [item["totalTokens"] for item in billing.usages] == [15, 15]
    assert result.usage.totalTokens == 30
    assert result.finishReason == "terminal_control_tool"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second_response",
    [
        invalid_tool_turn(argument_character_count=29),
        turn("不能用纯文本绕过工具纠正"),
    ],
)
async def test_runtime_fails_safely_when_single_protocol_correction_does_not_recover(
    second_response: ModelTurnResult,
) -> None:
    provider = ScriptedProvider(
        [
            invalid_tool_turn(argument_character_count=23),
            second_response,
        ]
    )
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    with pytest.raises(ModelToolProtocolRecoveryFailedError) as caught:
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "读取角色"}],
            exposed_tools=registry.for_agent(
                agent_id="设定", capabilities={"character.read"}
            ),
            context=context(),
        )

    assert caught.value.code == "MODEL_TOOL_PROTOCOL_RECOVERY_FAILED"
    assert caught.value.retryable is False
    assert len(provider.requests) == 2
    assert gateway.calls == []
    assert "arguments" not in str(caught.value)


@pytest.mark.asyncio
async def test_runtime_uses_only_one_protocol_correction_across_business_turns() -> None:
    provider = ScriptedProvider(
        [
            invalid_tool_turn(),
            turn("", ("call-corrected", "get_novel_info", {})),
            invalid_tool_turn(argument_character_count=31),
        ]
    )
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    with pytest.raises(ModelToolProtocolRecoveryFailedError):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "连续调用"}],
            exposed_tools=registry.for_agent(
                agent_id="设定",
                capabilities={"novel.read", "character.read"},
            ),
            context=context(),
        )

    assert len(provider.requests) == 3
    assert gateway.calls == ["get_novel_info"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "error_code"),
    [
        ("length", "MODEL_OUTPUT_TRUNCATED"),
        ("content_filter", "MODEL_OUTPUT_FILTERED"),
        ("insufficient_system_resource", "MODEL_INSUFFICIENT_SYSTEM_RESOURCE"),
    ],
)
async def test_runtime_does_not_correct_invalid_tools_from_incomplete_response(
    finish_reason: str,
    error_code: str,
) -> None:
    response = invalid_tool_turn().model_copy(
        update={
            "finishReason": finish_reason,
            "rawFinishReason": finish_reason,
        }
    )
    provider = ScriptedProvider([response])
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    with pytest.raises(RuntimeError, match=error_code):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "生成"}],
            exposed_tools=registry.for_agent(
                agent_id="设定", capabilities={"character.read"}
            ),
            context=context(),
        )

    assert len(provider.requests) == 1
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_runtime_does_not_spend_correction_call_without_exposed_tools() -> None:
    provider = ScriptedProvider(
        [invalid_tool_turn(name="unknown_tool", argument_character_count=7)]
    )
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    with pytest.raises(ModelToolProtocolRecoveryFailedError):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "普通问答"}],
            exposed_tools=[],
            context=context(),
        )

    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_runtime_rejects_exposed_control_tool_not_authorized_for_agent() -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [
                    turn(
                        "不能保留的正文",
                        (
                            "call-1",
                            "submit_quality_report",
                            {
                                "scores": {
                                    "character": 90,
                                    "world_rule": 90,
                                    "timeline": 90,
                                    "causality": 90,
                                    "foreshadowing": 90,
                                },
                                "issues": [],
                                "gate": "pass",
                            },
                        ),
                    )
                ]
            )
        ),
        registry,
    )

    with pytest.raises(PermissionError, match="当前智能体无权执行工具"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "越权质量检查"}],
            exposed_tools=[registry.require("submit_quality_report")],
            context=context("设定"),
            terminal_control_tools={"submit_quality_report"},
        )

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_runtime_rejects_same_name_unregistered_exposed_tool() -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    registered = registry.require("get_novel_info")
    unregistered = ToolDefinition(
        name=registered.name,
        description=registered.description,
        argumentsModel=registered.argumentsModel,
        permission=registered.permission,
        toolKind=registered.toolKind,
        handler=registered.handler,
    )
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [turn("不能保留的正文", ("call-1", "get_novel_info", {}))]
            )
        ),
        registry,
    )

    with pytest.raises(ValueError, match="工具定义与注册表不一致"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "读取小说"}],
            exposed_tools=[unregistered],
            context=context("设定"),
        )

    assert gateway.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("call_id", ["", "   "])
async def test_runtime_rejects_empty_tool_call_id_before_control_event(
    call_id: str,
) -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [
                    turn(
                        "不能保留的正文",
                        (
                            call_id,
                            "submit_validation_report",
                            {"hasConflicts": False, "conflicts": []},
                        ),
                    )
                ]
            )
        ),
        registry,
    )

    with pytest.raises(RuntimeError, match="MODEL_TOOL_CALL_ID_INVALID"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "校验"}],
            exposed_tools=[registry.require("submit_validation_report")],
            context=context("校验"),
            terminal_control_tools={"submit_validation_report"},
        )

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_runtime_rejects_duplicate_tool_call_id_before_any_side_effect() -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [
                    turn(
                        "不能保留的正文",
                        (
                            "duplicate-call",
                            "submit_validation_report",
                            {"hasConflicts": False, "conflicts": []},
                        ),
                        ("duplicate-call", "get_novel_info", {}),
                    )
                ]
            )
        ),
        registry,
    )

    with pytest.raises(RuntimeError, match="MODEL_TOOL_CALL_ID_DUPLICATE"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "校验"}],
            exposed_tools=[
                registry.require("submit_validation_report"),
                registry.require("get_novel_info"),
            ],
            context=context("校验"),
        )

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_runtime_preserves_empty_raw_finish_reason_in_error() -> None:
    response = turn("不能接受", finish_reason="length")
    response.rawFinishReason = ""
    runtime = make_agent_runtime(
        ModelRuntime(ScriptedProvider([response])),
        build_default_registry(RecordingGateway()),
    )

    with pytest.raises(RuntimeError, match="原始原因：）"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "测试"}],
            exposed_tools=[],
            context=context(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "error_code"),
    [
        ("length", "MODEL_OUTPUT_TRUNCATED"),
        ("content_filter", "MODEL_OUTPUT_FILTERED"),
    ],
)
async def test_runtime_rejects_incomplete_output_before_content_or_tool_side_effects(
    finish_reason: str,
    error_code: str,
) -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [
                    turn(
                        "这段正文不能被接受",
                        ("call-1", "get_novel_info", {}),
                        finish_reason=finish_reason,
                    )
                ]
            )
        ),
        registry,
    )

    with pytest.raises(RuntimeError, match=error_code):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "生成"}],
            exposed_tools=registry.for_agent(
                agent_id="设定", capabilities={"novel.read"}
            ),
            context=context(),
        )

    assert gateway.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        turn("", ("call-1", "get_novel_info", {}), finish_reason="stop"),
        turn("", finish_reason="tool_calls"),
    ],
)
async def test_runtime_rejects_finish_reason_and_tool_call_mismatch(
    response: ModelTurnResult,
) -> None:
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(ScriptedProvider([response])), registry)

    with pytest.raises(RuntimeError, match="PROVIDER_FINISH_REASON_INVALID"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "测试"}],
            exposed_tools=registry.for_agent(
                agent_id="设定", capabilities={"novel.read"}
            ),
            context=context(),
        )


@pytest.mark.asyncio
async def test_runtime_rejects_unknown_finish_reason_without_tools() -> None:
    runtime = make_agent_runtime(
        ModelRuntime(ScriptedProvider([turn("不能接受", finish_reason="unknown")])),
        build_default_registry(RecordingGateway()),
    )

    with pytest.raises(RuntimeError, match="PROVIDER_FINISH_REASON_UNKNOWN"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "测试"}],
            exposed_tools=[],
            context=context(),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "error_code"),
    [
        ("submit_evaluation", {"verdict": "pass"}, "MODEL_TOOL_NOT_EXPOSED"),
        ("get_character_detail", {}, "MODEL_TOOL_ARGUMENTS_INVALID"),
    ],
)
async def test_runtime_preflights_unknown_tool_calls_before_execution(
    tool_name: str,
    arguments: dict[str, object],
    error_code: str,
) -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    response = turn("", ("call-1", tool_name, arguments), finish_reason="unknown")
    responses = [response] if tool_name == "submit_evaluation" else [response, response]
    runtime = make_agent_runtime(
        ModelRuntime(ScriptedProvider(responses)),
        registry,
    )
    exposed = (
        []
        if tool_name == "submit_evaluation"
        else registry.for_agent(agent_id="设定", capabilities={"character.read"})
    )

    expected_error_code = (
        error_code
        if tool_name == "submit_evaluation"
        else "MODEL_TOOL_PROTOCOL_RECOVERY_FAILED"
    )
    with pytest.raises(RuntimeError, match=expected_error_code):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "测试"}],
            exposed_tools=exposed,
            context=context(),
        )

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_runtime_allows_unknown_finish_reason_with_valid_tool_calls() -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [
                    turn(
                        "读取中",
                        ("call-1", "get_novel_info", {}),
                        finish_reason="unknown",
                    ),
                    turn("完成"),
                ]
            )
        ),
        registry,
    )

    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
        messages=[{"role": "user", "content": "测试"}],
        exposed_tools=registry.for_agent(
            agent_id="设定", capabilities={"novel.read"}
        ),
        context=context(),
    )

    assert gateway.calls == ["get_novel_info"]
    assert result.visibleContent == "读取中\n\n完成"


@pytest.mark.asyncio
async def test_runtime_validates_all_tool_calls_before_first_side_effect() -> None:
    gateway = RecordingGateway()
    registry = build_default_registry(gateway)
    invalid_response = turn(
        "",
        ("call-1", "get_novel_info", {}),
        ("call-2", "get_character_detail", {}),
    )
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [invalid_response, invalid_response]
            )
        ),
        registry,
    )

    with pytest.raises(
        ModelToolProtocolRecoveryFailedError,
        match="MODEL_TOOL_PROTOCOL_RECOVERY_FAILED",
    ):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "测试"}],
            exposed_tools=registry.for_agent(
                agent_id="设定",
                capabilities={"novel.read", "character.read"},
            ),
            context=context(),
        )

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_runtime_rejects_multiple_terminal_tools_before_side_effects() -> None:
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [
                    turn(
                        "",
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
                                "summary": "通过",
                            },
                        ),
                    )
                ]
            )
        ),
        registry,
    )

    with pytest.raises(RuntimeError, match="MODEL_TERMINAL_TOOL_CONFLICT"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "复审"}],
            exposed_tools=registry.for_agent(
                agent_id="校验",
                capabilities={"control.validation", "control.evaluation"},
            ),
            context=context("校验"),
            terminal_control_tools={"submit_validation_report", "submit_evaluation"},
        )


@pytest.mark.asyncio
async def test_runtime_stops_at_max_iterations_and_surfaces_provider_failure() -> None:
    looping = ScriptedProvider(
        [turn("", (f"call-{index}", "get_novel_info", {})) for index in range(3)]
    )
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(looping), registry)
    result = await runtime.run(
        policy=LEGACY_PROVIDER_DEFAULT,
        messages=[{"role": "user", "content": "循环"}],
        exposed_tools=registry.for_agent(agent_id="设定", capabilities={"novel.read"}),
        context=context(),
        max_iterations=2,
    )
    assert result.finishReason == "max_iterations"

    failing = make_agent_runtime(
        ModelRuntime(ScriptedProvider([RuntimeError("供应商不可用")])),
        registry,
    )
    with pytest.raises(RuntimeError, match="^MODEL_PROVIDER_FAILED："):
        await failing.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "失败"}],
            exposed_tools=[],
            context=context(),
        )


@pytest.mark.asyncio
async def test_runtime_replays_reasoning_content_with_assistant_tool_call() -> None:
    first = turn("", ("call-1", "get_novel_info", {})).model_copy(
        update={"reasoningContent": "先读取作品资料"}
    )
    provider = ScriptedProvider([first, turn("已完成")])
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

    await runtime.run(
        policy=CREATIVE_HIGH,
        messages=[{"role": "user", "content": "请调用工具"}],
        exposed_tools=registry.for_agent(agent_id="设定", capabilities={"novel.read"}),
        context=context(),
    )

    assert provider.requests[1].messages[1].reasoningContent == "先读取作品资料"


@pytest.mark.asyncio
async def test_runtime_rejects_insufficient_system_resource_before_visible_content() -> None:
    response = turn("不应展示", finish_reason="insufficient_system_resource")
    registry = build_default_registry(RecordingGateway())
    runtime = make_agent_runtime(ModelRuntime(ScriptedProvider([response])), registry)

    with pytest.raises(RuntimeError, match="MODEL_INSUFFICIENT_SYSTEM_RESOURCE"):
        await runtime.run(
            policy=LEGACY_PROVIDER_DEFAULT,
            messages=[{"role": "user", "content": "测试"}],
            exposed_tools=[],
            context=context(),
        )

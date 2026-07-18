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


def make_agent_runtime(
    model_runtime: ModelRuntime,
    registry: object,
) -> AgentRuntime:
    return AgentRuntime(  # type: ignore[arg-type]
        model_runtime,
        registry,
        max_output_tokens=16_384,
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
    runtime = make_agent_runtime(ModelRuntime(provider), registry)

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
            messages=[{"role": "user", "content": "越权调用"}],
            exposed_tools=[],
            context=context(),
        )

    invalid = make_agent_runtime(
        ModelRuntime(ScriptedProvider([turn("", ("call-2", "get_character_detail", {}))])),
        registry,
    )
    with pytest.raises(RuntimeError, match="MODEL_TOOL_ARGUMENTS_INVALID"):
        await invalid.run(
            messages=[{"role": "user", "content": "读取角色"}],
            exposed_tools=registry.for_agent(
                agent_id="设定", capabilities={"character.read"}
            ),
            context=context(),
        )


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
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [turn("", ("call-1", tool_name, arguments), finish_reason="unknown")]
            )
        ),
        registry,
    )
    exposed = (
        []
        if tool_name == "submit_evaluation"
        else registry.for_agent(agent_id="设定", capabilities={"character.read"})
    )

    with pytest.raises(RuntimeError, match=error_code):
        await runtime.run(
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
    runtime = make_agent_runtime(
        ModelRuntime(
            ScriptedProvider(
                [
                    turn(
                        "",
                        ("call-1", "get_novel_info", {}),
                        ("call-2", "get_character_detail", {}),
                    )
                ]
            )
        ),
        registry,
    )

    with pytest.raises(RuntimeError, match="MODEL_TOOL_ARGUMENTS_INVALID"):
        await runtime.run(
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
    with pytest.raises(RuntimeError, match="供应商不可用"):
        await failing.run(
            messages=[{"role": "user", "content": "失败"}],
            exposed_tools=[],
            context=context(),
        )

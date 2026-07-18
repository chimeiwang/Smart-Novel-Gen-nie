import pytest
from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.runtime.agent_runner import AgentRunner, AgentRunRequest
from inkforge_agents.runtime.agent_runtime import AgentRuntime
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_agents.short_story.story_graph import extract_complete_short_story
from inkforge_agents.tools.registry import ToolContext, build_default_registry
from inkforge_contracts import count_short_story_text_length


@pytest.mark.asyncio
async def test_fake_provider_returns_deterministic_text_tool_call_and_usage() -> None:
    provider = FakeModelProvider()
    request = ModelTurnRequest(
        messages=[{"role": "user", "content": "请测试工具"}],
        tools=[
            {
                "name": "submit_evaluation",
                "description": "提交复审结论",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        maxOutputTokens=256,
    )

    first = await provider.complete_turn(request)
    second = await provider.complete_turn(request)

    assert first == second
    assert first.content == "模拟模型已完成本轮处理。"
    assert first.toolCalls[0].name == "submit_evaluation"
    assert first.finishReason == "tool_calls"
    assert first.rawFinishReason == "tool_calls"
    assert first.usage.totalTokens == first.usage.promptTokens + first.usage.completionTokens
    assert provider.billable is False


@pytest.mark.asyncio
async def test_fake_provider_without_tools_returns_full_visible_text() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "正文" * 10_000}],
            tools=[],
            maxOutputTokens=256,
        )
    )

    assert result.toolCalls == []
    assert result.finishReason == "stop"
    assert result.rawFinishReason == "stop"
    assert result.content == "模拟模型已完成本轮处理。"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_word_count", [6000, 80000])
async def test_fake_provider_returns_exact_length_short_story_with_visible_tail(
    target_word_count: int,
) -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[
                {
                    "role": "system",
                    "content": "当前执行契约：operation=write_short_story，mode=primary。",
                },
                {
                    "role": "user",
                    "content": (
                        "生成完整中短篇正文；权威上下文："
                        f'{{"targetTotalWordCount":{target_word_count}}}'
                    ),
                },
            ],
            tools=[],
            maxOutputTokens=256,
        )
    )

    assert result.toolCalls == []
    assert result.finishReason == "stop"
    assert result.content.startswith("ARTIFACT_OUTPUT_START\n")
    assert result.content.endswith("\nARTIFACT_OUTPUT_END")
    assert "【模拟整稿尾部】" in result.content
    actual = count_short_story_text_length(
        extract_complete_short_story(result.content)
    )
    assert actual == target_word_count


@pytest.mark.asyncio
async def test_fake_provider_finishes_after_tool_result() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[
                {"role": "user", "content": "请测试工具"},
                {
                    "role": "tool",
                    "name": "get_novel_info",
                    "toolCallId": "fake-tool-call-1",
                    "content": "{}",
                },
            ],
            tools=[
                {
                    "name": "get_novel_info",
                    "description": "读取作品信息",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            maxOutputTokens=256,
        )
    )

    assert result.toolCalls == []
    assert result.finishReason == "stop"


@pytest.mark.asyncio
async def test_fake_provider_can_trigger_one_e2e_editor_rewrite() -> None:
    class CapturingFakeProvider(FakeModelProvider):
        def __init__(self) -> None:
            self.requests: list[ModelTurnRequest] = []

        async def complete_turn(self, request: ModelTurnRequest):
            self.requests.append(request)
            return await super().complete_turn(request)

    provider = CapturingFakeProvider()
    registry = build_default_registry()
    runner = AgentRunner(
        AgentRuntime(
            ModelRuntime(provider),
            registry,
            max_output_tokens=16_384,
        ),
        registry,
    )

    async def review(count: int, agent_id: str, instruction: str):
        result = await runner.run(
            AgentRunRequest(
                agentId=agent_id,
                executionMode="reviewer",
                operationKind="write_short_story",
                userMessage="审核当前完整中短篇正文",
                contextMessages=[
                    (
                        "中短篇整稿权威上下文："
                        '{"originalInspiration":"[E2E_AUTO_REWRITE_ONCE] 守夜人敲钟"}'
                    ),
                    (
                        "当前待审核草案权威内容："
                        f'{{"payload":{{"metadata":{{"automaticRewriteCount":{count}}}}}}}'
                    ),
                ],
                executionInstructions=[instruction],
                toolContext=ToolContext(
                    userId="user-1",
                    novelId="novel-1",
                    taskId="task-1",
                    runId="run-1",
                    agentId=agent_id,
                ),
                maxIterations=1,
            )
        )
        return result, provider.requests[-1]

    first_editor, first_request = await review(
        0,
        "编辑",
        "这是中短篇完整正文的全稿审核，只检查结构、节奏、高潮和结局兑现。",
    )
    validator, _ = await review(
        0,
        "校验",
        "这是中短篇完整正文的独立全稿校验，只检查人物、规则、时间线、因果和伏笔。",
    )
    second_editor, _ = await review(
        1,
        "编辑",
        "这是中短篇完整正文的全稿审核，只检查结构、节奏、高潮和结局兑现。",
    )

    runtime_message = "\n".join(message.content for message in first_request.messages)
    assert "[E2E_AUTO_REWRITE_ONCE]" in runtime_message
    assert '"automaticRewriteCount":0' in runtime_message
    assert "operation=write_short_story" in runtime_message
    assert "mode=reviewer" in runtime_message
    assert "结构、节奏、高潮和结局兑现" in runtime_message
    assert first_editor.controlEvents[0] == {
        "type": "submit_evaluation",
        "artifactKey": "fake-artifact",
        "verdict": "revise",
        "summary": "模拟编辑要求执行一次自动完整返工。",
        "requiredChanges": "强化开场危机，并保持结局兑现不变。",
    }
    assert validator.controlEvents[0]["verdict"] == "pass"
    assert second_editor.controlEvents[0]["verdict"] == "pass"


@pytest.mark.asyncio
async def test_fake_provider_creates_valid_chapter_artifact_call() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "写一章正文"}],
            tools=[
                {
                    "name": "begin_artifact_output",
                    "description": "声明正文草案",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            maxOutputTokens=256,
        )
    )

    assert result.toolCalls[0].name == "begin_artifact_output"
    assert result.toolCalls[0].arguments["kind"] == "chapter_draft"
    assert "ARTIFACT_OUTPUT_START" in result.content
    assert "ARTIFACT_OUTPUT_END" in result.content


@pytest.mark.asyncio
async def test_fake_provider_returns_complete_quality_report_from_tool_scope() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[
                {
                    "role": "user",
                    "name": "project_context",
                    "content": "只读章节资料，不依赖 system 角色触发",
                }
            ],
            tools=[
                {
                    "name": "submit_quality_report",
                    "description": "提交一致性终检",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            maxOutputTokens=256,
        )
    )

    assert result.toolCalls[0].name == "submit_quality_report"
    assert result.toolCalls[0].arguments == {
        "scores": {
            "characterConsistency": 90.0,
            "worldRuleConsistency": 90.0,
            "timelineConsistency": 90.0,
            "causalityConsistency": 90.0,
            "foreshadowingConsistency": 90.0,
        },
        "qualityGate": "pass",
        "issues": [],
        "report": "一致性终检未发现冲突。",
        "rewriteBrief": None,
    }


@pytest.mark.asyncio
async def test_fake_provider_submits_valid_full_short_outline() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[
                {
                    "role": "system",
                    "content": "当前执行契约：operation=develop_short_outline，mode=primary。",
                },
                {"role": "user", "content": "城市每天忘记一个人"},
            ],
            tools=[
                {
                    "name": "submit_short_story_outline",
                    "description": "提交中短篇大纲",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            maxOutputTokens=256,
        )
    )

    arguments = result.toolCalls[0].arguments
    assert result.toolCalls[0].name == "submit_short_story_outline"
    assert arguments["mode"] == "full"
    assert "originalInspiration" not in arguments
    assert all("id" not in section for section in arguments["sections"])


@pytest.mark.asyncio
async def test_fake_provider_submits_patch_against_authoritative_revision_and_id() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[
                {
                    "role": "system",
                    "content": "当前执行契约：operation=develop_short_outline，mode=reviser。",
                },
                {
                    "role": "user",
                    "content": (
                        '当前返工草案权威内容：{"revision":7,"payload":'
                        '{"sections":[{"id":"short-section-authority","title":"开端",'
                        '"events":"旧事件"}]}}'
                    ),
                },
            ],
            tools=[
                {
                    "name": "submit_short_story_outline",
                    "description": "提交中短篇大纲",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            maxOutputTokens=256,
        )
    )

    arguments = result.toolCalls[0].arguments
    assert arguments["mode"] == "patch"
    assert arguments["sourceRevision"] == 7
    assert arguments["sectionOperations"][0]["sectionId"] == "short-section-authority"

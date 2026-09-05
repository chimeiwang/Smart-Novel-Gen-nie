import json

import pytest
from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_agents.providers.fake import FakeModelProvider
from inkforge_agents.runtime.model_policy import LEGACY_PROVIDER_DEFAULT
from inkforge_contracts import ChapterDraftOutput


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
        policy=LEGACY_PROVIDER_DEFAULT,
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
            policy=LEGACY_PROVIDER_DEFAULT,
        )
    )

    assert result.toolCalls == []
    assert result.finishReason == "stop"
    assert result.rawFinishReason == "stop"
    assert result.content == "模拟模型已完成本轮处理。"


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
            policy=LEGACY_PROVIDER_DEFAULT,
        )
    )

    assert result.toolCalls == []
    assert result.finishReason == "stop"


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
            policy=LEGACY_PROVIDER_DEFAULT,
        )
    )

    assert result.toolCalls[0].name == "begin_artifact_output"
    assert result.toolCalls[0].arguments["kind"] == "chapter_draft"
    assert result.toolCalls[0].arguments["content"] == (
        "这是模拟模型生成的完整章节正文，用于验证待审核草案流程。"
    )


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
            policy=LEGACY_PROVIDER_DEFAULT,
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
async def test_fake_provider_returns_semantic_chapter_plan_without_system_fields() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "根据冻结证据规划章节"}],
            tools=[],
            maxOutputTokens=2000,
            policy=LEGACY_PROVIDER_DEFAULT,
            structuredOutput={
                "route": "chat_json_output_v1",
                "name": "output_beat_plan_v1",
                "jsonSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "chapterGoal": {"type": "string"},
                        "sceneBeats": {"type": "array"},
                    },
                },
            },
        )
    )
    output = result.structuredOutput
    assert output is not None
    assert output["title"] == "隔离章节规划"
    assert output["chapterGoal"]
    assert isinstance(output["sceneBeats"], list)
    assert len(output["sceneBeats"]) == 2
    assert all(isinstance(beat, dict) and beat["goal"] for beat in output["sceneBeats"])
    assert "beatCount" not in output
    assert "contentSha256" not in output
    assert all("order" not in beat for beat in output["sceneBeats"] if isinstance(beat, dict))
    assert result.toolCalls == []
    assert result.finishReason == "stop"
    assert result.usage.totalTokens == result.usage.promptTokens + result.usage.completionTokens


@pytest.mark.asyncio
async def test_fake_provider_returns_full_chapter_without_system_fields() -> None:
    result = await FakeModelProvider().complete_turn(
        ModelTurnRequest(
            messages=[{"role": "user", "content": "依据冻结资料写完整正文"}],
            tools=[],
            maxOutputTokens=8000,
            policy=LEGACY_PROVIDER_DEFAULT,
            structuredOutput={
                "route": "chat_json_output_v1",
                "name": "output_chapter_draft_v1",
                "jsonSchema": ChapterDraftOutput.model_json_schema(),
            },
        )
    )
    output = ChapterDraftOutput.model_validate(result.structuredOutput)
    assert output.content == (
        "林舟把旧行动线索放在桌上，逐一核对。\n\n窗外雨声渐紧，他终于作出选择。"
    )
    assert output.summary
    assert result.structuredOutput is not None
    assert set(result.structuredOutput) == {"summary", "content"}
    assert result.toolCalls == []
    assert result.finishReason == "stop"


@pytest.mark.asyncio
async def test_fake_provider_returns_distinct_review_and_outline_outputs() -> None:
    from inkforge_agents.providers.fake import (
        FAKE_CHAPTER_REVIEW_REPORT,
        FAKE_OUTLINE_SELECTION_REPLACEMENT,
    )
    from inkforge_contracts import ChapterReviewOutput, OutlineSelectionOutput

    outputs = []
    for name, schema in (
        ("output_chapter_review_text_v1", ChapterReviewOutput.model_json_schema()),
        ("output_outline_selection_replacement_v1", OutlineSelectionOutput.model_json_schema()),
    ):
        result = await FakeModelProvider().complete_turn(
            ModelTurnRequest(
                messages=[{"role": "user", "content": "隔离测试"}],
                tools=[],
                maxOutputTokens=12_000,
                policy=LEGACY_PROVIDER_DEFAULT,
                structuredOutput={
                    "route": "chat_json_output_v1",
                    "name": name,
                    "jsonSchema": schema,
                },
            )
        )
        outputs.append(result.structuredOutput)
    assert outputs == [
        {"report": FAKE_CHAPTER_REVIEW_REPORT},
        {"replacement": FAKE_OUTLINE_SELECTION_REPLACEMENT},
    ]


@pytest.mark.asyncio
async def test_fake_intent_marker_is_limited_by_frozen_available_operations() -> None:
    def request(operations: list[str]) -> ModelTurnRequest:
        envelope = {
            "input": {
                "userInstruction": "【隔离意图:review_chapter】",
                "clarifications": [],
            },
            "evidenceBundle": {
                "items": [
                    {
                        "resourceType": "intent_context",
                        "metadata": {"role": "intent_context"},
                        "contentJson": {
                            "availableOperations": [
                                {"operation": operation, "description": f"说明:{operation}"}
                                for operation in operations
                            ]
                        },
                    }
                ]
            },
        }
        return ModelTurnRequest(
            messages=[{"role": "user", "content": json.dumps(envelope)}],
            tools=[],
            maxOutputTokens=1000,
            policy=LEGACY_PROVIDER_DEFAULT,
            structuredOutput={
                "route": "chat_json_output_v1",
                "name": "output_proposed_command_v1",
                "jsonSchema": {
                    "type": "object",
                    "properties": {
                        "workflow": {},
                        "operation": {},
                        "confidence": {},
                        "clarification": {},
                    },
                },
            },
        )

    unavailable = await FakeModelProvider().complete_turn(request(["answer_question"]))
    available = await FakeModelProvider().complete_turn(request(["review_chapter"]))
    assert unavailable.structuredOutput["operation"] is None
    assert unavailable.structuredOutput["clarification"] is not None
    assert available.structuredOutput["operation"] == "review_chapter"
    assert available.structuredOutput["clarification"] is None

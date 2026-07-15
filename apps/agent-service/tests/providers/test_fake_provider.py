import pytest
from inkforge_agents.providers.base import ModelTurnRequest
from inkforge_agents.providers.fake import FakeModelProvider


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

import pytest
from inkforge_agents.tools.registry import ToolContext, build_default_registry


def test_structured_update_tools_publish_safe_write_contract_in_json_schema() -> None:
    registry = build_default_registry()

    for name in ("propose_updates", "append_update_batch"):
        tool = registry.require(name).as_model_tool()
        description = tool.parameters["properties"]["updates"]["description"]
        for expected in (
            "clientRequestId",
            "16..256",
            "expectedUpdatedAt",
            "权威上下文",
            "原样携带",
            "不得臆造或刷新",
            "重试或返工时保持不变",
            "停止并说明",
        ):
            assert expected in description


@pytest.mark.asyncio
async def test_character_proposal_template_repeats_safe_write_contract() -> None:
    tool = build_default_registry().require("propose_update_character")
    assert tool.handler is not None

    result = await tool.handler(
        {"character_name": "林舟"},
        ToolContext(
            userId="user-1",
            novelId="novel-1",
            taskId="task-1",
            runId="run-1",
            agentId="设定",
        ),
    )

    instruction = result["instruction"]
    assert "clientRequestId" in instruction
    assert "expectedUpdatedAt" in instruction
    assert "不得臆造或刷新" in instruction

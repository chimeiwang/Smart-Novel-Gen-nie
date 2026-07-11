import pytest
from inkforge_agents.tools.registry import ToolContext, build_default_registry


def test_registry_contains_migrated_read_proposal_and_control_tools() -> None:
    registry = build_default_registry()
    names = {tool.name for tool in registry.all()}

    assert {
        "get_novel_info",
        "get_character_detail",
        "get_active_review_artifact",
        "propose_update_character",
        "propose_updates",
        "append_outline_tree",
        "begin_artifact_output",
        "submit_evaluation",
    } <= names


@pytest.mark.asyncio
async def test_registry_refuses_control_tool_direct_execution() -> None:
    registry = build_default_registry()
    context = ToolContext(
        userId="user-1",
        novelId="novel-1",
        taskId="task-1",
        runId="run-1",
        agentId="校验",
    )

    with pytest.raises(ValueError, match="控制工具只能由智能体运行时捕获"):
        await registry.execute(
            "submit_evaluation",
            {
                "artifactKey": "task-1:write_chapter",
                "verdict": "pass",
                "summary": "通过",
            },
            context,
        )

from inkforge_agents.definitions.agents import AGENT_DEFINITIONS
from inkforge_agents.tools.registry import build_default_registry


def names_for(agent_id: str) -> set[str]:
    registry = build_default_registry()
    definition = AGENT_DEFINITIONS[agent_id]
    return {
        tool.name
        for tool in registry.for_agent(
            agent_id=agent_id,
            capabilities=definition.toolCapabilities,
        )
    }


def test_control_tool_permissions_match_agent_responsibilities() -> None:
    assert "append_outline_tree" in names_for("剧情")
    assert "append_outline_tree" not in names_for("设定")
    assert "begin_artifact_output" in names_for("写作")
    assert "begin_artifact_output" not in names_for("编辑")
    assert "submit_evaluation" in names_for("编辑")
    assert "submit_evaluation" in names_for("校验")
    assert "submit_evaluation" not in names_for("写作")


def test_agent_capability_and_tool_agent_whitelist_are_both_required() -> None:
    registry = build_default_registry()
    tools = registry.for_agent(
        agent_id="设定",
        capabilities={"control.builder"},
    )

    assert "append_outline_tree" not in {tool.name for tool in tools}

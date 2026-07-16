from inkforge_agents.definitions.capabilities import AGENT_CAPABILITIES


def test_only_validator_agent_has_quality_control_capability() -> None:
    assert "control.quality" in AGENT_CAPABILITIES["校验"]
    assert "control.quality" not in AGENT_CAPABILITIES["编辑"]

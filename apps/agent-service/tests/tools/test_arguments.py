import pytest
from inkforge_agents.tools.registry import build_default_registry
from pydantic import ValidationError


def test_tool_arguments_are_strictly_validated_without_truncation() -> None:
    registry = build_default_registry()
    tool = registry.require("get_character_detail")

    with pytest.raises(ValidationError):
        tool.validate({})
    with pytest.raises(ValidationError):
        tool.validate({"character_name": "角色", "unexpected": True})

    long_name = "长" * 20_000
    assert tool.validate({"character_name": long_name})["character_name"] == long_name


def test_evaluation_arguments_reject_invalid_verdict() -> None:
    tool = build_default_registry().require("submit_evaluation")

    with pytest.raises(ValidationError):
        tool.validate(
            {
                "artifactKey": "task-1:write_chapter",
                "verdict": "maybe",
                "summary": "不确定",
            }
        )


def test_evaluation_artifact_key_is_optional() -> None:
    tool = build_default_registry().require("submit_evaluation")

    validated = tool.validate({"verdict": "pass", "summary": "审核通过"})

    assert "artifactKey" not in validated

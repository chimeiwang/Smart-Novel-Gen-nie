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


def _evaluation(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "verdict": "revise",
        "summary": "需要修改",
        "revisionMode": "patch",
        "patches": [{"kind": "text_replace", "find": "甲", "replace": "乙"}],
    }
    value.update(overrides)
    return value


def test_evaluation_patch_requires_strict_non_empty_patches() -> None:
    tool = build_default_registry().require("submit_evaluation")

    with pytest.raises(ValidationError):
        tool.validate(_evaluation(patches=[]))
    with pytest.raises(ValidationError):
        tool.validate(_evaluation(patches=[{"kind": "text_replace", "find": "", "replace": "乙"}]))
    with pytest.raises(ValidationError):
        tool.validate(
            _evaluation(
                patches=[
                    {
                        "kind": "text_replace",
                        "find": "甲",
                        "replace": "乙",
                        "extra": True,
                    }
                ]
            )
        )


def test_evaluation_patch_accepts_one_to_twenty_and_rejects_twenty_one() -> None:
    tool = build_default_registry().require("submit_evaluation")
    patch = {"kind": "text_replace", "find": "甲", "replace": "乙"}

    assert len(tool.validate(_evaluation(patches=[patch]))["patches"]) == 1
    assert len(tool.validate(_evaluation(patches=[patch] * 20))["patches"]) == 20
    with pytest.raises(ValidationError):
        tool.validate(_evaluation(patches=[patch] * 21))


@pytest.mark.parametrize(
    "value",
    [
        {"verdict": "pass", "summary": "通过", "revisionMode": "rewrite"},
        {"verdict": "pass", "summary": "通过", "patches": []},
        {"verdict": "block", "summary": "阻断", "revisionMode": "patch"},
        {
            "verdict": "block",
            "summary": "阻断",
            "patches": [{"kind": "text_replace", "find": "甲", "replace": "乙"}],
        },
        {
            "verdict": "revise",
            "summary": "修改",
            "patches": [{"kind": "text_replace", "find": "甲", "replace": "乙"}],
        },
        {"verdict": "revise", "summary": "修改", "revisionMode": "rewrite", "patches": []},
    ],
)
def test_evaluation_rejects_invalid_revision_combinations(value: dict[str, object]) -> None:
    tool = build_default_registry().require("submit_evaluation")

    with pytest.raises(ValidationError):
        tool.validate(value)

import jsonschema_rs
import pytest
from inkforge_agents.tools.control import artifact_model_schema_for_operation
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


def test_default_registry_has_only_quality_report_strict_tool() -> None:
    registry = build_default_registry()

    assert {tool.name for tool in registry.all() if tool.as_model_tool().strict} == {
        "submit_quality_report"
    }


def test_quality_tool_validation_keeps_local_length_and_count_limits() -> None:
    tool = build_default_registry().require("submit_quality_report")
    scores = {
        "characterConsistency": 90,
        "worldRuleConsistency": 90,
        "timelineConsistency": 90,
        "causalityConsistency": 90,
        "foreshadowingConsistency": 90,
    }
    issue = {
        "dimension": "character",
        "severity": "warning",
        "message": "长" * 501,
        "evidence": "证据",
        "suggestion": "建议",
    }

    with pytest.raises(ValidationError):
        tool.validate(
            {
                "scores": scores,
                "qualityGate": "pass",
                "issues": [issue],
                "report": "报告",
            }
        )

    valid_issue = {**issue, "message": "消息"}
    with pytest.raises(ValidationError):
        tool.validate(
            {
                "scores": scores,
                "qualityGate": "pass",
                "issues": [valid_issue] * 101,
                "report": "报告",
            }
        )


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


@pytest.mark.parametrize(
    ("tool_name", "arguments", "valid", "error_code"),
    [
        (
            "put_update_item_text_block",
            {"artifactKey": "a", "section": "x", "field": "y"},
            False,
            "item_target_required",
        ),
        (
            "put_update_item_text_block",
            {"artifactKey": "a", "section": "x", "field": "y", "targetId": None},
            False,
            "item_target_required",
        ),
        (
            "put_update_item_text_block",
            {"artifactKey": "a", "section": "x", "field": "y", "targetName": "角色"},
            True,
            None,
        ),
        ("show_review_artifact", {}, False, "artifact_locator_required"),
        ("show_review_artifact", {"artifactId": None}, False, "artifact_locator_required"),
        ("show_review_artifact", {"artifactId": "草案-1"}, True, None),
    ],
)
def test_定位工具_schema_与本地错误码一致(
    tool_name: str, arguments: dict[str, object], valid: bool, error_code: str | None
) -> None:
    tool = build_default_registry().require(tool_name)
    assert jsonschema_rs.is_valid(tool.as_model_tool().parameters, arguments) is valid
    if valid:
        tool.validate(arguments)
    else:
        with pytest.raises(ValidationError) as failure:
            tool.validate(arguments)
        assert failure.value.errors()[0]["type"] == error_code


@pytest.mark.parametrize(
    ("arguments", "valid"),
    [
        ({"verdict": "pass", "summary": "通过"}, True),
        ({"verdict": "block", "summary": "阻断", "patches": None}, True),
        ({"verdict": "pass", "summary": "通过", "revisionMode": "patch"}, False),
        ({"verdict": "revise", "summary": "修改"}, False),
        (
            {
                "verdict": "revise",
                "summary": "修改",
                "revisionMode": "patch",
                "patches": [{"kind": "text_replace", "find": "甲", "replace": "乙"}],
            },
            True,
        ),
        ({"verdict": "revise", "summary": "修改", "revisionMode": "patch", "patches": []}, False),
        ({"verdict": "revise", "summary": "修改", "revisionMode": "rewrite"}, True),
        ({"verdict": "revise", "summary": "修改", "revisionMode": "rewrite", "patches": []}, False),
    ],
)
def test_复审结论_schema_与本地组合校验一致(arguments: dict[str, object], valid: bool) -> None:
    tool = build_default_registry().require("submit_evaluation")
    assert jsonschema_rs.is_valid(tool.as_model_tool().parameters, arguments) is valid
    if valid:
        tool.validate(arguments)
    else:
        with pytest.raises(ValidationError):
            tool.validate(arguments)


def test_规划输入派生数量但历史参数严格校验() -> None:
    tool = build_default_registry().require("submit_beat_plan")
    model_input = {
        "title": "第一章",
        "summary": "章节摘要",
        "chapterGoal": "达成目标",
        "sceneBeats": [{"goal": "进入城门"}, {"goal": "找到线索"}],
    }
    assert "beatCount" not in tool.as_model_tool().parameters["properties"]
    assert tool.validate_model_arguments(model_input)["beatCount"] == 2
    with pytest.raises(ValidationError):
        tool.validate_model_arguments({**model_input, "beatCount": 7})
    assert tool.validate({**model_input, "beatCount": 2})["beatCount"] == 2
    with pytest.raises(ValidationError):
        tool.validate({**model_input, "beatCount": 7})


@pytest.mark.parametrize("operation_kind", ["write_chapter", "rewrite_scene"])
def test_普通正文_schema_只接受完整正文(operation_kind: str) -> None:
    schema = artifact_model_schema_for_operation(operation_kind)
    assert schema is not None
    ordinary = {"kind": "chapter_draft", "summary": "草案", "content": "完整正文"}
    assert jsonschema_rs.is_valid(schema, ordinary)
    assert not jsonschema_rs.is_valid(schema, {"kind": "chapter_draft", "summary": "草案"})
    assert not jsonschema_rs.is_valid(schema, {**ordinary, "replacement": "片段"})


@pytest.mark.parametrize(
    ("operation_kind", "kind", "resource_type"),
    [
        ("rewrite_chapter_selection", "chapter_draft", "chapter_content"),
        ("rewrite_outline_selection", "outline_draft", "outline_node_content"),
    ],
)
def test_选区_schema_要求冻结身份且排斥完整正文(
    operation_kind: str, kind: str, resource_type: str
) -> None:
    schema = artifact_model_schema_for_operation(operation_kind)
    assert schema is not None
    selection = {
        "kind": kind,
        "summary": "改写",
        "operation": operation_kind,
        "resourceType": resource_type,
        "resourceId": "source-1",
        "baseUpdatedAt": "2026-09-30T00:00:00Z",
        "baseContentHash": "a" * 64,
        "selectionStart": 0,
        "selectionEnd": 2,
        "selectedTextHash": "b" * 64,
        "replacement": "新内容",
    }
    assert jsonschema_rs.is_valid(schema, selection)
    assert not jsonschema_rs.is_valid(
        schema, {key: value for key, value in selection.items() if key != "selectedTextHash"}
    )
    assert not jsonschema_rs.is_valid(schema, {**selection, "content": "整章"})
    assert not jsonschema_rs.is_valid(
        schema,
        {**selection, "resourceType": "chapter_content"}
        if operation_kind == "rewrite_outline_selection"
        else {**selection, "resourceType": "outline_content"},
    )

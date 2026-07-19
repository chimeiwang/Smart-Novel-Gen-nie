from __future__ import annotations

import pytest
from inkforge_agents.tools.registry import build_default_registry
from pydantic import ValidationError


def _full_payload() -> dict[str, object]:
    return {
        "mode": "full",
        "corePremise": "一个人试图对抗城市的集体遗忘。",
        "anchors": {"mustKeep": ["结局兑现"], "confirmed": [], "avoid": []},
        "sections": [
            {"title": "失踪", "events": "所有人忘记了一名记者。"},
            {"title": "追索", "events": "主角追查记忆规则。"},
        ],
        "changeSummary": "形成首版完整大纲。",
    }


def test_short_outline_tool_exposes_object_json_schema() -> None:
    tool = build_default_registry().require("submit_short_story_outline")

    parameters = tool.as_model_tool().parameters

    assert parameters["type"] == "object"
    assert parameters["discriminator"] == {
        "mapping": {
            "full": "#/$defs/ShortOutlineFullSubmission",
            "patch": "#/$defs/ShortOutlinePatchSubmission",
        },
        "propertyName": "mode",
    }


def test_short_outline_tool_strictly_discriminates_full_and_patch() -> None:
    tool = build_default_registry().require("submit_short_story_outline")

    full = tool.validate(_full_payload())
    patch = tool.validate(
        {
            "mode": "patch",
            "sourceRevision": 7,
            "sectionOperations": [
                {"operation": "update", "sectionId": "section-1", "events": "新事件"}
            ],
            "changeSummary": "只修改第一节。",
        }
    )

    assert full["mode"] == "full"
    assert patch["mode"] == "patch"
    assert patch["sourceRevision"] == 7


@pytest.mark.parametrize(
    "extra",
    [
        {"originalInspiration": "模型伪造灵感"},
        {"artifactKey": "model-key"},
        {"sectionCount": 8},
        {"chapterMapping": {"第一章": "第一节"}},
    ],
)
def test_full_submission_rejects_authority_fields_and_fixed_structure_metadata(
    extra: dict[str, object],
) -> None:
    tool = build_default_registry().require("submit_short_story_outline")
    payload = {**_full_payload(), **extra}

    with pytest.raises(ValidationError):
        tool.validate(payload)


@pytest.mark.parametrize(
    "section_extra",
    [
        {"id": "model-section"},
        {"targetWordCount": 2000},
        {"chapterId": "chapter-1"},
    ],
)
def test_full_sections_reject_model_ids_word_counts_and_chapter_mapping(
    section_extra: dict[str, object],
) -> None:
    tool = build_default_registry().require("submit_short_story_outline")
    payload = _full_payload()
    payload["sections"] = [
        {"title": "失踪", "events": "事件", **section_extra}
    ]

    with pytest.raises(ValidationError):
        tool.validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "patch", "sourceRevision": 1, "changeSummary": "空修改"},
        {
            "mode": "patch",
            "sourceRevision": 1,
            "sectionOperations": [
                {"operation": "update", "sectionId": "section-1"}
            ],
            "changeSummary": "更新缺少字段",
        },
        {
            "mode": "patch",
            "sourceRevision": 1,
            "sectionOperations": [
                {
                    "operation": "insert",
                    "id": "model-id",
                    "title": "新节",
                    "events": "事件",
                }
            ],
            "changeSummary": "模型不能指定新 ID",
        },
    ],
)
def test_patch_requires_candidate_change_and_rejects_invalid_operations(
    payload: dict[str, object],
) -> None:
    tool = build_default_registry().require("submit_short_story_outline")

    with pytest.raises(ValidationError):
        tool.validate(payload)

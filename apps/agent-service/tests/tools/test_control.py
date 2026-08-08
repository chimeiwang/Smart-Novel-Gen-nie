from __future__ import annotations

import pytest
from inkforge_agents.tools.control import (
    BeatPlanArgs,
    BeginArtifactArgs,
    QualityReportArgs,
)
from inkforge_contracts import ConsistencyQualityReport
from pydantic import ValidationError


def test_quality_tool_reuses_shared_report_contract() -> None:
    assert issubclass(QualityReportArgs, ConsistencyQualityReport)
    assert QualityReportArgs.model_fields.keys() == ConsistencyQualityReport.model_fields.keys()


def test_begin_artifact_requires_complete_content_in_tool_arguments() -> None:
    artifact = BeginArtifactArgs.model_validate(
        {
            "kind": "chapter_draft",
            "summary": "正文草案",
            "content": "完整章节正文",
        }
    )

    assert artifact.content == "完整章节正文"
    assert "content" in BeginArtifactArgs.model_json_schema()["required"]


@pytest.mark.parametrize("content", ["", " \r\n\t"])
def test_begin_artifact_rejects_empty_or_whitespace_content(content: str) -> None:
    with pytest.raises(ValidationError) as exc_info:
        BeginArtifactArgs.model_validate(
            {
                "kind": "chapter_draft",
                "summary": "正文草案",
                "content": content,
            }
        )

    assert exc_info.value.errors()[0]["loc"] == ("content",)


def _valid_beat_plan_payload() -> dict[str, object]:
    return {
        "title": "第一章",
        "beatCount": 1,
        "summary": "主角首次面对危机。",
        "chapterGoal": "让主角决定主动调查。",
        "sceneBeats": [{"goal": "发现关键线索。"}],
    }


def test_beat_plan_scene_uses_strict_normalized_contract() -> None:
    beat_plan = BeatPlanArgs.model_validate(_valid_beat_plan_payload())

    assert beat_plan.model_dump() == {
        "title": "第一章",
        "beatCount": 1,
        "summary": "主角首次面对危机。",
        "artifactKey": None,
        "reviewerAgent": None,
        "submitForReview": None,
        "chapterGoal": "让主角决定主动调查。",
        "mainPlotConnection": None,
        "chapterAcceptanceCriteria": None,
        "totalEstimatedWords": None,
        "sceneBeats": [
            {
                "order": None,
                "goal": "发现关键线索。",
                "conflict": None,
                "characters": [],
                "foreshadowingRefs": None,
                "estimatedWords": None,
                "acceptanceCriteria": None,
            }
        ],
    }


def test_beat_plan_rejects_legacy_scene_goal_field() -> None:
    payload = _valid_beat_plan_payload()
    payload["sceneBeats"] = [
        {"goal": "发现关键线索。", "sceneGoal": "旧场景目标。"}
    ]

    with pytest.raises(ValidationError) as exc_info:
        BeatPlanArgs.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == ("sceneBeats", 0, "sceneGoal")


def test_beat_plan_rejects_string_characters() -> None:
    payload = _valid_beat_plan_payload()
    payload["sceneBeats"] = [
        {"goal": "发现关键线索。", "characters": "主角"}
    ]

    with pytest.raises(ValidationError) as exc_info:
        BeatPlanArgs.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == ("sceneBeats", 0, "characters")


@pytest.mark.parametrize(
    ("location", "value"),
    [
        (("beatCount",), True),
        (("beatCount",), "1"),
        (("totalEstimatedWords",), True),
        (("totalEstimatedWords",), "1000"),
        (("sceneBeats", 0, "order"), True),
        (("sceneBeats", 0, "order"), "1"),
        (("sceneBeats", 0, "estimatedWords"), False),
        (("sceneBeats", 0, "estimatedWords"), "100"),
    ],
)
def test_beat_plan_rejects_non_strict_integers(
    location: tuple[str | int, ...], value: object
) -> None:
    payload = _valid_beat_plan_payload()
    if len(location) == 1:
        payload[location[0]] = value
    else:
        scene = payload["sceneBeats"]
        assert isinstance(scene, list)
        scene[0][location[-1]] = value

    with pytest.raises(ValidationError) as exc_info:
        BeatPlanArgs.model_validate(payload)

    assert exc_info.value.errors()[0]["loc"] == location


def test_beat_plan_schema_forbids_extra_fields_at_both_levels() -> None:
    schema = BeatPlanArgs.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["properties"]["sceneBeats"]["items"] == {
        "$ref": "#/$defs/BeatPlanSceneArgs"
    }
    assert schema["$defs"]["BeatPlanSceneArgs"]["additionalProperties"] is False


@pytest.mark.parametrize("field", ["chapterGoal", "sceneBeats"])
def test_beat_plan_requires_chapter_goal_and_scenes(field: str) -> None:
    payload = _valid_beat_plan_payload()
    del payload[field]

    with pytest.raises(ValidationError):
        BeatPlanArgs.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chapterGoal", ""),
        ("sceneBeats", []),
        ("beatCount", 2),
    ],
)
def test_beat_plan_rejects_incomplete_or_inconsistent_plan(
    field: str, value: object
) -> None:
    payload = _valid_beat_plan_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        BeatPlanArgs.model_validate(payload)

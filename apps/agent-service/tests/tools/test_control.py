from __future__ import annotations

import pytest
from inkforge_agents.tools.control import BeatPlanArgs, QualityReportArgs
from inkforge_contracts import ConsistencyQualityReport
from pydantic import ValidationError


def test_quality_tool_reuses_shared_report_contract() -> None:
    assert issubclass(QualityReportArgs, ConsistencyQualityReport)
    assert QualityReportArgs.model_fields.keys() == ConsistencyQualityReport.model_fields.keys()


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


def test_beat_plan_rejects_legacy_scene_shape() -> None:
    payload = _valid_beat_plan_payload()
    payload["sceneBeats"] = [
        {"sceneGoal": "发现关键线索。", "characters": "主角"}
    ]

    with pytest.raises(ValidationError):
        BeatPlanArgs.model_validate(payload)


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

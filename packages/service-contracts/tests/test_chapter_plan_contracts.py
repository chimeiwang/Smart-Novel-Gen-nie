from __future__ import annotations

from copy import deepcopy

import pytest
from inkforge_contracts.execution import (
    ChapterPlanInput,
    ChapterPlanOutput,
    ChapterPlanResult,
    canonical_execution_sha256,
    materialize_chapter_plan_output,
)
from pydantic import ValidationError


def plan() -> dict[str, object]:
    return {
        "title": "  午夜的抉择😀  ",
        "summary": "主角发现同伴隐瞒线索。\n他决定独自核实。",
        "chapterGoal": "找到失踪同伴的真实去向",
        "sceneBeats": [
            {"goal": "发现字条", "characters": ["林舟"], "estimatedWords": 800},
            {"goal": "向守门人求证", "conflict": "守门人拒绝透露行踪"},
        ],
        "totalEstimatedWords": 1600,
    }


def test_plan_preserves_text_and_derives_count_order_and_canonical_hash() -> None:
    output = plan()
    assert ChapterPlanOutput.model_validate(output).title == output["title"]
    result = materialize_chapter_plan_output(output)
    assert result["title"] == output["title"]
    assert result["beatCount"] == 2
    assert [scene["order"] for scene in result["sceneBeats"]] == [1, 2]
    expected = {key: value for key, value in result.items() if key != "contentSha256"}
    assert result["contentSha256"] == canonical_execution_sha256(expected)
    assert ChapterPlanResult.model_validate(result).beatCount == 2
    assert "order" not in output["sceneBeats"][0]


@pytest.mark.parametrize("field", ["artifactKey", "reviewerAgent", "beatCount", "contentSha256"])
def test_provider_plan_rejects_system_owned_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        ChapterPlanOutput.model_validate(plan() | {field: "伪造"})


@pytest.mark.parametrize("field", ["title", "summary", "chapterGoal"])
def test_provider_plan_rejects_blank_required_text(field: str) -> None:
    with pytest.raises(ValidationError):
        ChapterPlanOutput.model_validate(plan() | {field: " \n\u3000"})
    with pytest.raises(ValidationError):
        ChapterPlanOutput.model_validate(plan() | {field: " \ufeff\u00a0"})


@pytest.mark.parametrize("field", ["title", "summary", "chapterGoal", "sceneBeats"])
def test_provider_plan_cannot_omit_required_semantic_field(field: str) -> None:
    incomplete = plan()
    del incomplete[field]
    with pytest.raises(ValidationError):
        ChapterPlanOutput.model_validate(incomplete)


@pytest.mark.parametrize("value", [-1, True, 1.5, 2147483648])
def test_provider_plan_rejects_non_integer_or_database_overflow(value: object) -> None:
    with pytest.raises(ValidationError):
        ChapterPlanOutput.model_validate(plan() | {"totalEstimatedWords": value})


def test_scene_limits_and_derived_identity_are_strict() -> None:
    for scenes in (
        [],
        [{"goal": "目标"}] * 51,
        [{"goal": "目标", "order": 1}],
        [{"goal": "\u3000"}],
    ):
        with pytest.raises(ValidationError):
            ChapterPlanOutput.model_validate(plan() | {"sceneBeats": scenes})
    result = materialize_chapter_plan_output(plan())
    for field, value in (("beatCount", 3), ("contentSha256", "f" * 64)):
        with pytest.raises(ValidationError):
            ChapterPlanResult.model_validate(result | {field: value})
    wrong_order = deepcopy(result)
    wrong_order["sceneBeats"][0]["order"] = 2
    with pytest.raises(ValidationError):
        ChapterPlanResult.model_validate(wrong_order)


def test_plan_input_distinguishes_initial_and_exact_revision() -> None:
    initial = {"userInstruction": "  请规划下一章\n", "targetWordCount": 4000}
    assert ChapterPlanInput.model_validate(initial).userInstruction == initial["userInstruction"]
    previous = {
        "artifactId": "artifact-plan-1",
        "artifactRevision": 2,
        "payload": materialize_chapter_plan_output(plan()),
    }
    revised = initial | {"originalUserInstruction": "原指令", "previousArtifact": previous}
    assert ChapterPlanInput.model_validate(revised).previousArtifact.artifactRevision == 2
    for invalid in (
        initial | {"originalUserInstruction": "原指令"},
        initial | {"previousArtifact": previous},
        initial | {"targetWordCount": True},
        initial | {"selectedAgents": ["剧情"]},
        initial | {"userInstruction": " \u3000"},
    ):
        with pytest.raises(ValidationError):
            ChapterPlanInput.model_validate(invalid)

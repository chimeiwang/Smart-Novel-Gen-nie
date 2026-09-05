from __future__ import annotations

import hashlib

import pytest
from inkforge_contracts import (
    ChapterReviewInput,
    ChapterReviewOutput,
    OutlineSelectionInput,
    OutlineSelectionOutput,
    OutlineSelectionResult,
    materialize_outline_selection_output,
)
from pydantic import ValidationError


def selection_target() -> dict[str, object]:
    return {
        "resourceType": "outline_content",
        "resourceId": "outline-1",
        "baseUpdatedAt": "2026-09-05T00:00:00Z",
        "baseContentHash": "a" * 64,
        "selectionStart": 1,
        "selectionEnd": 4,
        "selectedTextHash": "b" * 64,
    }


def test_chapter_review_is_complete_text_not_evaluation() -> None:
    instruction = "  从追读角度审阅。\r\n  "
    report = "  开篇承诺清楚。\r\n尾钩需要更具体。  "
    assert (
        ChapterReviewInput.model_validate({"userInstruction": instruction}).userInstruction
        == instruction
    )
    assert ChapterReviewOutput.model_validate({"report": report}).report == report
    for value in ("", " \n\ufeff\u0085", None, 1):
        with pytest.raises(ValidationError):
            ChapterReviewOutput.model_validate({"report": value})
    with pytest.raises(ValidationError):
        ChapterReviewOutput.model_validate({"contentVerdict": "pass", "findings": []})


def test_outline_selection_derives_hash_without_changing_replacement() -> None:
    output = {"replacement": "  新剧情单元😀\r\n  "}
    expected = output | {
        "contentSha256": hashlib.sha256(output["replacement"].encode()).hexdigest()
    }
    assert materialize_outline_selection_output(output) == expected
    assert OutlineSelectionResult.model_validate(expected).replacement == output["replacement"]
    assert (
        "maxLength" not in OutlineSelectionOutput.model_json_schema()["properties"]["replacement"]
    )


def test_outline_selection_revision_requires_exact_pair() -> None:
    initial = {"userInstruction": "改写选区", "selectionTarget": selection_target()}
    previous = {"artifactId": "artifact-1", "artifactRevision": 2, "replacement": "旧候选"}
    assert OutlineSelectionInput.model_validate(initial).previousCandidate is None
    revised = OutlineSelectionInput.model_validate(
        initial | {"originalUserInstruction": "原始要求", "previousCandidate": previous}
    )
    assert revised.previousCandidate is not None and revised.previousCandidate.artifactRevision == 2
    for changed in (
        {"originalUserInstruction": "原始要求"},
        {"previousCandidate": previous},
        {"previousCandidate": None, "originalUserInstruction": None},
        {"chapterId": "伪造"},
    ):
        with pytest.raises(ValidationError):
            OutlineSelectionInput.model_validate(initial | changed)


@pytest.mark.parametrize("value", ["", " \n\ufeff\u0085", None, 1])
def test_outline_selection_output_is_strict_and_non_blank(value: object) -> None:
    with pytest.raises(ValidationError):
        OutlineSelectionOutput.model_validate({"replacement": value})
    with pytest.raises(ValidationError):
        OutlineSelectionOutput.model_validate({"replacement": "正文", "artifactId": "fake"})

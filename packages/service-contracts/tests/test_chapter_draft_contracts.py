from __future__ import annotations

import hashlib

import pytest
from inkforge_contracts.execution import (
    CandidateTextPatch,
    ChapterDraftInput,
    ChapterDraftOutput,
    ChapterDraftResult,
    EvaluationFinding,
    count_chapter_text_length,
    materialize_chapter_draft_output,
)
from pydantic import ValidationError


def draft():
    return {"summary": "  完整章节说明😀  ", "content": "\ufeff 夜里，林舟推门。\n😀\u0085"}


def test_draft_preserves_full_text_and_derives_hash_and_product_word_count():
    value = draft()
    result = materialize_chapter_draft_output(value)
    assert result == value | {
        "contentSha256": hashlib.sha256(value["content"].encode()).hexdigest(),
        "wordCount": 9,
    }
    assert ChapterDraftResult.model_validate(result).content == value["content"]
    assert "maxLength" not in ChapterDraftOutput.model_json_schema()["properties"]["content"]
    assert count_chapter_text_length("甲😀\x1c\x1d\x1e\x1f") == 6


@pytest.mark.parametrize("field", ["summary", "content"])
@pytest.mark.parametrize("value", ["", " \n\ufeff\u0085\u3000", None, 123])
def test_draft_rejects_missing_or_blank_semantic_text(field, value):
    with pytest.raises(ValidationError):
        ChapterDraftOutput.model_validate(draft() | {field: value})


@pytest.mark.parametrize("field", ["artifactKey", "wordCount", "contentSha256", "target"])
def test_draft_provider_cannot_supply_system_fields(field):
    with pytest.raises(ValidationError):
        ChapterDraftOutput.model_validate(draft() | {field: "伪造"})


def test_draft_summary_uses_codepoint_limit_and_content_is_not_truncated():
    value = {"summary": "😀" * 1000, "content": "正文\n" * 50_000}
    assert materialize_chapter_draft_output(value)["content"] == value["content"]
    with pytest.raises(ValidationError):
        ChapterDraftOutput.model_validate(value | {"summary": "😀" * 1001})
    for field in ("summary", "content"):
        with pytest.raises(ValidationError):
            ChapterDraftOutput.model_validate(
                {key: val for key, val in value.items() if key != field}
            )


@pytest.mark.parametrize(
    "changed", [{"wordCount": 99}, {"wordCount": True}, {"contentSha256": "f" * 64}]
)
def test_draft_result_rejects_incorrect_derived_fields(changed):
    with pytest.raises(ValidationError):
        ChapterDraftResult.model_validate(materialize_chapter_draft_output(draft()) | changed)


def test_draft_input_requires_exact_revision_and_original_instruction_pair():
    initial = {"userInstruction": "  完整写章\n", "targetWordCount": 4000}
    previous = {
        "artifactId": "artifact-1",
        "artifactRevision": 1,
        "payload": materialize_chapter_draft_output(draft()),
    }
    assert ChapterDraftInput.model_validate(initial).userInstruction == initial["userInstruction"]
    assert (
        ChapterDraftInput.model_validate(
            initial | {"originalUserInstruction": "最初要求", "previousArtifact": previous}
        ).previousArtifact.artifactRevision
        == 1
    )
    for changed in (
        {"originalUserInstruction": "原要求"},
        {"previousArtifact": previous},
        {"previousArtifact": None, "originalUserInstruction": None},
        {"targetWordCount": True},
        {"targetWordCount": 0},
        {"chapterId": "伪造"},
    ):
        with pytest.raises(ValidationError):
            ChapterDraftInput.model_validate(initial | changed)


def finding():
    return {
        "dimension": "chapter_draft.local",
        "severity": "warning",
        "claim": "局部措辞重复",
        "candidateRange": None,
        "evidence": [{"evidenceItemId": "e-1", "contentSha256": "a" * 64}],
        "suggestion": "删除重复的部分",
        "confidence": 0.9,
    }


def test_candidate_patch_preserves_match_and_empty_replacement_without_legacy_null():
    patch = {"kind": "text_replace", "find": " \n", "replace": ""}
    assert CandidateTextPatch.model_validate(patch).model_dump() == patch
    legacy = EvaluationFinding.model_validate(finding())
    assert "candidatePatch" not in legacy.model_dump()
    assert (
        "candidatePatch"
        not in EvaluationFinding.model_validate(finding() | {"candidatePatch": None}).model_dump()
    )
    assert (
        EvaluationFinding.model_validate(finding() | {"candidatePatch": patch}).model_dump()[
            "candidatePatch"
        ]
        == patch
    )


@pytest.mark.parametrize(
    "changed", [{"kind": "patch"}, {"find": ""}, {"replace": None}, {"revision": 1}]
)
def test_candidate_patch_is_closed_and_never_coerces_text(changed):
    with pytest.raises(ValidationError):
        CandidateTextPatch.model_validate(
            {"kind": "text_replace", "find": "原文", "replace": ""} | changed
        )

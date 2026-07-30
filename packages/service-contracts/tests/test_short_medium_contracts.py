from __future__ import annotations

import hashlib

import pytest
from inkforge_contracts.short_medium import (
    ShortMediumCheckResult,
    ShortMediumDocumentResult,
    ShortMediumReplacementResult,
    ShortMediumRunPayload,
)
from pydantic import ValidationError


def test_generate_manuscript_requires_source_outline_version() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_manuscript",
            documentType="manuscript",
            chapterId="chapter-1",
            sourceOutlineVersionId=None,
        )


def test_generate_manuscript_keeps_immutable_outline_snapshot() -> None:
    outline = "蓝图原文"
    payload = ShortMediumRunPayload(
        workflow="short_medium",
        operation="generate_manuscript",
        documentType="manuscript",
        chapterId="chapter-1",
        sourceOutlineVersionId="outline-version-1",
        sourceOutlineContent=outline,
        sourceOutlineContentHash=hashlib.sha256(outline.encode("utf-8")).hexdigest(),
        targetTotalWordCount=20_000,
    )

    assert payload.sourceOutlineContent == outline


def test_generate_manuscript_requires_immutable_outline_snapshot() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_manuscript",
            documentType="manuscript",
            chapterId="chapter-1",
            sourceOutlineVersionId="outline-version-1",
            sourceOutlineContent=None,
            sourceOutlineContentHash="a" * 64,
            targetTotalWordCount=20_000,
        )


def test_replace_selection_requires_complete_selection_identity() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="replace_selection",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId="version-1",
            baseContentHash="a" * 64,
            selectionStart=2,
            selectionEnd=5,
            selectedText="冲突",
            selectedTextHash="b" * 64,
            contextBefore=None,
            contextAfter="之后",
            userInstruction="加强冲突",
        )


def test_replace_selection_requires_original_selected_text() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="replace_selection",
            documentType="outline",
            baseVersionId="version-1",
            baseContentHash="a" * 64,
            selectionStart=2,
            selectionEnd=5,
            selectedText=None,
            selectedTextHash="b" * 64,
            userInstruction="加强冲突",
        )


def test_replace_selection_rejects_empty_or_reversed_codepoint_range() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="replace_selection",
            documentType="outline",
            baseVersionId="version-1",
            baseContentHash="a" * 64,
            selectionStart=5,
            selectionEnd=5,
            selectedText="冲突",
            selectedTextHash="b" * 64,
            userInstruction="改得更紧凑",
        )


def test_full_check_requires_manuscript_version() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="full_check",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId=None,
        )


def test_full_check_requires_immutable_manuscript_snapshot() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="full_check",
            documentType="manuscript",
            chapterId="chapter-1",
            baseVersionId="manuscript-version-1",
            baseContent=None,
            baseContentHash="a" * 64,
        )


def test_outline_generation_requires_authoritative_source() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_outline",
            documentType="outline",
            sourceKind="idea",
            sourceText=None,
        )


def test_operation_rejects_fields_owned_by_another_operation() -> None:
    with pytest.raises(ValidationError):
        ShortMediumRunPayload(
            workflow="short_medium",
            operation="generate_outline",
            documentType="outline",
            selectionStart=0,
        )


def test_document_result_matches_generation_operation_and_document() -> None:
    result = ShortMediumDocumentResult(
        resultType="short_medium_document",
        operation="generate_manuscript",
        documentType="manuscript",
        content="完整正文",
        sourceOutlineVersionId="outline-version-1",
    )

    assert result.content == "完整正文"

    with pytest.raises(ValidationError):
        ShortMediumDocumentResult(
            resultType="short_medium_document",
            operation="generate_outline",
            documentType="manuscript",
            content="错误文档",
        )


def test_replacement_result_only_contains_replacement_text() -> None:
    selection_identity = {
        "baseVersionId": "version-1",
        "baseContentHash": "a" * 64,
        "selectionStart": 2,
        "selectionEnd": 5,
        "selectedTextHash": "b" * 64,
    }

    value = ShortMediumReplacementResult(
        resultType="short_medium_replacement",
        operation="replace_selection",
        documentType="manuscript",
        replacement="新文本",
        **selection_identity,
    )
    assert value.replacement == "新文本"

    with pytest.raises(ValidationError):
        ShortMediumReplacementResult(
            resultType="short_medium_replacement",
            operation="replace_selection",
            documentType="manuscript",
            replacement="新文本",
            content="不允许携带完整正文",
            **selection_identity,
        )


def test_check_result_is_bound_to_manuscript_version() -> None:
    result = ShortMediumCheckResult(
        resultType="short_medium_check",
        operation="full_check",
        documentType="manuscript",
        baseVersionId="manuscript-version-1",
        report={"summary": "结尾已兑现开篇承诺", "issues": []},
    )

    assert result.baseVersionId == "manuscript-version-1"

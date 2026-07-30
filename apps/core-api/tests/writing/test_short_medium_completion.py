from __future__ import annotations

import hashlib

import pytest
from inkforge_contracts.short_medium import ShortMediumRunPayload
from inkforge_core.errors import ApiError
from inkforge_core.short_medium.completion import materialize_short_medium_result


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def selection_payload() -> ShortMediumRunPayload:
    content = "前😀乙后"
    return ShortMediumRunPayload(
        workflow="short_medium",
        operation="replace_selection",
        documentType="manuscript",
        chapterId="chapter-1",
        baseVersionId="manuscript-1",
        baseContent=content,
        baseContentHash=sha256(content),
        sourceOutlineVersionId="outline-1",
        sourceOutlineContent="蓝图",
        sourceOutlineContentHash=sha256("蓝图"),
        selectionStart=1,
        selectionEnd=3,
        selectedText="😀乙",
        selectedTextHash=sha256("😀乙"),
        contextBefore="前",
        contextAfter="后",
        userInstruction="加强冲突",
    )


def test_replacement_completion_only_changes_unicode_selection() -> None:
    payload = selection_payload()

    materialized = materialize_short_medium_result(
        payload,
        {
            "resultType": "short_medium_replacement",
            "operation": "replace_selection",
            "documentType": "manuscript",
            "replacement": "🔥",
            "baseVersionId": "manuscript-1",
            "baseContentHash": payload.baseContentHash,
            "selectionStart": 1,
            "selectionEnd": 3,
            "selectedTextHash": payload.selectedTextHash,
        },
    )

    assert materialized.content == "前🔥后"
    assert materialized.content[:1] == payload.baseContent[:1]
    assert materialized.content[-1:] == payload.baseContent[-1:]


def test_replacement_completion_rejects_changed_selection_identity() -> None:
    payload = selection_payload()

    with pytest.raises(ApiError) as error:
        materialize_short_medium_result(
            payload,
            {
                "resultType": "short_medium_replacement",
                "operation": "replace_selection",
                "documentType": "manuscript",
                "replacement": "🔥",
                "baseVersionId": "manuscript-1",
                "baseContentHash": payload.baseContentHash,
                "selectionStart": 0,
                "selectionEnd": 3,
                "selectedTextHash": payload.selectedTextHash,
            },
        )

    assert error.value.code == "SHORT_MEDIUM_COMPLETION_IDENTITY_MISMATCH"


def test_full_check_materializes_report_without_document_content() -> None:
    content = "完整正文"
    payload = ShortMediumRunPayload(
        workflow="short_medium",
        operation="full_check",
        documentType="manuscript",
        chapterId="chapter-1",
        baseVersionId="manuscript-1",
        baseContent=content,
        baseContentHash=sha256(content),
    )

    materialized = materialize_short_medium_result(
        payload,
        {
            "resultType": "short_medium_check",
            "operation": "full_check",
            "documentType": "manuscript",
            "baseVersionId": "manuscript-1",
            "report": {"text": "检查报告"},
        },
    )

    assert materialized.content is None
    assert materialized.check_report == {"text": "检查报告"}


@pytest.mark.parametrize(
    ("source_kind", "source_text", "generated"),
    [
        ("opening", "固定开头。", "被改写的开头。后续正文"),
        ("ending", "固定结尾。", "前文。被改写的结尾。"),
    ],
)
def test_manuscript_completion_rejects_changed_fixed_source_boundary(
    source_kind: str,
    source_text: str,
    generated: str,
) -> None:
    payload = ShortMediumRunPayload(
        workflow="short_medium",
        operation="generate_manuscript",
        documentType="manuscript",
        chapterId="chapter-1",
        sourceOutlineVersionId="outline-1",
        sourceOutlineContent="蓝图",
        sourceOutlineContentHash=sha256("蓝图"),
        targetTotalWordCount=6_000,
        sourceKind=source_kind,  # type: ignore[arg-type]
        sourceText=source_text,
    )

    with pytest.raises(ApiError) as error:
        materialize_short_medium_result(
            payload,
            {
                "resultType": "short_medium_document",
                "operation": "generate_manuscript",
                "documentType": "manuscript",
                "content": generated,
                "sourceOutlineVersionId": "outline-1",
            },
        )

    assert error.value.code == "SHORT_MEDIUM_FIXED_SOURCE_CHANGED"

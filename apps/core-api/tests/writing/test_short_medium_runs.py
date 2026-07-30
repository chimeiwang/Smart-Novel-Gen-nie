from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.short_medium.completion import (
    ShortMediumRunSource,
    assemble_short_medium_run_payload,
)
from inkforge_core.short_medium.repository import (
    VersionRecord,
    version_record_from_values,
)
from inkforge_core.short_medium.schemas import DocumentVersionPayload
from inkforge_core.writing.schemas import ShortMediumStartWritingRunRequest
from pydantic import ValidationError

NOW = datetime(2026, 7, 30, tzinfo=UTC)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def version(
    version_id: str,
    *,
    document_type: str,
    content: str,
    version_number: int = 1,
    source_outline_version_id: str | None = None,
) -> VersionRecord:
    payload = DocumentVersionPayload(
        kind="outline_draft" if document_type == "outline" else "chapter_draft",
        documentType=document_type,  # type: ignore[arg-type]
        versionNumber=version_number,
        baseVersionId=None,
        clientRequestId="request-12345678",
        source="manual",
        content=content,
        contentHash=sha256(content),
        sourceOutlineVersionId=source_outline_version_id,
    )
    return version_record_from_values(
        id=version_id,
        novel_id="novel-1",
        chapter_id=None if document_type == "outline" else "chapter-1",
        artifact_key=(
            "short-medium:outline:novel-1"
            if document_type == "outline"
            else "short-medium:manuscript:chapter-1"
        ),
        status="applied",
        summary=None,
        payload_json=payload.model_dump_json(),
        diff_json=None,
        created_by_agent=None,
        task_id=None,
        created_at=NOW,
        updated_at=NOW,
        applied_at=NOW,
    )


def test_public_short_medium_request_rejects_untrusted_content_and_hashes() -> None:
    values = {
        "clientRequestId": "request-12345678",
        "workflow": "short_medium",
        "novelId": "novel-1",
        "operation": "full_check",
        "documentType": "manuscript",
        "chapterId": "chapter-1",
        "baseVersionId": "manuscript-1",
    }
    assert ShortMediumStartWritingRunRequest.model_validate(values).operation == "full_check"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ShortMediumStartWritingRunRequest.model_validate(
            {**values, "baseContent": "客户端伪造正文"}
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ShortMediumStartWritingRunRequest.model_validate(
            {**values, "baseContentHash": "0" * 64}
        )


def test_generate_manuscript_uses_current_applied_outline_snapshot() -> None:
    outline = version("outline-1", document_type="outline", content="固定蓝图")
    request = ShortMediumStartWritingRunRequest(
        clientRequestId="request-12345678",
        workflow="short_medium",
        novelId="novel-1",
        operation="generate_manuscript",
        documentType="manuscript",
        chapterId="chapter-1",
        baseVersionId=None,
        sourceOutlineVersionId=outline.id,
        userInstruction="生成完整正文",
    )
    source = ShortMediumRunSource(
        chapter_id="chapter-1",
        target_total_word_count=20_000,
        source_kind="idea",
        source_text="一个灵感",
        document_content="",
        current_document_version=None,
        outline_content=outline.content,
        current_outline_version=outline,
    )

    payload = assemble_short_medium_run_payload(request, source)

    assert payload.sourceOutlineVersionId == outline.id
    assert payload.sourceOutlineContent == "固定蓝图"
    assert payload.sourceOutlineContentHash == sha256("固定蓝图")
    assert payload.targetTotalWordCount == 20_000


def test_dirty_outline_blocks_manuscript_generation() -> None:
    outline = version("outline-1", document_type="outline", content="已确认蓝图")
    request = ShortMediumStartWritingRunRequest(
        clientRequestId="request-12345678",
        workflow="short_medium",
        novelId="novel-1",
        operation="generate_manuscript",
        documentType="manuscript",
        chapterId="chapter-1",
        sourceOutlineVersionId=outline.id,
    )
    source = ShortMediumRunSource(
        chapter_id="chapter-1",
        target_total_word_count=20_000,
        source_kind="idea",
        source_text="灵感",
        document_content="",
        current_document_version=None,
        outline_content="未提交蓝图修改",
        current_outline_version=outline,
    )

    with pytest.raises(ApiError) as error:
        assemble_short_medium_run_payload(request, source)

    assert error.value.code == "SHORT_MEDIUM_WORK_DRAFT_DIRTY"


def test_selection_uses_unicode_code_points_and_core_derived_text() -> None:
    content = "甲😀乙丙"
    manuscript = version(
        "manuscript-1",
        document_type="manuscript",
        content=content,
        source_outline_version_id="outline-1",
    )
    request = ShortMediumStartWritingRunRequest(
        clientRequestId="request-12345678",
        workflow="short_medium",
        novelId="novel-1",
        operation="replace_selection",
        documentType="manuscript",
        chapterId="chapter-1",
        baseVersionId=manuscript.id,
        selectionStart=1,
        selectionEnd=3,
        selectedTextHash=sha256("😀乙"),
        userInstruction="只加强冲突",
    )
    source = ShortMediumRunSource(
        chapter_id="chapter-1",
        target_total_word_count=20_000,
        source_kind="idea",
        source_text="灵感",
        document_content=content,
        current_document_version=manuscript,
        outline_content="蓝图",
        current_outline_version=version(
            "outline-1", document_type="outline", content="蓝图"
        ),
    )

    payload = assemble_short_medium_run_payload(request, source)

    assert payload.selectedText == "😀乙"
    assert payload.baseContent == content
    assert payload.contextBefore == "甲"
    assert payload.contextAfter == "丙"


def test_selection_hash_mismatch_is_rejected_before_task_creation() -> None:
    outline = version("outline-1", document_type="outline", content="甲😀乙")
    request = ShortMediumStartWritingRunRequest(
        clientRequestId="request-12345678",
        workflow="short_medium",
        novelId="novel-1",
        operation="replace_selection",
        documentType="outline",
        baseVersionId=outline.id,
        selectionStart=1,
        selectionEnd=2,
        selectedTextHash=sha256("伪造"),
        userInstruction="改写",
    )
    source = ShortMediumRunSource(
        chapter_id="chapter-1",
        target_total_word_count=20_000,
        source_kind="outline",
        source_text="甲😀乙",
        document_content="甲😀乙",
        current_document_version=outline,
        outline_content="甲😀乙",
        current_outline_version=outline,
    )

    with pytest.raises(ApiError) as error:
        assemble_short_medium_run_payload(request, source)

    assert error.value.code == "SHORT_MEDIUM_SELECTION_HASH_CONFLICT"

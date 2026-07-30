from __future__ import annotations

import hashlib

import pytest
from inkforge_core.short_medium.schemas import DocumentVersionPayload
from pydantic import ValidationError


def test_version_payload_rejects_hash_that_does_not_match_complete_content() -> None:
    with pytest.raises(ValidationError, match="contentHash"):
        DocumentVersionPayload(
            kind="outline_draft",
            documentType="outline",
            versionNumber=1,
            baseVersionId=None,
            clientRequestId="request-12345678",
            source="manual",
            content="完整大纲",
            contentHash="0" * 64,
        )


def test_version_payload_preserves_complete_long_content() -> None:
    content = "正文" * 40_000 + "八万字尾部标记"
    payload = DocumentVersionPayload(
        kind="chapter_draft",
        documentType="manuscript",
        versionNumber=1,
        baseVersionId=None,
        clientRequestId="request-12345678",
        source="manual",
        content=content,
        contentHash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        sourceOutlineVersionId="outline-version-1",
    )

    assert payload.content.endswith("八万字尾部标记")
    assert payload.content == content


def test_manuscript_version_requires_source_outline_version() -> None:
    with pytest.raises(ValidationError, match="sourceOutlineVersionId"):
        DocumentVersionPayload(
            kind="chapter_draft",
            documentType="manuscript",
            versionNumber=1,
            baseVersionId=None,
            clientRequestId="request-12345678",
            source="manual",
            content="正文",
            contentHash=hashlib.sha256("正文".encode()).hexdigest(),
        )


def test_restore_version_requires_restored_source_and_manual_requires_request_id() -> None:
    content_hash = hashlib.sha256("大纲".encode()).hexdigest()
    with pytest.raises(ValidationError):
        DocumentVersionPayload(
            kind="outline_draft",
            documentType="outline",
            versionNumber=2,
            baseVersionId="version-1",
            source="restore",
            content="大纲",
            contentHash=content_hash,
        )
    with pytest.raises(ValidationError):
        DocumentVersionPayload(
            kind="outline_draft",
            documentType="outline",
            versionNumber=2,
            baseVersionId="version-1",
            clientRequestId="request-12345678",
            source="restore",
            content="大纲",
            contentHash=content_hash,
        )

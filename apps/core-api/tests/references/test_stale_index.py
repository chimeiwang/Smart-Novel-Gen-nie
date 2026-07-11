from __future__ import annotations

import pytest
from inkforge_core.db.models import RagDocument, ReferenceMaterial
from inkforge_core.errors import ApiError
from inkforge_core.references.rag import content_sha256
from inkforge_core.references.repository import ReferenceRepository


def reference(content: str = "当前正文") -> ReferenceMaterial:
    return ReferenceMaterial(
        id="reference-1",
        novelId="novel-1",
        title="资料",
        type="note",
        content=content,
        sourceUrl=None,
    )


def document(content_hash: str, status: str = "disabled") -> RagDocument:
    return RagDocument(
        id="document-1",
        novelId="novel-1",
        sourceType="reference_material",
        sourceId="reference-1",
        title="资料",
        contentHash=content_hash,
        status=status,
        errorMessage=None,
    )


def test_current_reference_and_document_hash_are_both_required() -> None:
    current_hash = content_sha256("当前正文")
    ReferenceRepository._require_current_hash(reference(), document(current_hash), current_hash)


@pytest.mark.parametrize(
    ("reference_content", "document_hash", "expected_hash"),
    [
        ("新正文", content_sha256("旧正文"), content_sha256("旧正文")),
        ("新正文", content_sha256("新正文"), content_sha256("旧正文")),
        ("新正文", content_sha256("旧正文"), content_sha256("新正文")),
    ],
)
def test_any_stale_hash_combination_is_rejected_before_mutation(
    reference_content: str, document_hash: str, expected_hash: str
) -> None:
    with pytest.raises(ApiError) as caught:
        ReferenceRepository._require_current_hash(
            reference(reference_content), document(document_hash), expected_hash
        )
    assert caught.value.status_code == 409
    assert caught.value.code == "RAG_INDEX_STALE"


@pytest.mark.parametrize("status", ["ready", "failed"])
def test_old_failure_callback_cannot_overwrite_terminal_index_state(status: str) -> None:
    with pytest.raises(ApiError) as caught:
        ReferenceRepository._require_failure_target(document(content_sha256("正文"), status))
    assert caught.value.code == "RAG_INDEX_STALE"

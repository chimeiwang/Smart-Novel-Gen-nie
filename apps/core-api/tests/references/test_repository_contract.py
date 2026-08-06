from __future__ import annotations

import inspect

from inkforge_core.references.repository import ReferenceRepository


def test_reference_content_change_explicitly_deletes_old_chunks_and_disables_document() -> None:
    source = inspect.getsource(ReferenceRepository._update_reference_in_session)
    assert "delete(RagChunk)" in source
    assert 'document.status = "disabled"' in source
    assert '"content" in changed_fields' in source
    assert 'if "title" in changed_fields' in source


def test_reference_delete_explicitly_deletes_rag_document_before_source() -> None:
    source = inspect.getsource(ReferenceRepository._delete_reference_in_session)
    assert source.index("_lock_reference_and_document") < source.index("delete(RagDocument)")
    assert source.index("delete(RagChunk)") < source.index("delete(RagDocument)")
    assert source.index("delete(RagDocument)") < source.index("delete(ReferenceMaterial)")
    assert "rowcount != 1" in source


def test_reference_and_document_lock_order_is_stable() -> None:
    source = inspect.getsource(ReferenceRepository._lock_reference_and_document)
    assert source.count("with_for_update") == 2
    assert source.index("select(ReferenceMaterial)") < source.index("select(RagDocument)")


def test_reference_mutations_lock_owner_and_novel_before_resource_rows() -> None:
    for name in ("create_reference", "update_reference", "delete_reference", "prepare_reindex"):
        source = inspect.getsource(getattr(ReferenceRepository, name))
        assert source.index("_require_owner") < source.index("_lock_novel")
    assert "with_for_update" in inspect.getsource(ReferenceRepository._lock_novel)


def test_review_reference_batch_reuses_one_session_and_one_novel_lock() -> None:
    source = inspect.getsource(ReferenceRepository.apply_reference_mutations)
    assert source.count("self._session_factory()") == 1
    assert source.count("session.begin()") == 1
    assert source.count("_lock_novel") == 1
    assert "_create_reference_in_session" in source
    assert "_update_reference_in_session" in source
    assert "_delete_reference_in_session" in source


def test_reference_source_url_is_never_fetched() -> None:
    source = inspect.getsource(ReferenceRepository)
    assert "httpx" not in source
    assert "fetch(" not in source
    assert "sourceUrl" in source


def test_index_replacement_uses_fixed_size_batches_and_vector_binding() -> None:
    source = inspect.getsource(ReferenceRepository.replace_index)
    assert "EMBEDDING_BATCH_SIZE" in source
    assert "insert(RagChunk)" in source
    assert '"embedding": normalized[index]' in source


def test_index_callbacks_lock_both_rows_and_check_job_identity_before_mutation() -> None:
    lock_source = inspect.getsource(ReferenceRepository._lock_reference_and_document)
    replace_source = inspect.getsource(ReferenceRepository.replace_index)
    failure_source = inspect.getsource(ReferenceRepository.mark_index_failed)
    assert lock_source.count("with_for_update") == 2
    assert replace_source.index("_require_current_job_identity") < replace_source.index(
        "delete(RagChunk)"
    )
    assert "_require_current_job_identity" in failure_source
    assert "_require_failure_target" in failure_source

from __future__ import annotations

import inspect

from inkforge_core.references.repository import ReferenceRepository


def test_reference_content_change_explicitly_deletes_old_chunks_and_disables_document() -> None:
    source = inspect.getsource(ReferenceRepository.update_reference)
    assert "delete(RagChunk)" in source
    assert 'document.status = "disabled"' in source
    assert '"title", "content"' in source


def test_reference_delete_explicitly_deletes_rag_document_before_source() -> None:
    source = inspect.getsource(ReferenceRepository.delete_reference)
    assert source.index("_lock_reference_and_document") < source.index("delete(RagDocument)")
    assert source.index("delete(RagDocument)") < source.index("delete(ReferenceMaterial)")
    assert "rowcount != 1" in source


def test_reference_and_document_lock_order_is_stable() -> None:
    source = inspect.getsource(ReferenceRepository._lock_reference_and_document)
    assert source.count("with_for_update") == 2
    assert source.index("select(ReferenceMaterial)") < source.index("select(RagDocument)")


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


def test_index_callbacks_lock_both_rows_and_check_hash_before_chunk_deletion() -> None:
    lock_source = inspect.getsource(ReferenceRepository._lock_reference_and_document)
    replace_source = inspect.getsource(ReferenceRepository.replace_index)
    failure_source = inspect.getsource(ReferenceRepository.mark_index_failed)
    assert lock_source.count("with_for_update") == 2
    assert replace_source.index("_require_current_hash") < replace_source.index("delete(RagChunk)")
    assert "_require_current_hash" in failure_source
    assert "_require_failure_target" in failure_source

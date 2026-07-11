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
    assert source.index("delete(RagDocument)") < source.index("delete(ReferenceMaterial)")
    assert "rowcount != 1" in source


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

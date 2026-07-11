from __future__ import annotations

import math

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.references.rag import (
    SEARCH_SQL,
    chunk_text_losslessly,
    content_sha256,
    normalize_embeddings,
    validate_top_k,
    vector_literal,
)


@pytest.mark.parametrize(
    "source",
    [
        "",
        "  首尾空白  ",
        "第一段\n\n\n第二段",
        "第一行\r\n第二行\r\n",
        "甲😀乙" * 1000,
        "没有任何分隔符" * 1000,
    ],
    ids=["空文本", "首尾空白", "连续空行", "回车换行", "表情符号", "超长无分隔"],
)
def test_chunking_is_lossless_for_all_source_characters(source: str) -> None:
    chunks = chunk_text_losslessly(source, max_chars=17)
    assert "".join(chunks) == source
    assert all(0 < len(value) <= 17 for value in chunks)


def test_hash_uses_original_utf8_bytes() -> None:
    assert content_sha256("a\r\n") != content_sha256("a\n")
    assert content_sha256(" 文本 ") != content_sha256("文本")


def test_embedding_validation_rejects_empty_nonfinite_and_mixed_dimensions() -> None:
    for value in ([], [[]], [[1.0, math.nan]], [[1.0], [1.0, 2.0]]):
        with pytest.raises(ApiError) as caught:
            normalize_embeddings(value)
        assert caught.value.code == "EMBEDDING_INVALID"


def test_empty_document_has_no_chunks_and_needs_no_embedding_vector() -> None:
    assert chunk_text_losslessly("") == []


def test_vector_literal_only_accepts_validated_finite_values() -> None:
    assert vector_literal([1.0, -2.5]) == "[1.0,-2.5]"
    with pytest.raises(ApiError):
        vector_literal([math.inf])


def test_search_sql_binds_all_values_and_guards_mixed_dimensions_in_both_expressions() -> None:
    assert SEARCH_SQL.count('CASE WHEN c."embeddingDimension" = :dimension') == 2
    assert "CAST(:query_vector AS vector)" in SEARCH_SQL
    assert ":novel_id" in SEARCH_SQL
    assert ":source_type" in SEARCH_SQL
    assert ":top_k" in SEARCH_SQL
    assert "{query" not in SEARCH_SQL


@pytest.mark.parametrize("top_k", [0, -1, 21, 100, 2**31])
def test_top_k_outside_explicit_limit_is_rejected_instead_of_clamped(top_k: int) -> None:
    with pytest.raises(ApiError) as caught:
        validate_top_k(top_k)
    assert caught.value.code == "RAG_TOP_K_INVALID"


@pytest.mark.parametrize("top_k", [1, 20])
def test_top_k_accepts_both_boundaries(top_k: int) -> None:
    assert validate_top_k(top_k) == top_k

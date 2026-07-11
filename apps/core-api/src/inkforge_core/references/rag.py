from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from sqlalchemy import TextClause, text

from ..errors import ApiError

MAX_CHUNK_CHARS = 1800
EMBEDDING_BATCH_SIZE = 10
MAX_TOP_K = 20

SEARCH_SQL = """
SELECT
  d."title",
  d."sourceId",
  c."chunkIndex",
  c."text",
  1 - CASE WHEN c."embeddingDimension" = :dimension
      THEN c."embedding" <=> CAST(:query_vector AS vector) END AS "score"
FROM "RagChunk" AS c
JOIN "RagDocument" AS d ON d."id" = c."documentId"
WHERE c."novelId" = :novel_id
  AND d."novelId" = :novel_id
  AND d."sourceType" = :source_type
  AND d."status" = 'ready'
  AND c."embeddingDimension" = :dimension
ORDER BY CASE WHEN c."embeddingDimension" = :dimension
    THEN c."embedding" <=> CAST(:query_vector AS vector) END
LIMIT :top_k
"""


def chunk_text_losslessly(content: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """按 Python 字符边界切分，完整保留空白、换行和每个 Unicode 字符。"""

    if max_chars <= 0:
        raise ValueError("分块长度必须大于零")
    return [content[index : index + max_chars] for index in range(0, len(content), max_chars)]


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize_embeddings(values: Sequence[Sequence[float]]) -> list[list[float]]:
    if not values:
        raise _embedding_error()
    normalized: list[list[float]] = []
    dimension: int | None = None
    for value in values:
        vector = [float(item) for item in value]
        if not vector or any(not math.isfinite(item) for item in vector):
            raise _embedding_error()
        if dimension is None:
            dimension = len(vector)
        elif len(vector) != dimension:
            raise _embedding_error()
        normalized.append(vector)
    return normalized


def vector_literal(value: Sequence[float]) -> str:
    normalized = normalize_embeddings([value])[0]
    return "[" + ",".join(str(item) for item in normalized) + "]"


def validate_top_k(top_k: int) -> int:
    if top_k <= 0 or top_k > MAX_TOP_K:
        raise ApiError(
            status_code=422,
            code="RAG_TOP_K_INVALID",
            message="检索结果数量必须在 1 到 20 之间",
        )
    return top_k


def search_statement() -> TextClause:
    """返回全部值均通过绑定参数传入的余弦检索语句。"""

    return text(SEARCH_SQL)


def _embedding_error() -> ApiError:
    return ApiError(
        status_code=422,
        code="EMBEDDING_INVALID",
        message="嵌入向量必须非空、维度一致且只包含有限数值",
    )

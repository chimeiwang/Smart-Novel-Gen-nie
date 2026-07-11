from __future__ import annotations

import pytest
from inkforge_core.app import create_app
from inkforge_core.references.schemas import (
    CompleteReferenceIndexRequest,
    RagSearchRequest,
)
from pydantic import ValidationError

HASH = "a" * 64


def test_index_callback_accepts_exact_capacity_boundary() -> None:
    body = CompleteReferenceIndexRequest(
        taskId="task-1",
        runId="run-1",
        expectedContentHash=HASH,
        embeddings=[[1.0] * 4096 for _ in range(64)],
    )
    assert len(body.embeddings) == 64
    assert len(body.embeddings[0]) == 4096


@pytest.mark.parametrize(
    "payload",
    [
        {
            "taskId": "task-1",
            "runId": "run-1",
            "expectedContentHash": HASH,
            "embeddings": [[1.0] for _ in range(65)],
        },
        {
            "taskId": "task-1",
            "runId": "run-1",
            "expectedContentHash": HASH,
            "embeddings": [[1.0] * 4097],
        },
        {
            "taskId": "task-1",
            "runId": "run-1",
            "expectedContentHash": "bad",
            "embeddings": [[1.0]],
        },
    ],
)
def test_index_callback_rejects_capacity_and_hash_violations(payload) -> None:
    with pytest.raises(ValidationError):
        CompleteReferenceIndexRequest.model_validate(payload)


def test_search_request_accepts_exact_embedding_capacity_boundary() -> None:
    request = RagSearchRequest(queryEmbedding=[1.0] * 4096)
    assert len(request.queryEmbedding) == 4096


@pytest.mark.parametrize("query_embedding", [[], [1.0] * 4097])
def test_search_request_rejects_empty_or_oversized_embedding(
    query_embedding: list[float],
) -> None:
    with pytest.raises(ValidationError):
        RagSearchRequest.model_validate({"queryEmbedding": query_embedding})


def test_search_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RagSearchRequest.model_validate(
            {"queryEmbedding": [1.0], "embedding": [1.0]}
        )


def test_search_openapi_uses_query_embedding_contract_name() -> None:
    schema = create_app(testing=True).openapi()["components"]["schemas"]["RagSearchRequest"]
    assert set(schema["properties"]) == {"queryEmbedding", "topK"}
    assert schema["properties"]["queryEmbedding"]["minItems"] == 1
    assert schema["properties"]["queryEmbedding"]["maxItems"] == 4096

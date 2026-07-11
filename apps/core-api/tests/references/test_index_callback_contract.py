from __future__ import annotations

import pytest
from inkforge_core.references.schemas import CompleteReferenceIndexRequest
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

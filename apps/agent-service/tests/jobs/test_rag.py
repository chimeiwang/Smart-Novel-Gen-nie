from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.jobs.rag import RagJobHandler
from inkforge_agents.queue.repository import QueueJob


class Core:
    def __init__(self) -> None:
        self.completed: list[tuple[str, str, list[list[float]]]] = []

    async def get_rag_context(
        self, resource: object, reference_id: str, content_hash: str
    ) -> dict[str, Any]:
        del resource
        assert reference_id == "reference-1"
        assert content_hash == "hash-1"
        return {"chunks": ["第一段", "第二段"], "contentHash": "hash-1"}

    async def complete_rag(
        self,
        resource: object,
        reference_id: str,
        content_hash: str,
        embeddings: list[list[float]],
    ) -> None:
        del resource
        self.completed.append((reference_id, content_hash, embeddings))

    async def fail_rag(self, *args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))


class Embeddings:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        assert texts == ["第一段", "第二段"]
        return [[1.0, 0.0], [0.0, 1.0]]


@pytest.mark.asyncio
async def test_rag_job_reads_current_chunks_and_returns_embeddings_to_core() -> None:
    core = Core()
    handler = RagJobHandler(core, Embeddings())
    job = QueueJob(
        jobId="rag-1",
        kind="rag",
        runId="rag-1",
        taskId="rag-1",
        novelId="novel-1",
        userId="user-1",
        priority=30,
        payload={"referenceId": "reference-1", "contentHash": "hash-1"},
        createdAt=datetime.now(UTC),
    )

    await handler(job)

    assert core.completed == [
        ("reference-1", "hash-1", [[1.0, 0.0], [0.0, 1.0]])
    ]

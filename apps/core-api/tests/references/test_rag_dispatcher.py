from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from inkforge_contracts.jobs import AgentJobStatus
from inkforge_core.references.rag_dispatcher import RagDispatchRecord, RagIndexDispatcher

HASH = "a" * 64
GENERATION = datetime(2026, 8, 7, 1, 2, 3, 456000, tzinfo=UTC)


def record(reference_id: str) -> RagDispatchRecord:
    return RagDispatchRecord(
        user_id="user-1",
        novel_id="novel-1",
        reference_id=reference_id,
        content_hash=HASH,
        generation=GENERATION,
    )


class Repository:
    def __init__(self, records: list[RagDispatchRecord]) -> None:
        self.records = records
        self.claimed = asyncio.Event()
        self.terminals: list[tuple[str, str, str, datetime, AgentJobStatus]] = []

    async def list_pending_rag_documents(self, limit: int) -> list[RagDispatchRecord]:
        self.claimed.set()
        return self.records[:limit]

    async def mark_rag_dispatch_terminal(
        self,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        generation: datetime,
        agent_status: AgentJobStatus,
    ) -> None:
        self.terminals.append(
            (novel_id, reference_id, content_hash, generation, agent_status)
        )


class Submitter:
    def __init__(
        self,
        failing_reference_id: str | None = None,
        statuses: dict[str, AgentJobStatus] | None = None,
    ) -> None:
        self.failing_reference_id = failing_reference_id
        self.statuses = statuses or {}
        self.calls: list[tuple[str, str, str, str, datetime]] = []

    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        generation: datetime,
    ) -> AgentJobStatus:
        self.calls.append((user_id, novel_id, reference_id, content_hash, generation))
        if reference_id == self.failing_reference_id:
            raise ConnectionError("索引提交暂时失败")
        return self.statuses.get(reference_id, "queued")


@pytest.mark.asyncio
async def test_rag_dispatcher_submits_only_persisted_pending_records() -> None:
    repository = Repository([record("reference-1")])
    submitter = Submitter()
    dispatcher = RagIndexDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert submitter.calls == [
        ("user-1", "novel-1", "reference-1", HASH, GENERATION)
    ]


@pytest.mark.asyncio
async def test_rag_dispatcher_reuses_same_persisted_generation_on_network_retry() -> None:
    repository = Repository([record("reference-1")])
    submitter = Submitter()
    dispatcher = RagIndexDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert await dispatcher.run_once() == 1
    assert submitter.calls[0] == submitter.calls[1]


@pytest.mark.asyncio
async def test_rag_dispatcher_isolates_one_submission_failure() -> None:
    repository = Repository([record("bad"), record("good")])
    submitter = Submitter(failing_reference_id="bad")
    dispatcher = RagIndexDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert [value[2] for value in submitter.calls] == ["bad", "good"]


@pytest.mark.asyncio
async def test_rag_dispatcher_propagates_deterministic_submission_error() -> None:
    repository = Repository([record("invalid")])

    class InvalidSubmitter(Submitter):
        async def submit(
            self,
            user_id: str,
            novel_id: str,
            reference_id: str,
            content_hash: str,
            generation: datetime,
        ) -> AgentJobStatus:
            del user_id, novel_id, reference_id, content_hash, generation
            raise TypeError("索引提交契约错误")

    dispatcher = RagIndexDispatcher(repository, InvalidSubmitter())

    with pytest.raises(TypeError, match="索引提交契约错误"):
        await dispatcher.run_once()


@pytest.mark.asyncio
async def test_rag_dispatcher_converges_existing_terminal_job() -> None:
    repository = Repository([record("terminal")])
    submitter = Submitter(statuses={"terminal": "cancelled"})
    dispatcher = RagIndexDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert repository.terminals == [
        ("novel-1", "terminal", HASH, GENERATION, "cancelled")
    ]


@pytest.mark.asyncio
async def test_rag_dispatcher_loop_recovers_after_repository_failure() -> None:
    class FlakyRepository(Repository):
        def __init__(self) -> None:
            super().__init__([record("recovered")])
            self.failed = False

        async def list_pending_rag_documents(self, limit: int) -> list[RagDispatchRecord]:
            if not self.failed:
                self.failed = True
                raise ConnectionError("索引任务领取暂时失败")
            return await super().list_pending_rag_documents(limit)

    repository = FlakyRepository()
    submitter = Submitter()
    dispatcher = RagIndexDispatcher(repository, submitter, interval_seconds=0.001)

    task = asyncio.create_task(dispatcher.run())
    await asyncio.wait_for(repository.claimed.wait(), timeout=1)
    dispatcher.request_stop()
    await task

    assert [value[2] for value in submitter.calls] == ["recovered"]

from __future__ import annotations

import asyncio

import pytest
from inkforge_contracts.jobs import AgentJobStatus
from inkforge_core.references.rag_dispatcher import RagDispatchRecord, RagIndexDispatcher

HASH = "a" * 64


def record(reference_id: str) -> RagDispatchRecord:
    return RagDispatchRecord(
        user_id="user-1",
        novel_id="novel-1",
        reference_id=reference_id,
        content_hash=HASH,
    )


class Repository:
    def __init__(self, records: list[RagDispatchRecord]) -> None:
        self.records = records
        self.claimed = asyncio.Event()
        self.terminals: list[tuple[str, str, str, AgentJobStatus]] = []

    async def list_pending_rag_documents(self, limit: int) -> list[RagDispatchRecord]:
        self.claimed.set()
        return self.records[:limit]

    async def mark_rag_dispatch_terminal(
        self,
        novel_id: str,
        reference_id: str,
        content_hash: str,
        agent_status: AgentJobStatus,
    ) -> None:
        self.terminals.append((novel_id, reference_id, content_hash, agent_status))


class Submitter:
    def __init__(
        self,
        failing_reference_id: str | None = None,
        statuses: dict[str, AgentJobStatus] | None = None,
    ) -> None:
        self.failing_reference_id = failing_reference_id
        self.statuses = statuses or {}
        self.calls: list[tuple[str, str, str, str]] = []

    async def submit(
        self,
        user_id: str,
        novel_id: str,
        reference_id: str,
        content_hash: str,
    ) -> AgentJobStatus:
        self.calls.append((user_id, novel_id, reference_id, content_hash))
        if reference_id == self.failing_reference_id:
            raise ConnectionError("索引提交暂时失败")
        return self.statuses.get(reference_id, "queued")


@pytest.mark.asyncio
async def test_rag_dispatcher_submits_only_persisted_pending_records() -> None:
    repository = Repository([record("reference-1")])
    submitter = Submitter()
    dispatcher = RagIndexDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert submitter.calls == [("user-1", "novel-1", "reference-1", HASH)]


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
        ) -> AgentJobStatus:
            del user_id, novel_id, reference_id, content_hash
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
        ("novel-1", "terminal", HASH, "cancelled")
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

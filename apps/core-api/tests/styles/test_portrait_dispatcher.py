from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from inkforge_contracts.jobs import AgentJobStatus
from inkforge_core.styles.portrait_dispatcher import (
    PortraitDispatchRecord,
    PortraitTaskDispatcher,
)


class Repository:
    def __init__(self, records: list[PortraitDispatchRecord]) -> None:
        self.records = records
        self.calls: list[tuple[int, datetime]] = []
        self.terminals: list[tuple[str, str, AgentJobStatus]] = []

    async def list_reconcilable_portrait_tasks(
        self,
        limit: int,
        stale_before: datetime,
    ) -> list[PortraitDispatchRecord]:
        self.calls.append((limit, stale_before))
        return self.records[:limit]

    async def mark_portrait_dispatch_terminal(
        self,
        style_id: str,
        task_id: str,
        agent_status: AgentJobStatus,
    ) -> None:
        self.terminals.append((style_id, task_id, agent_status))


class Submitter:
    def __init__(
        self,
        *,
        failing_task_id: str | None = None,
        statuses: dict[str, AgentJobStatus] | None = None,
    ) -> None:
        self.failing_task_id = failing_task_id
        self.statuses = statuses or {}
        self.calls: list[dict[str, object]] = []
        self.submitted = asyncio.Event()

    async def submit(self, **kwargs: object) -> AgentJobStatus:
        self.calls.append(kwargs)
        self.submitted.set()
        if kwargs["task_id"] == self.failing_task_id:
            raise RuntimeError("模拟画像投递失败")
        return self.statuses.get(str(kwargs["task_id"]), "queued")


def record(task_id: str, status: str = "pending") -> PortraitDispatchRecord:
    return PortraitDispatchRecord(
        task_id=task_id,
        style_id="style-1",
        user_id="user-1",
        section="uniqueMarkers",
        status=status,
        updated_at=datetime(2026, 7, 14, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_portrait_dispatcher_reuses_persisted_task_identity() -> None:
    repository = Repository([record("task-pending"), record("task-processing", "processing")])
    submitter = Submitter()
    dispatcher = PortraitTaskDispatcher(repository, submitter, batch_size=10)

    assert await dispatcher.run_once() == 2
    assert submitter.calls == [
        {
            "user_id": "user-1",
            "style_id": "style-1",
            "task_id": "task-pending",
            "run_id": "task-pending",
            "section": "uniqueMarkers",
        },
        {
            "user_id": "user-1",
            "style_id": "style-1",
            "task_id": "task-processing",
            "run_id": "task-processing",
            "section": "uniqueMarkers",
        },
    ]


@pytest.mark.asyncio
async def test_portrait_dispatcher_isolates_one_submission_failure() -> None:
    repository = Repository([record("bad"), record("good")])
    submitter = Submitter(failing_task_id="bad")
    dispatcher = PortraitTaskDispatcher(repository, submitter, batch_size=10)

    assert await dispatcher.run_once() == 1
    assert [value["task_id"] for value in submitter.calls] == ["bad", "good"]


@pytest.mark.asyncio
async def test_portrait_dispatcher_converges_existing_terminal_job() -> None:
    repository = Repository([record("terminal")])
    submitter = Submitter(statuses={"terminal": "failed"})
    dispatcher = PortraitTaskDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert repository.terminals == [("style-1", "terminal", "failed")]


@pytest.mark.asyncio
async def test_portrait_dispatcher_loop_recovers_after_repository_failure() -> None:
    class FlakyRepository(Repository):
        def __init__(self) -> None:
            super().__init__([record("recovered")])
            self.failures = 0

        async def list_reconcilable_portrait_tasks(
            self,
            limit: int,
            stale_before: datetime,
        ) -> list[PortraitDispatchRecord]:
            if self.failures == 0:
                self.failures += 1
                raise RuntimeError("模拟画像数据库领取失败")
            return await super().list_reconcilable_portrait_tasks(limit, stale_before)

    repository = FlakyRepository()
    submitter = Submitter()
    dispatcher = PortraitTaskDispatcher(
        repository,
        submitter,
        batch_size=10,
        interval_seconds=0.001,
    )

    task = asyncio.create_task(dispatcher.run())
    await asyncio.wait_for(submitter.submitted.wait(), timeout=1)
    dispatcher.request_stop()
    await task

    assert [value["task_id"] for value in submitter.calls] == ["recovered"]

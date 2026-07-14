from __future__ import annotations

import asyncio

import pytest
from inkforge_core.quality.dispatcher import QualityDispatchRecord, QualityRunDispatcher


def record(run_id: str, *, message: str | None = "检查时间线") -> QualityDispatchRecord:
    return QualityDispatchRecord(
        run_id=run_id,
        check_id="check-1",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
        source_task_id="source-task-1",
        message=message,
    )


class Repository:
    def __init__(self, records: list[QualityDispatchRecord]) -> None:
        self.records = records
        self.running: list[str] = []
        self.failures: list[tuple[str, str]] = []
        self.claimed = asyncio.Event()

    async def list_dispatchable_quality_runs(self, limit: int) -> list[QualityDispatchRecord]:
        self.claimed.set()
        return self.records[:limit]

    async def mark_quality_run_running(self, run_id: str) -> None:
        self.running.append(run_id)

    async def record_quality_dispatch_failure(self, run_id: str, error_code: str) -> None:
        self.failures.append((run_id, error_code))


class Submitter:
    def __init__(self, failing_run_id: str | None = None) -> None:
        self.failing_run_id = failing_run_id
        self.calls: list[dict[str, object]] = []

    async def submit(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if kwargs["run_id"] == self.failing_run_id:
            raise RuntimeError("模拟质量检查投递失败")


@pytest.mark.asyncio
async def test_dispatcher_uses_workflow_run_as_stable_job_identity() -> None:
    repository = Repository([record("run-1")])
    submitter = Submitter()
    dispatcher = QualityRunDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert submitter.calls == [
        {
            "run_id": "run-1",
            "user_id": "user-1",
            "check_id": "check-1",
            "novel_id": "novel-1",
            "chapter_id": "chapter-1",
            "source_task_id": "source-task-1",
            "message": "检查时间线",
        }
    ]
    assert repository.running == ["run-1"]


@pytest.mark.asyncio
async def test_dispatcher_leaves_failed_run_recoverable_and_continues_batch() -> None:
    repository = Repository([record("bad"), record("good")])
    submitter = Submitter(failing_run_id="bad")
    dispatcher = QualityRunDispatcher(repository, submitter)

    assert await dispatcher.run_once() == 1
    assert repository.running == ["good"]
    assert repository.failures == [("bad", "RuntimeError")]


@pytest.mark.asyncio
async def test_dispatcher_loop_recovers_after_repository_failure() -> None:
    class FlakyRepository(Repository):
        def __init__(self) -> None:
            super().__init__([record("recovered")])
            self.failed = False

        async def list_dispatchable_quality_runs(
            self,
            limit: int,
        ) -> list[QualityDispatchRecord]:
            if not self.failed:
                self.failed = True
                raise RuntimeError("模拟质量运行领取失败")
            return await super().list_dispatchable_quality_runs(limit)

    repository = FlakyRepository()
    submitter = Submitter()
    dispatcher = QualityRunDispatcher(
        repository,
        submitter,
        interval_seconds=0.001,
    )

    task = asyncio.create_task(dispatcher.run())
    await asyncio.wait_for(repository.claimed.wait(), timeout=1)
    dispatcher.request_stop()
    await task

    assert repository.running == ["recovered"]

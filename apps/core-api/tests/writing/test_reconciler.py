from __future__ import annotations

import pytest
from inkforge_core.writing.reconciler import WritingRunReconciler
from inkforge_core.writing.tasks import TaskRecord


class Repository:
    def __init__(self, tasks: list[TaskRecord]) -> None:
        self.tasks = tasks

    async def list_reconcilable(self, limit: int) -> list[TaskRecord]:
        return self.tasks[:limit]


class Submitter:
    def __init__(self) -> None:
        self.tasks: list[str] = []

    async def reconcile(self, task: TaskRecord) -> None:
        self.tasks.append(task.id)


@pytest.mark.asyncio
async def test_reconciler_force_resubmits_all_nonterminal_database_tasks() -> None:
    tasks = [
        TaskRecord("task-1", "user-1", "novel-1", "chapter-1", None, "idle", None),
        TaskRecord("task-2", "user-1", "novel-1", "chapter-1", None, "waiting_user", "{}"),
    ]
    submitter = Submitter()
    reconciler = WritingRunReconciler(Repository(tasks), submitter, batch_size=10)

    assert await reconciler.run_once() == 2
    assert submitter.tasks == ["task-1", "task-2"]


@pytest.mark.asyncio
async def test_reconciler_continues_after_one_submission_failure() -> None:
    tasks = [
        TaskRecord("bad", "user-1", "novel-1", "chapter-1", None, "idle", None),
        TaskRecord("good", "user-1", "novel-1", "chapter-1", None, "idle", None),
    ]

    class PartialSubmitter(Submitter):
        async def reconcile(self, task: TaskRecord) -> None:
            if task.id == "bad":
                raise RuntimeError("暂时失败")
            await super().reconcile(task)

    submitter = PartialSubmitter()
    reconciler = WritingRunReconciler(Repository(tasks), submitter, batch_size=10)

    assert await reconciler.run_once() == 1
    assert submitter.tasks == ["good"]

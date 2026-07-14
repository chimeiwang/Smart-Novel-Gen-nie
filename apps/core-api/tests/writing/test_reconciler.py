from __future__ import annotations

import pytest
from inkforge_core.db.models import WritingTask
from inkforge_core.writing.reconciler import WritingRunReconciler
from inkforge_core.writing.records import TaskRecord
from inkforge_core.writing.tasks import WritingTaskRepository
from sqlalchemy.dialects import postgresql


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


class EmptyRows:
    def all(self) -> list[object]:
        return []


class QuerySession:
    def __init__(self) -> None:
        self.statement: object | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def execute(self, statement):
        self.statement = statement
        return EmptyRows()


@pytest.mark.asyncio
async def test_legacy_reconciliation_excludes_review_waiting_and_active_commands() -> None:
    session = QuerySession()
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    assert await repository.list_reconcilable(10) == []

    assert session.statement is not None
    compiled = session.statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    phase_values = next(
        value
        for key, value in compiled.params.items()
        if key.startswith("phase_") and isinstance(value, list)
    )
    assert set(phase_values) == {"active", "waiting_call"}
    assert "NOT (EXISTS" in sql
    assert '"WritingRunCommand"' in sql
    assert WritingTask.__tablename__ in sql

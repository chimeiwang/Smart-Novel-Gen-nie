from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from inkforge_contracts.jobs import AgentJobStatus
from inkforge_core.db.models import WritingTask
from inkforge_core.writing.reconciler import WritingRunReconciler
from inkforge_core.writing.records import TaskRecord
from inkforge_core.writing.tasks import WritingTaskRepository
from sqlalchemy.dialects import postgresql


class Repository:
    def __init__(self, tasks: list[TaskRecord]) -> None:
        self.tasks = tasks
        self.terminals: list[tuple[str, AgentJobStatus]] = []

    async def list_reconcilable(self, limit: int) -> list[TaskRecord]:
        return self.tasks[:limit]

    async def settle_reconciliation_terminal(
        self,
        task: TaskRecord,
        agent_status: AgentJobStatus,
    ) -> None:
        self.terminals.append((task.id, agent_status))


class Submitter:
    def __init__(self, statuses: dict[str, AgentJobStatus] | None = None) -> None:
        self.tasks: list[str] = []
        self.statuses = statuses or {}

    async def reconcile(self, task: TaskRecord) -> AgentJobStatus:
        self.tasks.append(task.id)
        return self.statuses.get(task.id, "queued")


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
        async def reconcile(self, task: TaskRecord) -> AgentJobStatus:
            if task.id == "bad":
                raise RuntimeError("暂时失败")
            return await super().reconcile(task)

    submitter = PartialSubmitter()
    reconciler = WritingRunReconciler(Repository(tasks), submitter, batch_size=10)

    assert await reconciler.run_once() == 1
    assert submitter.tasks == ["good"]


@pytest.mark.asyncio
async def test_reconciler_converges_existing_terminal_job() -> None:
    current = TaskRecord(
        "terminal", "user-1", "novel-1", "chapter-1", None, "active", "{}"
    )
    repository = Repository([current])
    submitter = Submitter({"terminal": "completed"})

    assert await WritingRunReconciler(repository, submitter).run_once() == 1
    assert repository.terminals == [("terminal", "completed")]


@pytest.mark.asyncio
async def test_reconciler_loop_recovers_after_one_repository_failure() -> None:
    expected = TaskRecord(
        "recovered",
        "user-1",
        "novel-1",
        "chapter-1",
        None,
        "idle",
        None,
    )

    class FlakyRepository:
        def __init__(self) -> None:
            self.calls = 0

        async def list_reconcilable(self, limit: int) -> list[TaskRecord]:
            assert limit == 10
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("模拟数据库领取失败")
            return [expected]

    class StoppingSubmitter(Submitter):
        def __init__(self) -> None:
            super().__init__()
            self.completed = asyncio.Event()

        async def reconcile(self, task: TaskRecord) -> AgentJobStatus:
            status = await super().reconcile(task)
            self.completed.set()
            return status

    repository = FlakyRepository()
    submitter = StoppingSubmitter()
    reconciler = WritingRunReconciler(
        repository,
        submitter,
        batch_size=10,
        interval_seconds=0.001,
    )

    task = asyncio.create_task(reconciler.run())
    await asyncio.wait_for(submitter.completed.wait(), timeout=1)
    reconciler.request_stop()
    await task

    assert repository.calls >= 2
    assert submitter.tasks == ["recovered"]


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


class SettlementSession:
    def __init__(self, model: WritingTask, active_command_id: str | None = None) -> None:
        self.model = model
        self.active_command_id = active_command_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield

    async def get(self, model_type, task_id, *, with_for_update=False):
        assert model_type is WritingTask
        assert task_id == self.model.id
        assert with_for_update is True
        return self.model

    async def scalar(self, statement):
        del statement
        return self.active_command_id


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


@pytest.mark.asyncio
async def test_terminal_reconciliation_rejects_changed_graph_snapshot() -> None:
    model = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="active",
        graphStateJson='{"version":2}',
    )
    expected = TaskRecord(
        "task-1",
        "user-1",
        "novel-1",
        "chapter-1",
        None,
        "active",
        '{"version":1}',
    )
    repository = WritingTaskRepository(  # type: ignore[arg-type]
        lambda: SettlementSession(model)
    )

    await repository.settle_reconciliation_terminal(expected, "failed")

    assert model.phase == "active"
    assert model.graphStateJson == '{"version":2}'


@pytest.mark.asyncio
async def test_terminal_reconciliation_marks_unchanged_task_error() -> None:
    model = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="waiting_call",
        graphStateJson='{"phase":"waiting_call"}',
    )
    expected = TaskRecord(
        "task-1",
        "user-1",
        "novel-1",
        "chapter-1",
        None,
        "waiting_call",
        '{"phase":"waiting_call"}',
    )
    repository = WritingTaskRepository(  # type: ignore[arg-type]
        lambda: SettlementSession(model)
    )

    await repository.settle_reconciliation_terminal(expected, "cancelled")

    assert model.phase == "error"

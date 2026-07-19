from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from inkforge_core.db.models import WritingBible, WritingRunCommand, WritingTask
from inkforge_core.errors import ApiError
from inkforge_core.writing.reconciler import WritingRunReconciler
from inkforge_core.writing.records import TaskRecord
from inkforge_core.writing.tasks import WritingTaskRepository
from sqlalchemy.dialects import postgresql


class Repository:
    def __init__(self, tasks: list[TaskRecord]) -> None:
        self.tasks = tasks
        self.created: list[str] = []

    async def list_reconcilable(self, limit: int) -> list[TaskRecord]:
        return self.tasks[:limit]

    async def create_reconciliation_command(self, task: TaskRecord) -> bool:
        self.created.append(task.id)
        return True


class Dispatcher:
    def __init__(self) -> None:
        self.calls = 0

    async def run_once(self) -> int:
        self.calls += 1
        return 1


@pytest.mark.asyncio
async def test_reconciler_persists_command_before_immediate_dispatch() -> None:
    order: list[str] = []
    current = TaskRecord(
        "task-1", "user-1", "novel-1", "chapter-1", None, "active", "{}"
    )

    class CommandRepository:
        async def list_reconcilable(self, limit: int) -> list[TaskRecord]:
            assert limit == 10
            return [current]

        async def create_reconciliation_command(self, task: TaskRecord) -> bool:
            assert task == current
            order.append("database")
            return True

    class Dispatcher:
        async def run_once(self) -> int:
            order.append("dispatch")
            return 1

    reconciler = WritingRunReconciler(
        CommandRepository(),  # type: ignore[arg-type]
        Dispatcher(),  # type: ignore[arg-type]
        batch_size=10,
    )

    assert await reconciler.run_once() == 1
    assert order == ["database", "dispatch"]


@pytest.mark.asyncio
async def test_reconciler_force_resubmits_all_nonterminal_database_tasks() -> None:
    tasks = [
        TaskRecord("task-1", "user-1", "novel-1", "chapter-1", None, "idle", None),
        TaskRecord("task-2", "user-1", "novel-1", "chapter-1", None, "waiting_user", "{}"),
    ]
    repository = Repository(tasks)
    dispatcher = Dispatcher()
    reconciler = WritingRunReconciler(repository, dispatcher, batch_size=10)

    assert await reconciler.run_once() == 2
    assert repository.created == ["task-1", "task-2"]
    assert dispatcher.calls == 1


@pytest.mark.asyncio
async def test_reconciler_continues_after_one_submission_failure() -> None:
    tasks = [
        TaskRecord("bad", "user-1", "novel-1", "chapter-1", None, "idle", None),
        TaskRecord("good", "user-1", "novel-1", "chapter-1", None, "idle", None),
    ]

    class PartialRepository(Repository):
        async def create_reconciliation_command(self, task: TaskRecord) -> bool:
            if task.id == "bad":
                raise ConnectionError("数据库暂时不可用")
            return await super().create_reconciliation_command(task)

    repository = PartialRepository(tasks)
    dispatcher = Dispatcher()
    reconciler = WritingRunReconciler(repository, dispatcher, batch_size=10)

    assert await reconciler.run_once() == 1
    assert repository.created == ["good"]
    assert dispatcher.calls == 1


@pytest.mark.asyncio
async def test_reconciler_propagates_deterministic_submission_error() -> None:
    current = TaskRecord(
        "invalid", "user-1", "novel-1", "chapter-1", None, "idle", None
    )

    class InvalidRepository(Repository):
        async def create_reconciliation_command(self, task: TaskRecord) -> bool:
            del task
            raise TypeError("对账命令契约错误")

    reconciler = WritingRunReconciler(
        InvalidRepository([current]),
        Dispatcher(),
    )

    with pytest.raises(TypeError, match="对账命令契约错误"):
        await reconciler.run_once()


@pytest.mark.asyncio
async def test_reconciler_does_not_dispatch_when_command_was_not_created() -> None:
    current = TaskRecord(
        "terminal", "user-1", "novel-1", "chapter-1", None, "active", "{}"
    )
    class ExistingRepository(Repository):
        async def create_reconciliation_command(self, task: TaskRecord) -> bool:
            del task
            return False

    dispatcher = Dispatcher()
    assert (
        await WritingRunReconciler(
            ExistingRepository([current]),
            dispatcher,
        ).run_once()
        == 0
    )
    assert dispatcher.calls == 0


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
                raise ConnectionError("对账任务领取暂时失败")
            return [expected]

        async def create_reconciliation_command(self, task: TaskRecord) -> bool:
            assert task == expected
            return True

    class StoppingDispatcher(Dispatcher):
        def __init__(self) -> None:
            super().__init__()
            self.completed = asyncio.Event()

        async def run_once(self) -> int:
            completed = await super().run_once()
            self.completed.set()
            return completed

    repository = FlakyRepository()
    dispatcher = StoppingDispatcher()
    reconciler = WritingRunReconciler(
        repository,
        dispatcher,
        batch_size=10,
        interval_seconds=0.001,
    )

    task = asyncio.create_task(reconciler.run())
    await asyncio.wait_for(dispatcher.completed.wait(), timeout=1)
    reconciler.request_stop()
    await task

    assert repository.calls >= 2
    assert dispatcher.calls == 1


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


class ReconciliationCommandSession(SettlementSession):
    def __init__(
        self,
        model: WritingTask,
        *,
        bible: WritingBible | None = None,
        latest_payload: str | None = None,
    ) -> None:
        super().__init__(model)
        self.commands: dict[str, WritingRunCommand] = {}
        self.bible = bible
        self.latest_payload = latest_payload

    async def get(self, model_type, identifier, *, with_for_update=False):
        assert with_for_update is True
        if model_type is WritingTask:
            assert identifier == self.model.id
            return self.model
        if model_type is WritingRunCommand:
            return self.commands.get(identifier)
        raise AssertionError(model_type)

    def add(self, value: object) -> None:
        assert isinstance(value, WritingRunCommand)
        self.commands[value.id] = value
        self.active_command_id = value.id

    async def flush(self) -> None:
        return None

    async def scalar(self, statement):
        source = str(statement)
        if '"WritingBible"' in source:
            return self.bible
        if '"WritingRunCommand"."payloadJson"' in source:
            return self.latest_payload
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


@pytest.mark.asyncio
async def test_reconciliation_creates_single_command_and_invalidates_old_legacy_job() -> None:
    graph_state = '{"eventSequence":20,"callbackJobId":"writing-old"}'
    model = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId="session-1",
        phase="active",
        selectedAgents="写作,编辑",
        targetWordCount=4000,
        graphStateJson=graph_state,
    )
    expected = TaskRecord(
        "task-1",
        "user-1",
        "novel-1",
        "chapter-1",
        "session-1",
        "active",
        graph_state,
    )
    session = ReconciliationCommandSession(model)
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    created = await repository.create_reconciliation_command(expected)
    duplicate = await repository.create_reconciliation_command(expected)
    command = next(iter(session.commands.values()))
    old_authorization = await repository.authorize_callback(model.id, "writing-old")
    new_authorization = await repository.authorize_callback(model.id, command.id)

    assert created is True
    assert duplicate is False
    assert len(session.commands) == 1
    assert command.taskId == model.id
    assert command.status == "pending"
    assert command.id != "writing-old"
    payload = json.loads(command.payloadJson)
    assert payload["workflowKind"] == "long_serial"
    assert payload["operation"] is None
    assert payload["source"] is None
    assert old_authorization.accepted is False
    assert new_authorization.accepted is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "source"),
    [
        (
            "develop_short_outline",
            {
                "kind": "short_outline_inspiration",
                "originalInspiration": "城市每天忘记一个人",
            },
        ),
        (
            "write_short_story",
            {
                "kind": "approved_short_outline",
                "outlineArtifactId": "outline-1",
                "outlineRevision": 3,
                "outlineHash": "a" * 64,
            },
        ),
    ],
)
@pytest.mark.parametrize("target", [None, 6000])
async def test_short_reconciliation_copies_latest_persisted_workflow_identity(
    operation: str,
    source: dict[str, object],
    target: int | None,
) -> None:
    latest_payload = json.dumps(
        {
            "version": 1,
            "resume": False,
            "chapterId": "chapter-1",
            "writingSessionId": "session-1",
            "resumeInput": None,
            "workflowKind": "short_medium",
            "operation": operation,
            "targetTotalWordCount": target,
            "source": source,
        },
        ensure_ascii=False,
    )
    model = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId="session-1",
        phase="active",
        selectedAgents="剧情",
        targetWordCount=target or 80_000,
        graphStateJson='{"phase":"active"}',
    )
    expected = TaskRecord(
        "task-1",
        "user-1",
        "novel-1",
        "chapter-1",
        "session-1",
        "active",
        '{"phase":"active"}',
    )
    session = ReconciliationCommandSession(
        model,
        bible=WritingBible(
            id="bible-1",
            novelId="novel-1",
            storyLengthProfile="short_medium",
            targetTotalWordCount=target,
        ),
        latest_payload=latest_payload,
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    assert await repository.create_reconciliation_command(expected) is True

    command = next(iter(session.commands.values()))
    payload = json.loads(command.payloadJson)
    assert payload["workflowKind"] == "short_medium"
    assert payload["operation"] == operation
    assert payload["targetTotalWordCount"] == target
    assert payload["source"] == source


@pytest.mark.asyncio
async def test_long_legacy_reconciliation_remains_long_serial() -> None:
    model = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="active",
        targetWordCount=4000,
        graphStateJson='{"phase":"active"}',
    )
    expected = TaskRecord(
        "task-1",
        "user-1",
        "novel-1",
        "chapter-1",
        None,
        "active",
        '{"phase":"active"}',
    )
    session = ReconciliationCommandSession(
        model,
        bible=WritingBible(
            id="bible-1",
            novelId="novel-1",
            storyLengthProfile="long_serial",
            targetTotalWordCount=1_000_000,
        ),
        latest_payload=json.dumps(
            {
                "version": 1,
                "resume": True,
                "chapterId": "chapter-1",
                "writingSessionId": None,
                "resumeInput": None,
            }
        ),
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    assert await repository.create_reconciliation_command(expected) is True

    command = next(iter(session.commands.values()))
    payload = json.loads(command.payloadJson)
    assert payload["workflowKind"] == "long_serial"
    assert payload["operation"] is None
    assert payload["targetTotalWordCount"] == 1_000_000
    assert payload["source"] is None


@pytest.mark.asyncio
async def test_short_reconciliation_rejects_legacy_command_without_workflow_identity() -> None:
    model = WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        phase="waiting_call",
        targetWordCount=6000,
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
    session = ReconciliationCommandSession(
        model,
        bible=WritingBible(
            id="bible-1",
            novelId="novel-1",
            storyLengthProfile="short_medium",
            targetTotalWordCount=6000,
        ),
        latest_payload=json.dumps(
            {
                "version": 1,
                "resume": True,
                "chapterId": "chapter-1",
                "writingSessionId": None,
                "resumeInput": None,
            }
        ),
    )
    repository = WritingTaskRepository(lambda: session)  # type: ignore[arg-type]

    with pytest.raises(ApiError) as caught:
        await repository.create_reconciliation_command(expected)

    assert caught.value.code == "WRITING_RECONCILIATION_IDENTITY_MISSING"
    assert session.commands == {}

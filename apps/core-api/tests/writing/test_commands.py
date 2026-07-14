from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from inkforge_core.db.base import utc_now
from inkforge_core.db.models import WritingRunCommand, WritingTask
from inkforge_core.errors import ApiError
from inkforge_core.writing.commands import (
    WritingRunCommandRepository,
    command_idempotency_key,
)
from sqlalchemy.dialects import postgresql


class RowResult:
    def __init__(self, row: tuple[object, ...] | None) -> None:
        self._row = row

    def one_or_none(self) -> tuple[object, ...] | None:
        return self._row


class RowsResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class CommandSession:
    def __init__(self, execute_results: list[object] | None = None) -> None:
        self.execute_results = list(execute_results or [])
        self.added: list[object] = []
        self.statements: list[object] = []
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> CommandSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True

    def begin_nested(self):
        return self.begin()

    async def execute(self, statement: object) -> object:
        self.statements.append(statement)
        if not self.execute_results:
            raise AssertionError("收到未预期的数据库查询")
        return self.execute_results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


class SessionFactory:
    def __init__(self, sessions: list[CommandSession]) -> None:
        self.sessions = sessions

    def __call__(self) -> CommandSession:
        if not self.sessions:
            raise AssertionError("收到未预期的数据库会话")
        return self.sessions.pop(0)


def task() -> WritingTask:
    now = utc_now()
    return WritingTask(
        id="task-1",
        novelId="novel-1",
        chapterId="chapter-1",
        writingSessionId="session-1",
        phase="active",
        selectedAgents="写作,编辑",
        targetWordCount=4000,
        createdAt=now,
        updatedAt=now,
    )


def command(
    *,
    command_id: str = "command-1",
    client_request_id: str = "request-00000001",
    status: str = "pending",
    next_attempt_at: datetime | None = None,
) -> WritingRunCommand:
    now = utc_now()
    return WritingRunCommand(
        id=command_id,
        taskId="task-1",
        kind="resume",
        payloadJson='{"version":1,"resume":true}',
        idempotencyKey=command_idempotency_key("user-1", client_request_id),
        status=status,
        attemptCount=0,
        nextAttemptAt=next_attempt_at or now,
        createdAt=now,
        updatedAt=now,
    )


@pytest.mark.asyncio
async def test_same_client_request_returns_existing_command() -> None:
    owned_task = task()
    first_session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
        ]
    )
    factory = SessionFactory([first_session])
    repository = WritingRunCommandRepository(factory)  # type: ignore[arg-type]

    first = await repository.create_resume(
        "user-1", "task-1", "request-00000001", {"userMessage": "继续"}
    )
    persisted = first_session.added[0]
    factory.sessions.append(CommandSession([RowResult((persisted, owned_task, "user-1"))]))
    second = await repository.create_resume(
        "user-1", "task-1", "request-00000001", {"userMessage": "继续"}
    )

    assert second.id == first.id
    assert second.status == "pending"
    assert len(first_session.added) == 1


@pytest.mark.asyncio
async def test_task_allows_only_one_active_command() -> None:
    owned_task = task()
    session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(("command-active",)),
        ]
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    with pytest.raises(ApiError) as captured:
        await repository.create_resume(
            "user-1", "task-1", "request-00000002", {"userMessage": "继续"}
        )

    assert captured.value.status_code == 409
    assert captured.value.code == "WRITING_COMMAND_ACTIVE"
    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_claim_due_uses_skip_locked_and_returns_task_context() -> None:
    due = command(next_attempt_at=utc_now() - timedelta(seconds=1))
    owned_task = task()
    session = CommandSession([RowsResult([(due, owned_task, "user-1")])])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    records = await repository.claim_due(limit=10)

    assert [record.id for record in records] == ["command-1"]
    assert records[0].task.user_id == "user-1"
    rendered = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in rendered
    assert "SKIP LOCKED" in rendered


@pytest.mark.asyncio
async def test_command_status_transitions_are_idempotent() -> None:
    model = command()
    sessions = [
        CommandSession([RowResult((model, task(), "user-1"))]),
        CommandSession([RowResult((model, task(), "user-1"))]),
        CommandSession([RowResult((model, task(), "user-1"))]),
        CommandSession([RowResult((model, task(), "user-1"))]),
    ]
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(sessions)
    )

    submitted = await repository.mark_submitted("command-1")
    processing = await repository.mark_processing("command-1")
    succeeded = await repository.mark_succeeded("command-1", {"accepted": True})
    repeated = await repository.mark_succeeded("command-1", {"accepted": True})

    assert submitted.status == "submitted"
    assert processing.status == "processing"
    assert succeeded.status == "succeeded"
    assert repeated.status == "succeeded"
    assert model.completedAt is not None
    assert model.resultJson == '{"accepted":true}'


@pytest.mark.asyncio
async def test_dispatch_failure_records_only_error_code_and_backs_off() -> None:
    model = command()
    previous_attempt = model.nextAttemptAt
    session = CommandSession([RowResult((model, task(), "user-1"))])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    record = await repository.record_dispatch_failure(
        "command-1", "AgentRunSubmitFailed"
    )

    assert record.status == "pending"
    assert record.attempt_count == 1
    assert model.lastError == "AgentRunSubmitFailed"
    assert model.nextAttemptAt > previous_attempt
    assert model.nextAttemptAt <= previous_attempt + timedelta(seconds=3)


def test_command_idempotency_key_is_user_scoped() -> None:
    assert command_idempotency_key("user-1", "request-1") == "user-1:request-1"
    assert command_idempotency_key("user-2", "request-1") != command_idempotency_key(
        "user-1", "request-1"
    )

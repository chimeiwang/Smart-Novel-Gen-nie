from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from inkforge_core.db.base import utc_now
from inkforge_core.db.models import (
    WritingMessage,
    WritingRunCommand,
    WritingSession,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.writing.commands import (
    WritingRunCommandRepository,
    command_idempotency_key,
)
from inkforge_core.writing.schemas import ResumeWritingRunRequest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError


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

    async def scalar(self, statement: object) -> object | None:
        result = await self.execute(statement)
        if not isinstance(result, RowResult):
            raise AssertionError("scalar 查询必须返回 RowResult")
        if result._row is None:
            return None
        return result._row[0]

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def get(self, _model: object, _identifier: str) -> None:
        return None


class RacingCommandSession(CommandSession):
    async def flush(self) -> None:
        if any(isinstance(item, WritingRunCommand) for item in self.added):
            raise IntegrityError("INSERT", {}, RuntimeError("duplicate"))


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
async def test_require_owned_task_keeps_lock_in_enclosing_transaction() -> None:
    owned_task = task()
    session = CommandSession([RowResult((owned_task, "user-1"))])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    result = await repository.require_owned_task("user-1", "task-1")

    assert result.id == "task-1"
    assert session.committed is True
    rendered = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert 'FOR UPDATE OF "WritingTask"' in rendered


@pytest.mark.asyncio
async def test_same_client_request_returns_existing_command() -> None:
    owned_task = task()
    first_session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
            RowResult(None),
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
async def test_internal_resume_idempotency_ignores_later_task_session_binding() -> None:
    rebound_task = task()
    rebound_task.writingSessionId = "session-later"
    existing = command()
    existing.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "writingSessionId": None,
            "resumeInput": {"userMessage": "继续"},
        }
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(
            [CommandSession([RowResult((existing, rebound_task, "user-1"))])]
        )
    )

    result = await repository.create_resume(
        "user-1",
        "task-1",
        "request-00000001",
        {"userMessage": "继续"},
    )

    assert result.id == existing.id


@pytest.mark.asyncio
async def test_task_allows_only_one_active_command() -> None:
    owned_task = task()
    session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
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
async def test_resume_with_message_rejects_same_key_with_different_raw_message() -> None:
    existing = command()
    existing.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "resumeInput": {"userMessage": "只修改第二节"},
        },
        ensure_ascii=False,
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([CommandSession([RowResult((existing, task(), "user-1"))])])
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_resume_with_message(
            "user-1",
            "task-1",
            ResumeWritingRunRequest(
                clientRequestId="request-00000001",
                writingSessionId="session-1",
                userMessage="只修改第三节",
            ),
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_resume_with_message_same_key_session_and_message_returns_existing() -> None:
    existing = command()
    existing.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "writingSessionId": "session-1",
            "resumeInput": {"userMessage": "继续"},
        }
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([CommandSession([RowResult((existing, task(), "user-1"))])])
    )

    result = await repository.create_resume_with_message(
        "user-1",
        "task-1",
        ResumeWritingRunRequest(
            clientRequestId="request-00000001",
            writingSessionId="session-1",
            userMessage="继续",
        ),
    )

    assert result.commandId == existing.id
    assert result.commandStatus == existing.status


@pytest.mark.asyncio
async def test_resume_with_message_rejects_same_key_with_different_session() -> None:
    existing = command()
    existing.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "writingSessionId": "session-1",
            "resumeInput": {"userMessage": "继续"},
        }
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([CommandSession([RowResult((existing, task(), "user-1"))])])
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_resume_with_message(
            "user-1",
            "task-1",
            ResumeWritingRunRequest(
                clientRequestId="request-00000001",
                writingSessionId="session-2",
                userMessage="继续",
            ),
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_resume_session_semantics_are_rechecked_after_task_lock() -> None:
    owned_task = task()
    owned_task.writingSessionId = "session-2"
    existing = command()
    existing.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "writingSessionId": "session-1",
            "resumeInput": {"userMessage": "继续"},
        }
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(
            [
                CommandSession([RowResult(None)]),
                CommandSession(
                    [
                        RowResult(None),
                        RowResult((owned_task, "user-1")),
                        RowResult((existing, owned_task, "user-1")),
                    ]
                ),
            ]
        )
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_resume_with_message(
            "user-1",
            "task-1",
            ResumeWritingRunRequest(
                clientRequestId="request-00000001",
                writingSessionId="session-2",
                userMessage="继续",
            ),
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_resume_session_semantics_are_rechecked_after_integrity_race() -> None:
    owned_task = task()
    owned_task.writingSessionId = "session-2"
    raced = command()
    raced.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "writingSessionId": "session-1",
            "resumeInput": {"userMessage": "继续"},
        }
    )
    creation_session = RacingCommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
            RowResult(None),
            RowResult(None),
        ]
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(
            [
                CommandSession([RowResult(None)]),
                creation_session,
                CommandSession([RowResult((raced, owned_task, "user-1"))]),
            ]
        )
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_resume_with_message(
            "user-1",
            "task-1",
            ResumeWritingRunRequest(
                clientRequestId="request-00000001",
                writingSessionId="session-2",
                userMessage="继续",
            ),
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_resume_with_message_persists_unmodified_user_text() -> None:
    owned_task = task()
    creation_session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
            RowResult(None),
            RowResult(None),
        ]
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory(
            [
                CommandSession([RowResult(None)]),
                creation_session,
            ]
        )
    )

    await repository.create_resume_with_message(
        "user-1",
        "task-1",
        ResumeWritingRunRequest(
            clientRequestId="request-00000001",
            writingSessionId="session-1",
            userMessage="  只修改第二节，不要改结尾。  ",
        ),
    )

    message = next(
        item for item in creation_session.added if isinstance(item, WritingMessage)
    )
    persisted_command = next(
        item for item in creation_session.added if isinstance(item, WritingRunCommand)
    )
    assert message.content == "  只修改第二节，不要改结尾。  "
    assert json.loads(persisted_command.payloadJson)["resumeInput"]["userMessage"] == (
        "  只修改第二节，不要改结尾。  "
    )


@pytest.mark.asyncio
async def test_resume_rechecks_semantics_after_task_lock() -> None:
    owned_task = task()
    existing = command()
    existing.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "resumeInput": {"userMessage": "旧修改要求"},
        },
        ensure_ascii=False,
    )
    session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult((existing, owned_task, "user-1")),
        ]
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_resume(
            "user-1",
            "task-1",
            "request-00000001",
            {"userMessage": "新修改要求"},
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_resume_integrity_race_rechecks_full_semantics() -> None:
    owned_task = task()
    raced = command()
    raced.payloadJson = json.dumps(
        {
            "version": 1,
            "resume": True,
            "resumeInput": {"userMessage": "竞争请求"},
        },
        ensure_ascii=False,
    )
    session = RacingCommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
            RowResult(None),
            RowResult(None),
            RowResult((raced, owned_task, "user-1")),
        ]
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_resume(
            "user-1",
            "task-1",
            "request-00000001",
            {"userMessage": "当前请求"},
        )

    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_claim_due_uses_skip_locked_and_returns_task_context() -> None:
    due = command(next_attempt_at=utc_now() - timedelta(seconds=1))
    owned_task = task()
    session = CommandSession([RowsResult([(due, owned_task, "user-1")])])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    stale_before = utc_now() - timedelta(minutes=10)
    records = await repository.claim_due(
        limit=10,
        active_stale_before=stale_before,
    )

    assert [record.id for record in records] == ["command-1"]
    assert records[0].task.user_id == "user-1"
    rendered = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in rendered
    assert "SKIP LOCKED" in rendered
    params = session.statements[0].compile(dialect=postgresql.dialect()).params
    assert any(
        isinstance(value, list) and set(value) == {"submitted", "processing"}
        for value in params.values()
    )
    assert stale_before in params.values()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "submitted", "processing"])
async def test_agent_terminal_settles_active_command_and_task(status: str) -> None:
    model = command(status=status)
    owned_task = task()
    owned_task.graphStateJson = '{"phase":"active"}'
    row = (model, owned_task, "user-1")
    session = CommandSession([RowResult(row), RowResult(row)])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    record = await repository.settle_dispatch_terminal("command-1", "failed")

    assert record.status == "failed"
    assert model.lastError == "AGENT_JOB_TERMINAL_FAILED"
    assert owned_task.phase == "error"
    assert json.loads(owned_task.graphStateJson or "{}")["errorMessage"] == (
        "智能体运行失败：AGENT_JOB_TERMINAL_FAILED"
    )
    rendered = [
        str(statement.compile(dialect=postgresql.dialect())) for statement in session.statements
    ]
    assert 'FOR UPDATE OF "WritingTask"' in rendered[0]
    assert 'FOR UPDATE OF "WritingRunCommand"' in rendered[1]


@pytest.mark.asyncio
async def test_agent_terminal_does_not_overwrite_succeeded_command_or_completed_task() -> None:
    model = command(status="succeeded")
    owned_task = task()
    owned_task.phase = "completed"
    row = (model, owned_task, "user-1")
    session = CommandSession([RowResult(row), RowResult(row)])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    record = await repository.settle_dispatch_terminal("command-1", "failed")

    assert record.status == "succeeded"
    assert owned_task.phase == "completed"


@pytest.mark.asyncio
async def test_agent_terminal_closes_active_command_for_completed_task() -> None:
    model = command(status="processing")
    owned_task = task()
    owned_task.phase = "completed"
    row = (model, owned_task, "user-1")
    session = CommandSession([RowResult(row), RowResult(row)])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    record = await repository.settle_dispatch_terminal("command-1", "failed")

    assert record.status == "succeeded"
    assert model.lastError is None
    assert owned_task.phase == "completed"


@pytest.mark.asyncio
async def test_agent_terminal_preserves_artifact_decision_idempotency_result() -> None:
    model = command(status="submitted")
    model.kind = "artifact_decision"
    model.resultJson = '{"artifactId":"artifact-1","accepted":true}'
    owned_task = task()
    row = (model, owned_task, "user-1")
    session = CommandSession([RowResult(row), RowResult(row)])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    record = await repository.settle_dispatch_terminal("command-1", "cancelled")

    assert record.status == "failed"
    assert record.result == {"artifactId": "artifact-1", "accepted": True}
    assert model.resultJson == '{"artifactId":"artifact-1","accepted":true}'


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

    record = await repository.record_dispatch_failure("command-1", "AgentRunSubmitFailed")

    assert record.status == "pending"
    assert record.attempt_count == 1
    assert model.lastError == "AgentRunSubmitFailed"
    assert model.nextAttemptAt > previous_attempt
    assert model.nextAttemptAt <= previous_attempt + timedelta(seconds=3)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["submitted", "processing"])
async def test_active_command_dispatch_failure_refreshes_reconciliation_age(
    status: str,
) -> None:
    model = command(status=status)
    previous_updated_at = model.updatedAt
    session = CommandSession([RowResult((model, task(), "user-1"))])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    record = await repository.record_dispatch_failure("command-1", "AgentUnavailable")

    assert record.status == status
    assert record.attempt_count == 1
    assert model.lastError == "AgentUnavailable"
    assert model.updatedAt >= previous_updated_at


def test_command_idempotency_key_is_user_scoped() -> None:
    assert command_idempotency_key("user-1", "request-1") == "user-1:request-1"
    assert command_idempotency_key("user-2", "request-1") != command_idempotency_key(
        "user-1", "request-1"
    )


@pytest.mark.asyncio
async def test_revise_decision_persists_raw_revision_focus_once_with_command() -> None:
    owned_task = task()
    session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
            RowResult(None),
            RowResult(None),
        ]
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )
    payload = {
        "version": 1,
        "resume": True,
        "resumeInput": {
            "artifactId": "artifact-1",
            "decision": "revise",
            "expectedRevision": 3,
            "userMessage": "  第三节不要让主角妥协。  ",
        },
        "decisionRequest": {
            "artifactId": "artifact-1",
            "decision": "revise",
            "expectedRevision": 3,
            "editedContent": None,
            "selectedUpdateRefs": None,
            "userMessage": "  第三节不要让主角妥协。  ",
        },
    }

    await repository.create_artifact_decision(
        command_id="command-1",
        user_id="user-1",
        task_id="task-1",
        artifact_id="artifact-1",
        decision="revise",
        client_request_id="request-00000001",
        payload=payload,
        result={"artifactId": "artifact-1"},
    )

    messages = [item for item in session.added if isinstance(item, WritingMessage)]
    commands = [item for item in session.added if isinstance(item, WritingRunCommand)]
    assert len(messages) == 1
    assert len(commands) == 1
    assert messages[0].content == "  第三节不要让主角妥协。  "
    metadata = json.loads(messages[0].metadata_ or "{}")
    assert metadata["eventType"] == "revision_focus"
    assert metadata["intent"] == "revision_focus"
    assert metadata["artifactId"] == "artifact-1"
    assert metadata["sourceRevision"] == 3
    assert metadata["taskId"] == "task-1"
    assert metadata["contentHash"]


@pytest.mark.asyncio
async def test_non_revise_decision_does_not_persist_revision_focus_message() -> None:
    owned_task = task()
    session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
            RowResult(None),
            RowResult(None),
        ]
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )
    await repository.create_artifact_decision(
        command_id="command-1",
        user_id="user-1",
        task_id="task-1",
        artifact_id="artifact-1",
        decision="approve",
        client_request_id="request-00000001",
        payload={
            "decisionRequest": {
                "artifactId": "artifact-1",
                "decision": "approve",
                "expectedRevision": 1,
                "userMessage": "批准",
            }
        },
        result={"artifactId": "artifact-1"},
    )
    assert not any(isinstance(item, WritingMessage) for item in session.added)


@pytest.mark.asyncio
async def test_artifact_decision_repository_rejects_raced_semantic_key_reuse() -> None:
    existing = command()
    existing.kind = "artifact_decision"
    existing.artifactId = "artifact-1"
    existing.decision = "discard"
    existing.payloadJson = json.dumps(
        {
            "decisionRequest": {
                "artifactId": "artifact-1",
                "decision": "discard",
                "expectedRevision": 1,
                "userMessage": None,
            }
        }
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([CommandSession([RowResult((existing, task(), "user-1"))])])
    )

    with pytest.raises(ApiError) as caught:
        await repository.create_artifact_decision(
            command_id="command-2",
            user_id="user-1",
            task_id="task-1",
            artifact_id="artifact-1",
            decision="approve",
            client_request_id="request-00000001",
            payload={
                "decisionRequest": {
                    "artifactId": "artifact-1",
                    "decision": "approve",
                    "expectedRevision": 1,
                    "userMessage": None,
                }
            },
            result={"artifactId": "artifact-1"},
        )
    assert caught.value.code == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_revise_decision_creates_and_binds_session_before_persisting_raw_message() -> None:
    owned_task = task()
    owned_task.writingSessionId = None
    first_session = CommandSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
            RowResult(None),
            RowResult(None),
        ]
    )
    factory = SessionFactory([first_session])
    repository = WritingRunCommandRepository(factory)  # type: ignore[arg-type]
    payload = {
        "version": 1,
        "resume": True,
        "writingSessionId": None,
        "decisionRequest": {
            "artifactId": "artifact-1",
            "decision": "revise",
            "expectedRevision": 4,
            "userMessage": "  保留原始空格，不要牺牲结尾。  ",
        },
    }

    first = await repository.create_artifact_decision(
        command_id="command-1",
        user_id="user-1",
        task_id="task-1",
        artifact_id="artifact-1",
        decision="revise",
        client_request_id="request-00000001",
        payload=payload,
        result={"artifactId": "artifact-1"},
    )

    sessions = [item for item in first_session.added if isinstance(item, WritingSession)]
    messages = [item for item in first_session.added if isinstance(item, WritingMessage)]
    commands = [item for item in first_session.added if isinstance(item, WritingRunCommand)]
    assert len(sessions) == len(messages) == len(commands) == 1
    assert owned_task.writingSessionId == sessions[0].id
    assert messages[0].sessionId == sessions[0].id
    assert messages[0].content == "  保留原始空格，不要牺牲结尾。  "
    assert first.payload["writingSessionId"] == sessions[0].id

    second_session = CommandSession([RowResult((commands[0], owned_task, "user-1"))])
    factory.sessions.append(second_session)
    second = await repository.create_artifact_decision(
        command_id="command-other",
        user_id="user-1",
        task_id="task-1",
        artifact_id="artifact-1",
        decision="revise",
        client_request_id="request-00000001",
        payload=payload,
        result={"artifactId": "artifact-1"},
    )
    assert second.id == first.id
    assert second_session.added == []

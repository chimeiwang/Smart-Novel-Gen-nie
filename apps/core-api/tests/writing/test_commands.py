from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from inkforge_contracts.long_serial import SourceBinding
from inkforge_core.db.base import utc_now
from inkforge_core.db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    WritingRunCommand,
    WritingTask,
)
from inkforge_core.errors import ApiError
from inkforge_core.writing import commands as commands_module
from inkforge_core.writing.commands import (
    WritingRunCommandRepository,
    command_idempotency_key,
)
from inkforge_core.writing.recoverability import resolve_recoverable_checkpoint
from inkforge_core.writing.schemas import ResumeWritingRunRequest, StartWritingRunRequest
from inkforge_core.writing.transaction_locks import LockedWritingRows
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
        if 'UPDATE public."WritingEventOutbox"' in str(statement):
            return type("UpdateResult", (), {"rowcount": 0})()
        if not self.execute_results:
            raise AssertionError("收到未预期的数据库查询")
        return self.execute_results.pop(0)

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        return None

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


class StatusSession(CommandSession):
    def __init__(
        self,
        execute_results: list[object],
        scalar_results: list[object | None],
    ) -> None:
        super().__init__(execute_results)
        self.scalar_results = list(scalar_results)

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        if not self.scalar_results:
            raise AssertionError("收到未预期的标量查询")
        return self.scalar_results.pop(0)


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


def review_artifact(
    *,
    artifact_id: str = "artifact-1",
    task_id: str = "task-1",
    novel_id: str = "novel-1",
    chapter_id: str | None = "chapter-1",
    kind: str = "chapter_draft",
    status: str = "awaiting_user",
) -> ReviewArtifact:
    now = utc_now()
    return ReviewArtifact(
        id=artifact_id,
        novelId=novel_id,
        chapterId=chapter_id,
        taskId=task_id,
        artifactKey="draft-1",
        kind=kind,
        status=status,
        title="待确认草案",
        payloadJson=json.dumps({"kind": kind, "content": "正文"}),
        revision=1,
        createdAt=now,
        updatedAt=now,
    )


@pytest.mark.asyncio
async def test_run_status_projects_latest_artifact_decision_command() -> None:
    owned_task = task()
    decision = command(command_id="decision-1", status="processing")
    decision.kind = "artifact_decision"
    decision.createdAt = owned_task.updatedAt + timedelta(seconds=1)
    decision.updatedAt = decision.createdAt
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [decision],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.commandId == decision.id
    assert response.outcome.state == "running"
    assert response.outcome.currentCommand is not None
    assert response.outcome.currentCommand.id == decision.id
    assert response.outcome.currentCommand.kind == "artifact_decision"
    rendered = str(session.statements[1].compile(dialect=postgresql.dialect()))
    assert '"WritingRunCommand"."kind" IN' not in rendered


@pytest.mark.asyncio
async def test_long_form_waiting_status_requires_authoritative_review_artifact() -> None:
    owned_task = task()
    owned_task.phase = "awaiting_user_review"
    owned_task.graphStateJson = json.dumps(
        {
            "taskId": owned_task.id,
            "userId": "user-1",
            "novelId": owned_task.novelId,
            "chapterId": owned_task.chapterId,
            "targetWordCount": owned_task.targetWordCount,
            "conversationHistory": [],
            "phase": "awaiting_user_review",
            "eventSequence": 7,
            "artifactReview": {"activeArtifactId": "artifact-1"},
        }
    )
    completed_command = command(status="succeeded")
    artifact = review_artifact()
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [completed_command, artifact],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.outcome.state == "waiting_user"
    assert response.outcome.taskTerminal is False
    assert response.outcome.result.kind == "review_artifact"
    assert response.outcome.result.id == artifact.id
    assert response.outcome.result.ready is True


@pytest.mark.asyncio
async def test_legacy_long_form_waiting_status_loads_artifact_without_command() -> None:
    owned_task = task()
    owned_task.phase = "awaiting_user_review"
    owned_task.graphStateJson = json.dumps(
        {
            "taskId": owned_task.id,
            "userId": "user-1",
            "novelId": owned_task.novelId,
            "chapterId": owned_task.chapterId,
            "targetWordCount": owned_task.targetWordCount,
            "conversationHistory": [],
            "phase": "awaiting_user_review",
            "eventSequence": 7,
            "artifactReview": {"activeArtifactId": "artifact-1"},
        }
    )
    artifact = review_artifact()
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [None, artifact],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.commandId is None
    assert response.outcome.state == "waiting_user"
    assert response.outcome.currentCommand is None
    assert response.outcome.result.id == artifact.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifact",
    [
        review_artifact(artifact_id="artifact-other"),
        review_artifact(task_id="task-other"),
        review_artifact(novel_id="novel-other"),
        review_artifact(status="applied"),
    ],
    ids=["wrong-id", "wrong-task", "wrong-novel", "not-awaiting-user"],
)
async def test_long_form_waiting_status_rejects_non_authoritative_artifact(
    artifact: ReviewArtifact,
) -> None:
    owned_task = task()
    owned_task.phase = "awaiting_user_review"
    owned_task.graphStateJson = json.dumps(
        {
            "taskId": owned_task.id,
            "userId": "user-1",
            "novelId": owned_task.novelId,
            "chapterId": owned_task.chapterId,
            "targetWordCount": owned_task.targetWordCount,
            "conversationHistory": [],
            "phase": "awaiting_user_review",
            "eventSequence": 7,
            "artifactReview": {"activeArtifactId": "artifact-1"},
        }
    )
    completed_command = command(status="succeeded")
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [completed_command, artifact],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.outcome.state == "inconsistent"
    assert response.outcome.result.kind == "review_artifact"
    assert response.outcome.result.ready is False


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_status", ["awaiting_user", "applied"])
async def test_short_medium_completed_document_run_projects_verified_candidate(
    candidate_status: str,
) -> None:
    owned_task = task()
    owned_task.phase = "completed"
    short_command = command(status="succeeded")
    short_command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_manuscript",
            "documentType": "manuscript",
            "chapterId": owned_task.chapterId,
        }
    )
    short_command.resultJson = json.dumps({"candidateVersionId": "candidate-1"})
    short_command.artifactId = "candidate-1"
    candidate = review_artifact(
        artifact_id="candidate-1",
        status=candidate_status,
    )
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [short_command, candidate],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.candidateVersionId == candidate.id
    assert response.outcome.state == "succeeded"
    assert response.outcome.taskTerminal is True
    assert response.outcome.result.kind == "short_candidate"
    assert response.outcome.result.id == candidate.id
    assert response.outcome.result.ready is True


@pytest.mark.asyncio
async def test_short_medium_outline_candidate_has_outline_identity() -> None:
    owned_task = task()
    owned_task.phase = "completed"
    short_command = command(status="succeeded")
    short_command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_outline",
            "documentType": "outline",
            "chapterId": None,
        }
    )
    short_command.resultJson = json.dumps({"candidateVersionId": "candidate-1"})
    short_command.artifactId = "candidate-1"
    candidate = review_artifact(
        artifact_id="candidate-1",
        chapter_id=None,
        kind="outline_draft",
    )
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [short_command, candidate],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.outcome.state == "succeeded"
    assert response.outcome.result.kind == "short_candidate"
    assert response.outcome.result.ready is True


@pytest.mark.asyncio
async def test_short_medium_candidate_rejects_operation_document_type_conflict() -> None:
    owned_task = task()
    owned_task.phase = "completed"
    short_command = command(status="succeeded")
    short_command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_outline",
            "documentType": "manuscript",
            "chapterId": owned_task.chapterId,
        }
    )
    short_command.resultJson = json.dumps({"candidateVersionId": "candidate-1"})
    short_command.artifactId = "candidate-1"
    candidate = review_artifact(artifact_id="candidate-1")
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [short_command, candidate],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.outcome.state == "inconsistent"
    assert response.outcome.result.ready is False


@pytest.mark.asyncio
async def test_short_medium_full_check_projects_complete_report() -> None:
    owned_task = task()
    owned_task.phase = "completed"
    short_command = command(status="succeeded")
    short_command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "full_check",
            "documentType": "manuscript",
            "chapterId": owned_task.chapterId,
        }
    )
    report = {"summary": "检查完成", "issues": []}
    short_command.resultJson = json.dumps({"checkReport": report})
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [short_command],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.checkReport == report
    assert response.candidateVersionId is None
    assert response.outcome.state == "succeeded"
    assert response.outcome.result.kind == "check_report"
    assert response.outcome.result.id == short_command.id
    assert response.outcome.result.ready is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [{}, {"checkReport": "不是结构化报告"}],
    ids=["missing", "wrong-type"],
)
async def test_short_medium_full_check_rejects_missing_or_invalid_report(
    result: dict[str, object],
) -> None:
    owned_task = task()
    owned_task.phase = "completed"
    short_command = command(status="succeeded")
    short_command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "full_check",
            "documentType": "manuscript",
            "chapterId": owned_task.chapterId,
        }
    )
    short_command.resultJson = json.dumps(result)
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [short_command],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.checkReport is None
    assert response.outcome.state == "inconsistent"
    assert response.outcome.result.kind == "check_report"
    assert response.outcome.result.ready is False


@pytest.mark.asyncio
async def test_run_status_reports_corrupted_full_check_result_as_inconsistent() -> None:
    owned_task = task()
    owned_task.phase = "completed"
    short_command = command(status="succeeded")
    short_command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "full_check",
            "documentType": "manuscript",
            "chapterId": owned_task.chapterId,
        }
    )
    short_command.resultJson = "{损坏的 JSON"
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [short_command],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.checkReport is None
    assert response.outcome.state == "inconsistent"
    assert response.outcome.result.kind == "check_report"
    assert response.outcome.result.ready is False


@pytest.mark.asyncio
async def test_short_medium_without_command_does_not_use_long_form_reconciliation() -> None:
    owned_task = task()
    owned_task.phase = "active"
    owned_task.graphStateJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_manuscript",
            "documentType": "manuscript",
            "chapterId": owned_task.chapterId,
            "phase": "generating",
            "eventSequence": 3,
        }
    )
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [None],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.commandId is None
    assert response.outcome.state == "inconsistent"
    assert response.outcome.reconciliationRequired is True
    assert response.outcome.streamShouldClose is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "wrong-id",
        "wrong-task",
        "wrong-novel",
        "wrong-chapter",
        "wrong-kind",
        "wrong-status",
        "wrong-command-artifact",
    ],
)
async def test_short_medium_candidate_must_match_command_and_document_identity(
    case: str,
) -> None:
    owned_task = task()
    owned_task.phase = "completed"
    short_command = command(status="succeeded")
    short_command.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_manuscript",
            "documentType": "manuscript",
            "chapterId": owned_task.chapterId,
        }
    )
    short_command.resultJson = json.dumps({"candidateVersionId": "candidate-1"})
    short_command.artifactId = (
        "candidate-other" if case == "wrong-command-artifact" else "candidate-1"
    )
    candidate = review_artifact(
        artifact_id="candidate-other" if case == "wrong-id" else "candidate-1",
        task_id="task-other" if case == "wrong-task" else owned_task.id,
        novel_id="novel-other" if case == "wrong-novel" else owned_task.novelId,
        chapter_id=("chapter-other" if case == "wrong-chapter" else owned_task.chapterId),
        kind="outline_draft" if case == "wrong-kind" else "chapter_draft",
        status="draft" if case == "wrong-status" else "awaiting_user",
    )
    session = StatusSession(
        [RowResult((owned_task, "user-1"))],
        [short_command, candidate],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    response = await repository.get_run_status("user-1", owned_task.id)

    assert response.outcome.state == "inconsistent"
    assert response.outcome.result.kind == "short_candidate"
    assert response.outcome.result.ready is False


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
    assert any(
        'UPDATE public."WritingEventOutbox"' in str(statement)
        for statement in first_session.statements
    )


@pytest.mark.asyncio
async def test_artifact_decision_inherits_explicit_long_serial_start_job() -> None:
    owned_task = task()
    owned_task.phase = "awaiting_user_review"
    start_job = {
        "version": 1,
        "workflow": "long_serial",
        "chapterId": "chapter-1",
        "writingSessionId": "session-1",
        "operation": "write_chapter",
        "target": {"type": "chapter", "id": "chapter-1"},
        "scope": {"kind": "chapter", "chapterId": "chapter-1"},
        "sourceBindings": [
            {
                "resourceType": "chapter",
                "resourceId": "chapter-1",
                "exists": True,
                "updatedAt": "2026-08-06T08:00:00Z",
                "contentSha256": "a" * 64,
                "revision": 3,
                "absenceSentinel": None,
            }
        ],
        "targetWordCount": 5200,
        "userInstruction": "写出雨夜里的不可逆选择",
        "resume": False,
        "resumeInput": None,
    }
    start_payload = json.dumps(
        {
            "_inkforgeCommand": {
                "schemaVersion": 1,
                "clientRequestId": "long-start-request-0001",
                "commandKind": "start",
                "resourceIdentity": {
                    "novelId": "novel-1",
                    "chapterId": "chapter-1",
                },
                "normalizedBody": {"workflow": "long_serial"},
                "requestFingerprint": "a" * 64,
            },
            "job": start_job,
        }
    )
    session = StatusSession(
        [
            RowResult(None),
            RowResult((owned_task, "user-1")),
            RowResult(None),
        ],
        [start_payload],
    )
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )
    accepted = {
        "artifactId": "artifact-1",
        "taskId": owned_task.id,
        "commandId": "decision-1",
        "decision": "approve",
        "status": "pending",
        "savedCount": 1,
        "deleted": False,
    }

    await repository.create_artifact_decision(
        command_id="decision-1",
        user_id="user-1",
        task_id=owned_task.id,
        artifact_id="artifact-1",
        decision="approve",
        client_request_id="decision-request-0001",
        payload={
            "_inkforgeCommand": {
                "schemaVersion": 1,
                "clientRequestId": "decision-request-0001",
                "commandKind": "artifact_decision",
                "resourceIdentity": {"artifactId": "artifact-1"},
                "normalizedBody": {
                    "expectedRevision": 1,
                    "decision": "approve",
                },
                "requestFingerprint": "b" * 64,
            },
            "job": {
                "version": 1,
                "resume": True,
                "chapterId": "chapter-1",
                "writingSessionId": "session-1",
                "resumeInput": {
                    "artifactId": "artifact-1",
                    "decision": "approve",
                },
            },
        },
        result=accepted,
    )

    persisted = next(
        value for value in session.added if isinstance(value, WritingRunCommand)
    )
    payload = json.loads(persisted.payloadJson)
    assert payload["job"] == {
        **start_job,
        "resume": True,
        "resumeInput": {
            "artifactId": "artifact-1",
            "decision": "approve",
        },
    }
    result = json.loads(persisted.resultJson)
    assert result["_inkforgeArtifactDecisionAcceptedResponse"] == accepted


def test_recovery_checkpoint_requires_a_bound_snapshot_and_terminal_command() -> None:
    owned_task = task()
    source = command(status="succeeded")
    source.payloadJson = '{"job":{"operation":"write_chapter"}}'
    assert resolve_recoverable_checkpoint(owned_task, [source]) is None

    owned_task.graphStateJson = json.dumps(
        {
            "taskId": owned_task.id,
            "userId": "user-1",
            "novelId": owned_task.novelId,
            "chapterId": owned_task.chapterId,
            "targetWordCount": owned_task.targetWordCount,
            "conversationHistory": [],
            "phase": owned_task.phase,
            "eventSequence": 1,
            "currentOperation": {"kind": "write_chapter"},
            "operationStage": "执行创作操作",
            "callbackJobId": source.id,
        }
    )
    assert resolve_recoverable_checkpoint(owned_task, [source]) is not None
    assert resolve_recoverable_checkpoint(owned_task, [command(status="processing")]) is None
    source.payloadJson = '{"job":{"operation":"review_chapter"}}'
    assert resolve_recoverable_checkpoint(owned_task, [source]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("user_message", ["  ", None])
async def test_blank_resume_without_checkpoint_is_rejected_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    user_message: str | None,
) -> None:
    owned_task = task()
    session = CommandSession()
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    async def no_replay(*args: object, **kwargs: object) -> None:
        del args, kwargs
        return None

    async def identity(*args: object, **kwargs: object) -> tuple[str, str]:
        del args, kwargs
        return owned_task.novelId, owned_task.chapterId

    async def locked(*args: object, **kwargs: object) -> LockedWritingRows:
        del args, kwargs
        return LockedWritingRows(
            novel=Novel(id=owned_task.novelId, userId="user-1"),
            chapters=(Chapter(id=owned_task.chapterId, novelId=owned_task.novelId),),
            task=owned_task,
            artifact=None,
            command=None,
        )

    async def no_active(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", no_active)
    monkeypatch.setattr(commands_module, "_resolve_long_serial_resume_response", no_replay)
    monkeypatch.setattr(repository, "_require_owned_task_identity", identity)
    monkeypatch.setattr(repository, "_find_current_command_id", no_replay)
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(repository, "_require_no_active_command", no_active)

    with pytest.raises(ApiError, match="没有可恢复") as error:
        await repository.create_resume_with_message(
            "user-1",
            owned_task.id,
            ResumeWritingRunRequest(
                clientRequestId="resume-empty-0001", userMessage=user_message
            ),
        )

    assert error.value.code == "WRITING_RUN_NOT_RECOVERABLE"
    assert session.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("user_message", [None, "继续"])
async def test_authoritative_awaiting_artifact_blocks_resume_without_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    user_message: str | None,
) -> None:
    owned_task = task()
    session = CommandSession()
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    async def no_replay(*args: object, **kwargs: object) -> None:
        del args, kwargs
        return None

    async def identity(*args: object, **kwargs: object) -> tuple[str, str]:
        del args, kwargs
        return owned_task.novelId, owned_task.chapterId

    async def locked(*args: object, **kwargs: object) -> LockedWritingRows:
        del args, kwargs
        return LockedWritingRows(
            novel=Novel(id=owned_task.novelId, userId="user-1"),
            chapters=(Chapter(id=owned_task.chapterId, novelId=owned_task.novelId),),
            task=owned_task,
            artifact=None,
            command=None,
        )

    async def no_active(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def artifact(*args: object, **kwargs: object) -> str:
        del args, kwargs
        return "artifact-1"

    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", no_active)
    monkeypatch.setattr(commands_module, "_resolve_long_serial_resume_response", no_replay)
    monkeypatch.setattr(repository, "_require_owned_task_identity", identity)
    monkeypatch.setattr(repository, "_find_current_command_id", no_replay)
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(repository, "_require_no_active_command", no_active)
    monkeypatch.setattr(session, "scalar", artifact)

    with pytest.raises(ApiError) as error:
        await repository.create_resume_with_message(
            "user-1",
            owned_task.id,
            ResumeWritingRunRequest(
                clientRequestId="resume-artifact-01", userMessage=user_message
            ),
        )

    assert error.value.code == "ARTIFACT_DECISION_REQUIRED"
    assert session.added == []


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
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in session.statements
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

    record = await repository.record_dispatch_failure(
        "command-1", "AgentRunSubmitFailed"
    )

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


class NaturalStartSession(CommandSession):
    async def flush(self) -> None:
        now = utc_now()
        for value in self.added:
            if isinstance(value, WritingTask):
                value.id = value.id or "task-natural"
                value.createdAt = value.createdAt or now
                value.updatedAt = value.updatedAt or now
            elif isinstance(value, WritingRunCommand):
                value.id = value.id or "command-natural"
                value.createdAt = value.createdAt or now
                value.updatedAt = value.updatedAt or now


@pytest.mark.asyncio
async def test_natural_long_start_freezes_sources_without_explicit_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = NaturalStartSession()
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )
    order: list[str] = []
    binding = SourceBinding(
        resourceType="chapter",
        resourceId="chapter-1",
        exists=True,
        updatedAt=datetime(2026, 8, 6, tzinfo=UTC),
        contentSha256="a" * 64,
        revision=None,
        absenceSentinel=None,
    )

    async def no_existing(*args: object, **kwargs: object) -> None:
        del args, kwargs

    async def idempotency(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("idempotency")

    async def advisory(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("advisory")

    async def locked(*args: object, **kwargs: object) -> LockedWritingRows:
        del args, kwargs
        order.append("lock")
        return LockedWritingRows(
            novel=Novel(id="novel-1", userId="user-1"),
            chapters=(Chapter(id="chapter-1", novelId="novel-1"),),
            task=None,
            artifact=None,
            command=None,
        )

    async def profile(*args: object, **kwargs: object) -> str:
        del args, kwargs
        order.append("profile")
        return "long_serial"

    async def busy(*args: object, **kwargs: object) -> None:
        del args, kwargs
        order.append("busy")

    async def captured(*args: object, **kwargs: object) -> tuple[SourceBinding, ...]:
        del args, kwargs
        order.append("capture")
        return (binding,)

    monkeypatch.setattr(repository, "_get_existing_response", no_existing)
    monkeypatch.setattr(repository, "_get_by_idempotency_key", idempotency)
    monkeypatch.setattr(commands_module, "_require_chapter", no_existing)
    monkeypatch.setattr(commands_module, "acquire_idempotency_lock", advisory)
    monkeypatch.setattr(commands_module, "lock_writing_rows", locked)
    monkeypatch.setattr(
        commands_module,
        "_story_length_profile",
        profile,
        raising=False,
    )
    monkeypatch.setattr(
        commands_module,
        "_require_no_active_long_serial_mutation",
        busy,
    )
    monkeypatch.setattr(
        commands_module,
        "capture_chapter_source_bindings",
        captured,
    )

    await repository.create_start_with_task(
        "user-1",
        StartWritingRunRequest(
            clientRequestId="natural-start-000001",
            novelId="novel-1",
            chapterId="chapter-1",
            targetWordCount=4_000,
            selectedAgents=["写作", "编辑"],
            userMessage="续写本章",
        ),
    )

    command_model = next(
        value for value in session.added if isinstance(value, WritingRunCommand)
    )
    payload = json.loads(command_model.payloadJson)
    assert payload["sourceBindings"][0]["resourceType"] == "chapter"
    assert "workflow" not in payload
    assert "operation" not in payload
    assert order == [
        "advisory",
        "idempotency",
        "lock",
        "profile",
        "idempotency",
        "busy",
        "capture",
    ]


@pytest.mark.asyncio
async def test_short_medium_start_rejects_another_active_document_run() -> None:
    active = command(status="processing")
    active.payloadJson = json.dumps(
        {
            "workflow": "short_medium",
            "operation": "generate_outline",
            "documentType": "outline",
        }
    )
    session = CommandSession([RowsResult([(active.payloadJson,)])])
    repository = WritingRunCommandRepository(  # type: ignore[arg-type]
        SessionFactory([session])
    )

    with pytest.raises(ApiError) as captured:
        await repository._require_no_active_short_medium_document_run(
            session, "user-1", "novel-1"
        )

    assert captured.value.code == "SHORT_MEDIUM_DOCUMENT_RUN_ACTIVE"
    rendered = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert '"Novel"."userId"' in rendered
    assert '"WritingTask"."novelId"' in rendered

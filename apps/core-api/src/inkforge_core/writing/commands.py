from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from inkforge_contracts.jobs import AgentJobStatus, WritingJobPayload
from inkforge_contracts.short_story import (
    ShortStoryOutlineDraft,
    canonical_short_outline_hash,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    WritingBible,
    WritingMessage,
    WritingRunCommand,
    WritingSession,
    WritingTask,
)
from ..errors import ApiError
from .message_metadata import workflow_message_metadata
from .records import TaskRecord
from .recovery import validate_resume_session_binding
from .schemas import (
    ResumeWritingRunRequest,
    ResumeWritingRunResponse,
    StartWritingRunRequest,
    WritingRunResponse,
)
from .tasks import mark_task_failed_state

WritingCommandKind = Literal["start", "resume", "artifact_decision"]
WritingCommandStatus = Literal["pending", "submitted", "processing", "succeeded", "failed"]

ACTIVE_COMMAND_STATUSES = frozenset({"pending", "submitted", "processing"})
TERMINAL_COMMAND_STATUSES = frozenset({"succeeded", "failed"})
_RESUME_SESSION_UNSET = object()


@dataclass(frozen=True, slots=True)
class WritingCommandRecord:
    id: str
    task: TaskRecord
    kind: WritingCommandKind
    payload: dict[str, Any]
    status: WritingCommandStatus
    attempt_count: int
    artifact_id: str | None = None
    decision: str | None = None
    result: dict[str, Any] | None = None


def command_idempotency_key(user_id: str, client_request_id: str) -> str:
    return f"{user_id}:{client_request_id}"


class WritingRunCommandRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None:
        key = command_idempotency_key(user_id, client_request_id)
        async with self._session_factory() as session:
            row = await self._get_by_idempotency_key(session, key)
        return _command_record(*row) if row is not None else None

    async def create_start_with_task(
        self, user_id: str, request: StartWritingRunRequest
    ) -> WritingRunResponse:
        key = command_idempotency_key(user_id, request.clientRequestId)
        existing_record = await self.get_by_idempotency_key(user_id, request.clientRequestId)
        if existing_record is not None:
            _assert_start_command_semantics(existing_record, request)
        existing = await self._get_existing_response(user_id, request.clientRequestId)
        if isinstance(existing, WritingRunResponse):
            return existing
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    existing_row = await self._get_by_idempotency_key(session, key)
                    if existing_row is not None:
                        command, task, _owner_id = existing_row
                        _assert_start_command_semantics(
                            _command_record(command, task, _owner_id), request
                        )
                        return _run_response(task, command)
                    identity = await _resolve_start_workflow_identity(
                        session, user_id, request
                    )
                    if request.writingSessionId is not None:
                        await _require_session_binding(
                            session,
                            user_id,
                            request.writingSessionId,
                            request.novelId,
                            request.chapterId,
                        )
                    task = WritingTask(
                        novelId=request.novelId,
                        chapterId=request.chapterId,
                        writingSessionId=request.writingSessionId,
                        phase="idle",
                        targetWordCount=request.targetWordCount,
                        selectedAgents=",".join(request.selectedAgents),
                        conversationHistory=_dump_json(
                            [{"role": "user", "content": request.userMessage}]
                        ),
                    )
                    session.add(task)
                    await session.flush()
                    if request.writingSessionId is not None:
                        session.add(
                            WritingMessage(
                                sessionId=request.writingSessionId,
                                role="user",
                                content=request.userMessage,
                                metadata_=workflow_message_metadata(
                                    task.id,
                                    event_type="user",
                                    content=request.userMessage,
                                ),
                            )
                        )
                        await _touch_writing_session(session, request.writingSessionId)
                    command = _new_command(
                        task,
                        kind="start",
                        key=key,
                        payload=WritingJobPayload.model_validate(
                            {
                                "version": 1,
                                "resume": False,
                                "chapterId": task.chapterId,
                                "writingSessionId": task.writingSessionId,
                                "resumeInput": None,
                                **identity,
                                "startRequest": request.model_dump(mode="json"),
                            }
                        ).model_dump(mode="json"),
                    )
                    session.add(command)
                    await session.flush()
                    return _run_response(task, command)
        except IntegrityError as exc:
            raced_record = await self.get_by_idempotency_key(
                user_id, request.clientRequestId
            )
            if raced_record is not None:
                _assert_start_command_semantics(raced_record, request)
            raced = await self._get_existing_response(user_id, request.clientRequestId)
            if isinstance(raced, WritingRunResponse):
                return raced
            raise ApiError(
                status_code=409,
                code="WRITING_COMMAND_CONFLICT",
                message="写作启动请求发生并发冲突",
            ) from exc

    async def create_resume_with_message(
        self,
        user_id: str,
        task_id: str,
        request: ResumeWritingRunRequest,
    ) -> ResumeWritingRunResponse:
        key = command_idempotency_key(user_id, request.clientRequestId)
        resume_input = _resume_request_input(request)
        existing_record = await self.get_by_idempotency_key(
            user_id, request.clientRequestId
        )
        if existing_record is not None:
            _assert_resume_command_semantics(
                existing_record,
                task_id=task_id,
                resume_input=resume_input,
                writing_session_id=request.writingSessionId,
            )
            return _resume_record_response(existing_record)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    existing_row = await self._get_by_idempotency_key(session, key)
                    if existing_row is not None:
                        command, existing_task, owner_id = existing_row
                        _assert_resume_command_semantics(
                            _command_record(command, existing_task, owner_id),
                            task_id=task_id,
                            resume_input=resume_input,
                            writing_session_id=request.writingSessionId,
                        )
                        return _resume_response(command)
                    task, _owner_id = await self._require_owned_task(session, user_id, task_id)
                    existing_row = await self._get_by_idempotency_key(session, key)
                    if existing_row is not None:
                        command, existing_task, owner_id = existing_row
                        _assert_resume_command_semantics(
                            _command_record(command, existing_task, owner_id),
                            task_id=task_id,
                            resume_input=resume_input,
                            writing_session_id=request.writingSessionId,
                        )
                        return _resume_response(command)
                    if task.phase in {"completed", "error"}:
                        raise ApiError(
                            status_code=409,
                            code="WRITING_TASK_TERMINAL",
                            message="已完成或失败的任务不能继续恢复",
                        )
                    try:
                        validate_resume_session_binding(
                            request.writingSessionId, task.writingSessionId
                        )
                    except ValueError as exc:
                        raise ApiError(
                            status_code=409,
                            code="WRITING_SESSION_MISMATCH",
                            message=str(exc),
                        ) from exc
                    await self._require_no_active_command(session, task_id)
                    identity = await _latest_workflow_identity(session, task_id)
                    raw_user_message = request.userMessage or ""
                    if raw_user_message.strip() and task.writingSessionId is not None:
                        session.add(
                            WritingMessage(
                                sessionId=task.writingSessionId,
                                role="user",
                                content=raw_user_message,
                                metadata_=workflow_message_metadata(
                                    task.id,
                                    event_type="user",
                                    content=raw_user_message,
                                ),
                            )
                        )
                        await _touch_writing_session(session, task.writingSessionId)
                    command = _new_command(
                        task,
                        kind="resume",
                        key=key,
                        payload=WritingJobPayload.model_validate(
                            {
                                "version": 1,
                                "resume": True,
                                "chapterId": task.chapterId,
                                "writingSessionId": request.writingSessionId,
                                "resumeInput": resume_input,
                                **identity,
                            }
                        ).model_dump(mode="json"),
                    )
                    session.add(command)
                    await session.flush()
                    return _resume_response(command)
        except IntegrityError as exc:
            raced = await self.get_by_idempotency_key(user_id, request.clientRequestId)
            if raced is not None:
                _assert_resume_command_semantics(
                    raced,
                    task_id=task_id,
                    resume_input=resume_input,
                    writing_session_id=request.writingSessionId,
                )
                return _resume_record_response(raced)
            raise _active_command_error(task_id) from exc

    async def create_resume(
        self,
        user_id: str,
        task_id: str,
        client_request_id: str,
        resume_input: dict[str, Any],
    ) -> WritingCommandRecord:
        key = command_idempotency_key(user_id, client_request_id)
        async with self._session_factory() as session:
            async with session.begin():
                existing = await self._get_by_idempotency_key(session, key)
                if existing is not None:
                    record = _command_record(*existing)
                    _assert_resume_command_semantics(
                        record,
                        task_id=task_id,
                        resume_input=resume_input,
                    )
                    return record

                task, owner_id = await self._require_owned_task(session, user_id, task_id)
                raced = await self._get_by_idempotency_key(session, key)
                if raced is not None:
                    record = _command_record(*raced)
                    _assert_resume_command_semantics(
                        record,
                        task_id=task_id,
                        resume_input=resume_input,
                    )
                    return record
                await self._require_no_active_command(session, task_id)
                identity = await _latest_workflow_identity(session, task_id)
                payload = WritingJobPayload.model_validate(
                    {
                        "version": 1,
                        "resume": True,
                        "chapterId": task.chapterId,
                        "writingSessionId": task.writingSessionId,
                        "resumeInput": resume_input,
                        **identity,
                    }
                ).model_dump(mode="json")
                command = WritingRunCommand(
                    taskId=task.id,
                    kind="resume",
                    payloadJson=_dump_json(payload),
                    idempotencyKey=key,
                    status="pending",
                    attemptCount=0,
                    nextAttemptAt=utc_now(),
                )
                try:
                    async with session.begin_nested():
                        session.add(command)
                        await session.flush()
                except IntegrityError as exc:
                    raced = await self._get_by_idempotency_key(session, key)
                    if raced is not None:
                        record = _command_record(*raced)
                        _assert_resume_command_semantics(
                            record,
                            task_id=task_id,
                            resume_input=resume_input,
                        )
                        return record
                    raise _active_command_error(task_id) from exc
                return _command_record(command, task, owner_id)

    async def require_owned_task(self, user_id: str, task_id: str) -> TaskRecord:
        async with self._session_factory() as session:
            async with session.begin():
                task, owner_id = await self._require_owned_task(session, user_id, task_id)
        return _task_record(task, owner_id)

    async def create_artifact_decision(
        self,
        *,
        command_id: str,
        user_id: str,
        task_id: str,
        artifact_id: str,
        decision: Literal["approve", "discard", "revise"],
        client_request_id: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> WritingCommandRecord:
        key = command_idempotency_key(user_id, client_request_id)
        async with self._session_factory() as session:
            async with session.begin():
                existing = await self._get_by_idempotency_key(session, key)
                if existing is not None:
                    record = _command_record(*existing)
                    _assert_artifact_decision_semantics(
                        record,
                        artifact_id=artifact_id,
                        decision=decision,
                        payload=payload,
                    )
                    return record
                task, owner_id = await self._require_owned_task(session, user_id, task_id)
                raced = await self._get_by_idempotency_key(session, key)
                if raced is not None:
                    record = _command_record(*raced)
                    _assert_artifact_decision_semantics(
                        record,
                        artifact_id=artifact_id,
                        decision=decision,
                        payload=payload,
                    )
                    return record
                if task.phase in {"completed", "error"}:
                    raise ApiError(
                        status_code=409,
                        code="WRITING_TASK_TERMINAL",
                        message="终态写作任务不能受理草案决定",
                    )
                await self._require_no_active_command(session, task_id)
                identity = await _latest_workflow_identity(session, task_id)
                decision_request = payload.get("decisionRequest")
                if not isinstance(decision_request, dict):
                    decision_request = {}
                raw_user_message = decision_request.get("userMessage")
                source_revision = decision_request.get("expectedRevision")
                if (
                    decision == "revise"
                    and isinstance(raw_user_message, str)
                    and raw_user_message.strip()
                    and isinstance(source_revision, int)
                    and not isinstance(source_revision, bool)
                ):
                    if task.writingSessionId is None:
                        writing_session = WritingSession(
                            novelId=task.novelId,
                            chapterId=task.chapterId,
                            title="草案修改",
                            phase="idle",
                        )
                        session.add(writing_session)
                        await session.flush()
                        task.writingSessionId = writing_session.id
                        payload["writingSessionId"] = writing_session.id
                        writing_session_id = writing_session.id
                    else:
                        writing_session_id = task.writingSessionId
                    session.add(
                        WritingMessage(
                            sessionId=writing_session_id,
                            role="user",
                            content=raw_user_message,
                            intent="revision_focus",
                            metadata_=workflow_message_metadata(
                                task.id,
                                event_type="revision_focus",
                                content=raw_user_message,
                                artifact_id=artifact_id,
                                source_revision=source_revision,
                                intent="revision_focus",
                            ),
                        )
                    )
                    await _touch_writing_session(session, writing_session_id)
                resume_input = payload.get("resumeInput")
                if not isinstance(resume_input, dict):
                    resume_input = {
                        "artifactId": artifact_id,
                        "decision": decision,
                    }
                    if isinstance(source_revision, int) and not isinstance(
                        source_revision, bool
                    ):
                        resume_input["expectedRevision"] = source_revision
                    if isinstance(raw_user_message, str):
                        resume_input["userMessage"] = raw_user_message
                payload = WritingJobPayload.model_validate(
                    {
                        **payload,
                        "version": 1,
                        "resume": True,
                        "chapterId": task.chapterId,
                        "writingSessionId": task.writingSessionId,
                        "resumeInput": resume_input,
                        **identity,
                    }
                ).model_dump(mode="json")
                command = WritingRunCommand(
                    id=command_id,
                    taskId=task_id,
                    kind="artifact_decision",
                    artifactId=artifact_id,
                    decision=decision,
                    payloadJson=_dump_json(payload),
                    resultJson=_dump_json(result),
                    idempotencyKey=key,
                    status="pending",
                    attemptCount=0,
                    nextAttemptAt=utc_now(),
                )
                session.add(command)
                await session.flush()
                return _command_record(command, task, owner_id)

    async def _get_existing_response(
        self, user_id: str, client_request_id: str
    ) -> WritingRunResponse | ResumeWritingRunResponse | None:
        key = command_idempotency_key(user_id, client_request_id)
        async with self._session_factory() as session:
            row = await self._get_by_idempotency_key(session, key)
        if row is None:
            return None
        command, task, _owner_id = row
        if command.kind == "start":
            return _run_response(task, command)
        return _resume_response(command)

    async def claim_due(
        self,
        limit: int,
        active_stale_before: datetime,
    ) -> list[WritingCommandRecord]:
        if limit < 1:
            raise ValueError("命令领取数量必须大于零")
        now = utc_now()
        async with self._session_factory() as session:
            async with session.begin():
                rows = (
                    await session.execute(
                        select(WritingRunCommand, WritingTask, Novel.userId)
                        .join(WritingTask, WritingTask.id == WritingRunCommand.taskId)
                        .join(Novel, Novel.id == WritingTask.novelId)
                        .where(
                            or_(
                                and_(
                                    WritingRunCommand.status == "pending",
                                    WritingRunCommand.nextAttemptAt <= now,
                                ),
                                and_(
                                    WritingRunCommand.status.in_(("submitted", "processing")),
                                    WritingRunCommand.updatedAt <= active_stale_before,
                                ),
                            ),
                            Novel.userId.is_not(None),
                        )
                        .order_by(
                            WritingRunCommand.nextAttemptAt,
                            WritingRunCommand.createdAt,
                            WritingRunCommand.id,
                        )
                        .limit(limit)
                        .with_for_update(of=WritingRunCommand, skip_locked=True)
                    )
                ).all()
                return [
                    _command_record(command, task, owner_id) for command, task, owner_id in rows
                ]

    async def mark_agent_active(self, command_id: str) -> WritingCommandRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._get_by_id(session, command_id, for_update=True)
                if row is None:
                    raise ApiError(
                        status_code=404,
                        code="WRITING_COMMAND_NOT_FOUND",
                        message="写作命令不存在",
                    )
                command, task, owner_id = row
                if command.status in TERMINAL_COMMAND_STATUSES:
                    return _command_record(command, task, owner_id)
                now = utc_now()
                if command.status == "pending":
                    command.status = "submitted"
                    command.submittedAt = command.submittedAt or now
                command.lastError = None
                command.updatedAt = now
                await session.flush()
                return _command_record(command, task, owner_id)

    async def settle_dispatch_terminal(
        self,
        command_id: str,
        agent_status: AgentJobStatus,
    ) -> WritingCommandRecord:
        if agent_status in {"queued", "running"}:
            raise ValueError("活动 Agent job 不能按终态收敛")
        async with self._session_factory() as session:
            async with session.begin():
                task_locked_row = await self._get_by_id(
                    session,
                    command_id,
                    for_update=True,
                    lock_task=True,
                )
                if task_locked_row is None:
                    raise ApiError(
                        status_code=404,
                        code="WRITING_COMMAND_NOT_FOUND",
                        message="写作命令不存在",
                    )
                row = await self._get_by_id(
                    session,
                    command_id,
                    for_update=True,
                )
                if row is None:
                    raise ApiError(
                        status_code=404,
                        code="WRITING_COMMAND_NOT_FOUND",
                        message="写作命令不存在",
                    )
                command, task, owner_id = row
                if command.status in TERMINAL_COMMAND_STATUSES:
                    return _command_record(command, task, owner_id)
                code = f"AGENT_JOB_TERMINAL_{agent_status.upper()}"
                now = utc_now()
                command.status = "succeeded" if task.phase == "completed" else "failed"
                command.completedAt = now
                command.updatedAt = now
                command.lastError = None if task.phase == "completed" else code
                if command.resultJson is None:
                    command.resultJson = _dump_json({"code": code, "agentStatus": agent_status})
                if task.phase not in {"completed", "error"}:
                    mark_task_failed_state(task, code)
                await session.flush()
                return _command_record(command, task, owner_id)

    async def mark_submitted(self, command_id: str) -> WritingCommandRecord:
        return await self.mark_agent_active(command_id)

    async def mark_processing(self, command_id: str) -> WritingCommandRecord:
        return await self._transition(command_id, "processing")

    async def mark_succeeded(
        self, command_id: str, result: dict[str, Any] | None = None
    ) -> WritingCommandRecord:
        return await self._transition(command_id, "succeeded", result=result)

    async def mark_failed(
        self, command_id: str, result: dict[str, Any] | None = None
    ) -> WritingCommandRecord:
        return await self._transition(command_id, "failed", result=result)

    async def record_dispatch_failure(
        self, command_id: str, error_code: str
    ) -> WritingCommandRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._get_by_id(session, command_id, for_update=True)
                if row is None:
                    raise ApiError(
                        status_code=404,
                        code="WRITING_COMMAND_NOT_FOUND",
                        message="写作命令不存在",
                    )
                command, task, owner_id = row
                if command.status in TERMINAL_COMMAND_STATUSES:
                    return _command_record(command, task, owner_id)
                attempt_count = command.attemptCount + 1
                delay_seconds = min(60, 2**attempt_count)
                now = utc_now()
                command.attemptCount = attempt_count
                command.nextAttemptAt = now + timedelta(seconds=delay_seconds)
                command.lastError = error_code[:128]
                command.updatedAt = now
                await session.flush()
                return _command_record(command, task, owner_id)

    async def _transition(
        self,
        command_id: str,
        target: WritingCommandStatus,
        *,
        result: dict[str, Any] | None = None,
    ) -> WritingCommandRecord:
        async with self._session_factory() as session:
            async with session.begin():
                row = await self._get_by_id(session, command_id, for_update=True)
                if row is None:
                    raise ApiError(
                        status_code=404,
                        code="WRITING_COMMAND_NOT_FOUND",
                        message="写作命令不存在",
                    )
                command, task, owner_id = row
                current = cast(WritingCommandStatus, command.status)
                if current == target:
                    return _command_record(command, task, owner_id)
                if current in TERMINAL_COMMAND_STATUSES:
                    raise ApiError(
                        status_code=409,
                        code="WRITING_COMMAND_TERMINAL",
                        message="终态写作命令不能再次变更",
                    )
                _validate_transition(current, target)
                now = utc_now()
                command.status = target
                command.updatedAt = now
                if target == "submitted":
                    command.submittedAt = command.submittedAt or now
                    command.lastError = None
                if target in TERMINAL_COMMAND_STATUSES:
                    command.completedAt = now
                    command.resultJson = _dump_json(result) if result is not None else None
                await session.flush()
                return _command_record(command, task, owner_id)

    async def _get_by_idempotency_key(
        self, session: AsyncSession, key: str
    ) -> tuple[WritingRunCommand, WritingTask, str] | None:
        row = (
            await session.execute(
                select(WritingRunCommand, WritingTask, Novel.userId)
                .join(WritingTask, WritingTask.id == WritingRunCommand.taskId)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(WritingRunCommand.idempotencyKey == key)
            )
        ).one_or_none()
        return cast(tuple[WritingRunCommand, WritingTask, str] | None, row)

    async def _get_by_id(
        self,
        session: AsyncSession,
        command_id: str,
        *,
        for_update: bool,
        lock_task: bool = False,
    ) -> tuple[WritingRunCommand, WritingTask, str] | None:
        statement = (
            select(WritingRunCommand, WritingTask, Novel.userId)
            .join(WritingTask, WritingTask.id == WritingRunCommand.taskId)
            .join(Novel, Novel.id == WritingTask.novelId)
            .where(WritingRunCommand.id == command_id)
        )
        if for_update:
            statement = statement.with_for_update(
                of=WritingTask if lock_task else WritingRunCommand
            )
        row = (await session.execute(statement)).one_or_none()
        return cast(tuple[WritingRunCommand, WritingTask, str] | None, row)

    async def _require_owned_task(
        self, session: AsyncSession, user_id: str, task_id: str
    ) -> tuple[WritingTask, str]:
        row = (
            await session.execute(
                select(WritingTask, Novel.userId)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(WritingTask.id == task_id, Novel.userId == user_id)
                .with_for_update(of=WritingTask)
            )
        ).one_or_none()
        if row is None:
            raise ApiError(
                status_code=404,
                code="WRITING_TASK_NOT_FOUND",
                message="写作任务不存在",
            )
        return cast(tuple[WritingTask, str], row)

    async def _require_no_active_command(self, session: AsyncSession, task_id: str) -> None:
        row = (
            await session.execute(
                select(WritingRunCommand.id).where(
                    WritingRunCommand.taskId == task_id,
                    WritingRunCommand.status.in_(ACTIVE_COMMAND_STATUSES),
                )
            )
        ).one_or_none()
        if row is not None:
            raise _active_command_error(task_id)


def _active_command_error(task_id: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="WRITING_COMMAND_ACTIVE",
        message="该写作任务已有正在处理的命令",
        details={"taskId": task_id},
    )


def _assert_artifact_decision_semantics(
    command: WritingCommandRecord,
    *,
    artifact_id: str,
    decision: str,
    payload: dict[str, Any],
) -> None:
    if (
        command.kind != "artifact_decision"
        or command.artifact_id != artifact_id
        or command.decision != decision
        or command.payload.get("decisionRequest") != payload.get("decisionRequest")
    ):
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="客户端请求标识已用于其他操作",
        )


def _assert_start_command_semantics(
    command: WritingCommandRecord,
    request: StartWritingRunRequest,
) -> None:
    if (
        command.kind != "start"
        or command.payload.get("startRequest") != request.model_dump(mode="json")
    ):
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="客户端请求标识已用于其他操作",
        )


def _resume_request_input(request: ResumeWritingRunRequest) -> dict[str, Any]:
    return request.model_dump(
        mode="json",
        exclude={"clientRequestId", "writingSessionId"},
        exclude_none=True,
    )


def _assert_resume_command_semantics(
    command: WritingCommandRecord,
    *,
    task_id: str,
    resume_input: dict[str, Any],
    writing_session_id: str | None | object = _RESUME_SESSION_UNSET,
) -> None:
    if (
        command.kind != "resume"
        or command.task.id != task_id
        or (
            writing_session_id is not _RESUME_SESSION_UNSET
            and command.payload.get("writingSessionId") != writing_session_id
        )
        or command.payload.get("resumeInput") != resume_input
    ):
        raise ApiError(
            status_code=409,
            code="IDEMPOTENCY_KEY_REUSED",
            message="客户端请求标识已用于其他操作",
        )


async def _resolve_start_workflow_identity(
    session: AsyncSession,
    user_id: str,
    request: StartWritingRunRequest,
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(Novel, Chapter, WritingBible)
            .join(Chapter, Chapter.novelId == Novel.id)
            .outerjoin(WritingBible, WritingBible.novelId == Novel.id)
            .where(
                Novel.id == request.novelId,
                Novel.userId == user_id,
                Chapter.id == request.chapterId,
                Chapter.novelId == request.novelId,
            )
        )
    ).one_or_none()
    if row is None:
        raise ApiError(
            status_code=404,
            code="CHAPTER_NOT_FOUND",
            message="章节不存在或不属于该小说",
        )
    novel, chapter, bible = cast(tuple[Novel, Chapter, WritingBible | None], row)
    persisted_profile = bible.storyLengthProfile if bible is not None else "long_serial"
    if request.workflowKind != persisted_profile:
        raise ApiError(
            status_code=409,
            code="WRITING_WORKFLOW_MISMATCH",
            message="写作请求篇幅类型与作品圣经不一致",
        )
    if persisted_profile == "long_serial":
        return {
            "workflowKind": "long_serial",
            "operation": request.operation,
            "targetTotalWordCount": (
                bible.targetTotalWordCount if bible is not None else None
            ),
            "source": None,
        }

    target = bible.targetTotalWordCount if bible is not None else None
    if target is None or not 6_000 <= target <= 80_000:
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_TARGET_INVALID",
            message="中短篇目标总字数必须先修正为 6000～80000",
        )
    if request.targetWordCount != target:
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_TARGET_MISMATCH",
            message="写作请求目标字数与作品圣经不一致",
        )
    chapter_count = await session.scalar(
        select(func.count(Chapter.id)).where(Chapter.novelId == request.novelId)
    )
    if chapter_count != 1:
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_CHAPTER_INVALID",
            message="中短篇必须使用小说创建时的唯一正文承载章节",
        )
    if request.operation == "develop_short_outline":
        inspiration = (novel.summary or "").strip()
        if not inspiration:
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_INSPIRATION_MISSING",
                message="中短篇缺少原始灵感",
            )
        source: dict[str, Any] = {
            "kind": "short_outline_inspiration",
            "originalInspiration": inspiration,
        }
    else:
        artifact = await session.scalar(
            select(ReviewArtifact)
            .where(
                ReviewArtifact.novelId == request.novelId,
                ReviewArtifact.kind == "outline_draft",
            )
            .order_by(
                ReviewArtifact.updatedAt.desc(),
                ReviewArtifact.id.desc(),
            )
            .limit(1)
        )
        if artifact is None or artifact.status != "applied":
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_OUTLINE_NOT_APPROVED",
                message="生成完整正文前必须先批准中短篇大纲",
            )
        try:
            outline = ShortStoryOutlineDraft.model_validate(json.loads(artifact.payloadJson))
        except (json.JSONDecodeError, ValueError, TypeError):
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_OUTLINE_INVALID",
                message="已批准中短篇大纲载荷无效",
            ) from None
        source = {
            "kind": "approved_short_outline",
            "outlineArtifactId": artifact.id,
            "outlineRevision": artifact.revision,
            "outlineHash": canonical_short_outline_hash(outline),
        }
    return {
        "workflowKind": "short_medium",
        "operation": request.operation,
        "targetTotalWordCount": target,
        "source": source,
    }


async def _latest_workflow_identity(
    session: AsyncSession,
    task_id: str,
) -> dict[str, Any]:
    serialized = await session.scalar(
        select(WritingRunCommand.payloadJson)
        .where(WritingRunCommand.taskId == task_id)
        .order_by(WritingRunCommand.createdAt.desc(), WritingRunCommand.id.desc())
        .limit(1)
    )
    legacy = {
        "workflowKind": "long_serial",
        "operation": None,
        "targetTotalWordCount": None,
        "source": None,
    }
    if serialized is None:
        return legacy
    try:
        value = json.loads(serialized)
    except (json.JSONDecodeError, TypeError):
        raise ApiError(
            status_code=409,
            code="WRITING_COMMAND_PAYLOAD_INVALID",
            message="最近写作命令载荷无效",
        ) from None
    if not isinstance(value, dict):
        raise ApiError(
            status_code=409,
            code="WRITING_COMMAND_PAYLOAD_INVALID",
            message="最近写作命令载荷无效",
        )
    if "workflowKind" not in value:
        return legacy
    try:
        parsed = WritingJobPayload.model_validate(value)
    except ValueError:
        raise ApiError(
            status_code=409,
            code="WRITING_COMMAND_IDENTITY_INVALID",
            message="最近写作命令身份无效",
        ) from None
    return {
        "workflowKind": parsed.workflowKind,
        "operation": parsed.operation,
        "targetTotalWordCount": parsed.targetTotalWordCount,
        "source": parsed.source.model_dump(mode="json") if parsed.source is not None else None,
    }


def _new_command(
    task: WritingTask,
    *,
    kind: WritingCommandKind,
    key: str,
    payload: dict[str, Any],
) -> WritingRunCommand:
    return WritingRunCommand(
        taskId=task.id,
        kind=kind,
        payloadJson=_dump_json(payload),
        idempotencyKey=key,
        status="pending",
        attemptCount=0,
        nextAttemptAt=utc_now(),
    )


def _run_response(task: WritingTask, command: WritingRunCommand) -> WritingRunResponse:
    return WritingRunResponse(
        id=task.id,
        novelId=task.novelId,
        chapterId=task.chapterId,
        writingSessionId=task.writingSessionId,
        phase=task.phase,
        targetWordCount=task.targetWordCount,
        selectedAgents=[item for item in task.selectedAgents.split(",") if item],
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
        commandId=command.id,
        commandStatus=cast(WritingCommandStatus, command.status),
    )


def _resume_response(command: WritingRunCommand) -> ResumeWritingRunResponse:
    return ResumeWritingRunResponse(
        accepted=True,
        taskId=command.taskId,
        commandId=command.id,
        commandStatus=cast(WritingCommandStatus, command.status),
    )


def _resume_record_response(command: WritingCommandRecord) -> ResumeWritingRunResponse:
    return ResumeWritingRunResponse(
        accepted=True,
        taskId=command.task.id,
        commandId=command.id,
        commandStatus=command.status,
    )


async def _require_chapter(
    session: AsyncSession, user_id: str, novel_id: str, chapter_id: str
) -> None:
    found = await session.scalar(
        select(Chapter.id)
        .join(Novel, Novel.id == Chapter.novelId)
        .where(
            Chapter.id == chapter_id,
            Chapter.novelId == novel_id,
            Novel.userId == user_id,
        )
    )
    if found is None:
        raise ApiError(
            status_code=404,
            code="CHAPTER_NOT_FOUND",
            message="章节不存在或不属于该小说",
        )


async def _require_session_binding(
    session: AsyncSession,
    user_id: str,
    session_id: str,
    novel_id: str,
    chapter_id: str,
) -> None:
    found = await session.scalar(
        select(WritingSession.id)
        .join(Novel, Novel.id == WritingSession.novelId)
        .where(
            WritingSession.id == session_id,
            WritingSession.novelId == novel_id,
            WritingSession.chapterId == chapter_id,
            Novel.userId == user_id,
        )
    )
    if found is None:
        raise ApiError(
            status_code=409,
            code="WRITING_SESSION_MISMATCH",
            message="写作会话与当前小说或章节不匹配",
        )


async def _touch_writing_session(session: AsyncSession, session_id: str) -> None:
    writing_session = await session.get(WritingSession, session_id)
    if writing_session is not None:
        writing_session.updatedAt = utc_now()


def _validate_transition(current: WritingCommandStatus, target: WritingCommandStatus) -> None:
    allowed: dict[WritingCommandStatus, frozenset[WritingCommandStatus]] = {
        "pending": frozenset({"submitted", "processing", "succeeded", "failed"}),
        "submitted": frozenset({"processing", "succeeded", "failed"}),
        "processing": frozenset({"succeeded", "failed"}),
        "succeeded": frozenset(),
        "failed": frozenset(),
    }
    if target not in allowed[current]:
        raise ApiError(
            status_code=409,
            code="WRITING_COMMAND_STATE_CONFLICT",
            message=f"写作命令不能从 {current} 变更为 {target}",
        )


def _command_record(
    command: WritingRunCommand, task: WritingTask, user_id: str
) -> WritingCommandRecord:
    payload = _load_json_object(command.payloadJson, field="payloadJson")
    result = (
        _load_json_object(command.resultJson, field="resultJson")
        if command.resultJson is not None
        else None
    )
    return WritingCommandRecord(
        id=command.id,
        task=_task_record(task, user_id),
        kind=cast(WritingCommandKind, command.kind),
        payload=payload,
        status=cast(WritingCommandStatus, command.status),
        attempt_count=command.attemptCount,
        artifact_id=command.artifactId,
        decision=command.decision,
        result=result,
    )


def _task_record(task: WritingTask, user_id: str) -> TaskRecord:
    return TaskRecord(
        id=task.id,
        user_id=user_id,
        novel_id=task.novelId,
        chapter_id=task.chapterId,
        writing_session_id=task.writingSessionId,
        phase=task.phase,
        graph_state_json=task.graphStateJson,
    )


def _load_json_object(value: str, *, field: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"写作命令的 {field} 不是合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"写作命令的 {field} 必须是 JSON 对象")
    return cast(dict[str, Any], parsed)


def _dump_json(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

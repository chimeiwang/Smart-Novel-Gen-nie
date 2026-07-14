from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from inkforge_contracts.jobs import AgentJobStatus
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Chapter,
    Novel,
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
        existing = await self._get_existing_response(user_id, request.clientRequestId)
        if isinstance(existing, WritingRunResponse):
            return existing
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    existing_row = await self._get_by_idempotency_key(session, key)
                    if existing_row is not None:
                        command, task, _owner_id = existing_row
                        return _run_response(task, command)
                    await _require_chapter(
                        session, user_id, request.novelId, request.chapterId
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
                        payload={
                            "version": 1,
                            "resume": False,
                            "chapterId": task.chapterId,
                            "writingSessionId": task.writingSessionId,
                            "resumeInput": None,
                        },
                    )
                    session.add(command)
                    await session.flush()
                    return _run_response(task, command)
        except IntegrityError as exc:
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
        existing = await self._get_existing_response(user_id, request.clientRequestId)
        if isinstance(existing, ResumeWritingRunResponse):
            return existing
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    existing_row = await self._get_by_idempotency_key(session, key)
                    if existing_row is not None:
                        command, _task, _owner_id = existing_row
                        return _resume_response(command)
                    task, _owner_id = await self._require_owned_task(
                        session, user_id, task_id
                    )
                    existing_row = await self._get_by_idempotency_key(session, key)
                    if existing_row is not None:
                        command, _task, _owner_id = existing_row
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
                    visible_message = (request.userMessage or "").strip()
                    if visible_message and task.writingSessionId is not None:
                        session.add(
                            WritingMessage(
                                sessionId=task.writingSessionId,
                                role="user",
                                content=visible_message,
                                metadata_=workflow_message_metadata(
                                    task.id,
                                    event_type="user",
                                    content=visible_message,
                                ),
                            )
                        )
                        await _touch_writing_session(session, task.writingSessionId)
                    resume_input = request.model_dump(
                        mode="json",
                        exclude={"clientRequestId", "writingSessionId"},
                        exclude_none=True,
                    )
                    command = _new_command(
                        task,
                        kind="resume",
                        key=key,
                        payload={
                            "version": 1,
                            "resume": True,
                            "chapterId": task.chapterId,
                            "writingSessionId": task.writingSessionId,
                            "resumeInput": resume_input,
                        },
                    )
                    session.add(command)
                    await session.flush()
                    return _resume_response(command)
        except IntegrityError as exc:
            raced = await self._get_existing_response(user_id, request.clientRequestId)
            if isinstance(raced, ResumeWritingRunResponse):
                return raced
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
                    return _command_record(*existing)

                task, owner_id = await self._require_owned_task(session, user_id, task_id)
                await self._require_no_active_command(session, task_id)
                payload = {
                    "version": 1,
                    "resume": True,
                    "chapterId": task.chapterId,
                    "writingSessionId": task.writingSessionId,
                    "resumeInput": resume_input,
                }
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
                        return _command_record(*raced)
                    raise _active_command_error(task_id) from exc
                return _command_record(command, task, owner_id)

    async def require_owned_task(self, user_id: str, task_id: str) -> TaskRecord:
        async with self._session_factory() as session:
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
                    return _command_record(*existing)
                task, owner_id = await self._require_owned_task(
                    session, user_id, task_id
                )
                if task.phase in {"completed", "error"}:
                    raise ApiError(
                        status_code=409,
                        code="WRITING_TASK_TERMINAL",
                        message="终态写作任务不能受理草案决定",
                    )
                await self._require_no_active_command(session, task_id)
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
                                    WritingRunCommand.status.in_(
                                        ("submitted", "processing")
                                    ),
                                    WritingRunCommand.updatedAt
                                    <= active_stale_before,
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
                    _command_record(command, task, owner_id)
                    for command, task, owner_id in rows
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
                    command.resultJson = _dump_json(
                        {"code": code, "agentStatus": agent_status}
                    )
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

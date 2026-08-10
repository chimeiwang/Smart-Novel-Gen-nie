from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from inkforge_contracts.jobs import AgentJobStatus
from inkforge_contracts.long_serial import (
    LONG_SERIAL_RUN_PAYLOAD_ADAPTER,
    PUBLIC_LONG_SERIAL_OPERATIONS,
    ChapterScope,
    NovelScope,
    OutlineNodeScope,
    SelectionAttachmentMetadata,
    SelectionTarget,
    SourceBinding,
)
from inkforge_contracts.operations import PublicOperationDefinition
from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Chapter,
    Novel,
    Outline,
    OutlineNode,
    ReviewArtifact,
    WritingBible,
    WritingMessage,
    WritingRunCommand,
    WritingSession,
    WritingTask,
)
from ..errors import ApiError
from ..short_medium.completion import (
    assemble_short_medium_run_payload,
    load_short_medium_run_source,
)
from .idempotency import (
    JsonValue,
    acquire_idempotency_lock,
    command_idempotency_key,
    enveloped_command_idempotency_key,
    logical_command_kind,
    normalize_json_value,
    parse_command_envelope,
    request_fingerprint,
    resolve_idempotency,
)
from .message_metadata import workflow_message_metadata
from .outbox import supersede_waiting_for_new_command
from .records import TaskRecord
from .recoverability import resolve_recoverable_checkpoint
from .recovery import validate_resume_session_binding
from .schemas import (
    LongSerialStartWritingRunRequest,
    ResumeWritingRunRequest,
    ResumeWritingRunResponse,
    ShortMediumStartWritingRunRequest,
    StartWritingRunRequest,
    WritingRunListResponse,
    WritingRunResponse,
    WritingRunStartRequest,
    WritingRunStatusResponse,
)
from .source_bindings import capture_chapter_source_bindings
from .tasks import TERMINAL_CALLBACK_RESULT_FIELD, mark_task_failed_state
from .transaction_locks import WritingLockRequest, lock_writing_rows

WritingCommandKind = Literal["start", "resume", "artifact_decision", "cancel"]
WritingCommandStatus = Literal["pending", "submitted", "processing", "succeeded", "failed"]

ACTIVE_COMMAND_STATUSES = frozenset({"pending", "submitted", "processing"})
TERMINAL_COMMAND_STATUSES = frozenset({"succeeded", "failed"})
ARTIFACT_DECISION_ACCEPTED_RESPONSE_FIELD = (
    "_inkforgeArtifactDecisionAcceptedResponse"
)


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


class WritingRunCommandRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_idempotency_key(
        self, user_id: str, client_request_id: str
    ) -> WritingCommandRecord | None:
        async with self._session_factory() as session:
            row = await self._get_by_idempotency_key(
                session, enveloped_command_idempotency_key(user_id, client_request_id)
            )
            if row is None:
                row = await self._get_by_idempotency_key(
                    session, command_idempotency_key(user_id, client_request_id)
                )
        return _command_record(*row) if row is not None else None

    async def create_start_with_task(
        self, user_id: str, request: WritingRunStartRequest
    ) -> WritingRunResponse:
        if isinstance(request, LongSerialStartWritingRunRequest):
            return await self._create_long_serial_start(user_id, request)
        if isinstance(request, StartWritingRunRequest):
            return await self._create_natural_start(user_id, request)
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
                    return await self._create_short_medium_start(
                        session, user_id, request, key
                    )
        except IntegrityError as exc:
            raced = await self._get_existing_response(user_id, request.clientRequestId)
            if isinstance(raced, WritingRunResponse):
                return raced
            raise ApiError(
                status_code=409,
                code="WRITING_COMMAND_CONFLICT",
                message="写作启动请求发生并发冲突",
            ) from exc

    async def _create_natural_start(
        self,
        user_id: str,
        request: StartWritingRunRequest,
    ) -> WritingRunResponse:
        key = command_idempotency_key(user_id, request.clientRequestId)
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await acquire_idempotency_lock(
                        session,
                        user_id=user_id,
                        client_request_id=request.clientRequestId,
                    )
                    existing_row = await self._get_by_idempotency_key(
                        session, key
                    )
                    if existing_row is not None:
                        command, task, _owner_id = existing_row
                        return _run_response(task, command)

                    await lock_writing_rows(
                        session,
                        user_id=user_id,
                        request=WritingLockRequest(
                            novel_id=request.novelId,
                            chapter_ids=(request.chapterId,),
                        ),
                    )
                    story_length_profile = await _story_length_profile(
                        session, request.novelId
                    )
                    if request.writingSessionId is not None:
                        await _require_session_binding(
                            session,
                            user_id,
                            request.writingSessionId,
                            request.novelId,
                            request.chapterId,
                        )

                    existing_row = await self._get_by_idempotency_key(
                        session, key
                    )
                    if existing_row is not None:
                        command, task, _owner_id = existing_row
                        return _run_response(task, command)

                    payload: dict[str, Any] = {
                        "version": 1,
                        "resume": False,
                        "chapterId": request.chapterId,
                        "writingSessionId": request.writingSessionId,
                        "resumeInput": None,
                    }
                    if story_length_profile == "long_serial":
                        await _require_no_active_long_serial_mutation(
                            session, request.chapterId
                        )
                        bindings = await capture_chapter_source_bindings(
                            session,
                            novel_id=request.novelId,
                            chapter_id=request.chapterId,
                        )
                        payload["sourceBindings"] = [
                            binding.model_dump(mode="json")
                            for binding in bindings
                        ]

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
                        await _touch_writing_session(
                            session, request.writingSessionId
                        )
                    command = _new_command(
                        task,
                        kind="start",
                        key=key,
                        payload=payload,
                    )
                    session.add(command)
                    await session.flush()
                    return _run_response(task, command)
        except IntegrityError as exc:
            raced = await self._get_existing_response(
                user_id, request.clientRequestId
            )
            if isinstance(raced, WritingRunResponse):
                return raced
            raise ApiError(
                status_code=409,
                code="WRITING_COMMAND_CONFLICT",
                message="写作启动请求发生并发冲突",
            ) from exc

    async def _create_long_serial_start(
        self,
        user_id: str,
        request: LongSerialStartWritingRunRequest,
    ) -> WritingRunResponse:
        definition = _long_serial_operation_definition(request)
        normalized = normalize_json_value(
            request.model_dump(mode="json", exclude={"clientRequestId"})
        )
        if not isinstance(normalized, dict):
            raise RuntimeError("长篇启动请求规范化后不是 JSON 对象")
        normalized_body = normalized
        resource_identity: dict[str, JsonValue] = {
            "novelId": request.novelId,
            "chapterId": request.chapterId,
        }
        fingerprint = request_fingerprint(
            command_kind="start",
            resource_identity=resource_identity,
            body=normalized_body,
        )
        key = enveloped_command_idempotency_key(
            user_id, request.clientRequestId
        )

        async with self._session_factory() as session:
            async with session.begin():
                await acquire_idempotency_lock(
                    session,
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                )
                replay = await _resolve_long_serial_start_response(
                    self,
                    session,
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                    fingerprint=fingerprint,
                )
                if replay is not None:
                    return replay

                await lock_writing_rows(
                    session,
                    user_id=user_id,
                    request=WritingLockRequest(
                        novel_id=request.novelId,
                        chapter_ids=(request.chapterId,),
                    ),
                )
                await _require_long_serial_profile(session, request.novelId)
                if request.writingSessionId is not None:
                    await _require_session_binding(
                        session,
                        user_id,
                        request.writingSessionId,
                        request.novelId,
                        request.chapterId,
                    )

                replay = await _resolve_long_serial_start_response(
                    self,
                    session,
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                    fingerprint=fingerprint,
                )
                if replay is not None:
                    return replay

                if definition.mutating:
                    await _require_no_active_long_serial_mutation(
                        session, request.chapterId
                    )
                bindings = await capture_chapter_source_bindings(
                    session,
                    novel_id=request.novelId,
                    chapter_id=request.chapterId,
                )
                selection_snapshot: dict[str, Any] | None = None
                selection_attachment_metadata: dict[str, Any] | None = None
                target_word_count = request.targetWordCount
                if request.selectionTarget is not None:
                    selection_snapshot = await _capture_selection_snapshot(
                        session,
                        novel_id=request.novelId,
                        chapter_id=request.chapterId,
                        operation=request.operation,
                        target=request.selectionTarget,
                    )
                    if request.selectionAttachmentMetadata is not None:
                        selection_attachment_metadata = _validate_selection_attachment_metadata(
                            request.selectionAttachmentMetadata,
                            request.selectionTarget,
                            selection_snapshot,
                        )
                    target_word_count = max(
                        1,
                        request.selectionTarget.selectionEnd
                        - request.selectionTarget.selectionStart,
                    )
                    bindings = (
                        *bindings,
                        SourceBinding(
                            resourceType=request.selectionTarget.resourceType,
                            resourceId=request.selectionTarget.resourceId,
                            exists=True,
                            updatedAt=request.selectionTarget.baseUpdatedAt,
                            contentSha256=request.selectionTarget.baseContentHash,
                            revision=None,
                            absenceSentinel=None,
                        ),
                    )
                raw_job = {
                    "version": 1,
                    "workflow": "long_serial",
                    "chapterId": request.chapterId,
                    "writingSessionId": request.writingSessionId,
                    "operation": request.operation,
                    "target": request.target.model_dump(mode="json"),
                    "scope": request.scope.model_dump(mode="json"),
                    "sourceBindings": [
                        binding.model_dump(mode="json") for binding in bindings
                    ],
                    "targetWordCount": target_word_count,
                    "userInstruction": request.userInstruction,
                    "resume": False,
                    "resumeInput": None,
                }
                if selection_snapshot is not None:
                    selection_target = cast(SelectionTarget, request.selectionTarget)
                    raw_job["selectionTarget"] = selection_target.model_dump(
                        mode="json"
                    )
                    raw_job["selectionSnapshot"] = selection_snapshot
                validated_job = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(
                    raw_job
                )
                job = validated_job.model_dump(mode="json")
                if request.selectionTarget is None:
                    job.pop("selectionTarget", None)
                    job.pop("selectionSnapshot", None)
                conversation_history = [
                    {
                        "role": "user",
                        "content": request.userInstruction,
                    }
                ]
                task = WritingTask(
                    novelId=request.novelId,
                    chapterId=request.chapterId,
                    writingSessionId=request.writingSessionId,
                    phase="idle",
                    targetWordCount=target_word_count,
                    selectedAgents=",".join(
                        (definition.principalAgent, *definition.reviewers)
                    ),
                    conversationHistory=_dump_json(conversation_history),
                )
                session.add(task)
                await session.flush()
                task.graphStateJson = _dump_json(
                    {
                        **job,
                        "taskId": task.id,
                        "userId": user_id,
                        "novelId": request.novelId,
                        "chapterId": request.chapterId,
                        "targetWordCount": target_word_count,
                        "conversationHistory": conversation_history,
                        "eventSequence": 0,
                        "phase": "active",
                    }
                )
                if request.writingSessionId is not None:
                    message_metadata = workflow_message_metadata(
                        task.id,
                        event_type="user",
                        content=request.userInstruction,
                    )
                    if selection_attachment_metadata is not None:
                        message_metadata_dict = json.loads(message_metadata)
                        message_metadata_dict["source"] = selection_attachment_metadata
                        message_metadata = json.dumps(
                            message_metadata_dict,
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    session.add(
                        WritingMessage(
                            sessionId=request.writingSessionId,
                            role="user",
                            content=request.userInstruction,
                            metadata_=message_metadata,
                        )
                    )
                    await _touch_writing_session(
                        session, request.writingSessionId
                    )
                envelope = {
                    "_inkforgeCommand": {
                        "schemaVersion": 1,
                        "clientRequestId": request.clientRequestId,
                        "commandKind": "start",
                        "resourceIdentity": resource_identity,
                        "normalizedBody": normalized_body,
                        "requestFingerprint": fingerprint,
                    },
                    "job": job,
                }
                command = _new_command(
                    task,
                    kind="start",
                    key=key,
                    payload=envelope,
                )
                session.add(command)
                await session.flush()
                return _run_response(task, command)

    async def _create_short_medium_start(
        self,
        session: AsyncSession,
        user_id: str,
        request: ShortMediumStartWritingRunRequest,
        key: str,
    ) -> WritingRunResponse:
        source = await load_short_medium_run_source(session, user_id, request)
        await self._require_no_active_short_medium_document_run(
            session, user_id, request.novelId
        )
        payload = assemble_short_medium_run_payload(request, source)
        agents_by_operation = {
            "generate_outline": "剧情",
            "generate_manuscript": "写作",
            "replace_selection": "编辑",
            "full_check": "校验",
        }
        task = WritingTask(
            novelId=request.novelId,
            chapterId=source.chapter_id,
            writingSessionId=None,
            phase="idle",
            targetWordCount=source.target_total_word_count,
            selectedAgents=agents_by_operation[request.operation],
            conversationHistory=_dump_json(
                [
                    {
                        "role": "user",
                        "content": request.userInstruction
                        or _short_medium_operation_label(request.operation),
                    }
                ]
            ),
            graphStateJson=_dump_json(
                {
                    **payload.model_dump(mode="json"),
                    "eventSequence": 0,
                    "phase": "active",
                }
            ),
        )
        session.add(task)
        await session.flush()
        command = _new_command(
            task,
            kind="start",
            key=key,
            payload=payload.model_dump(mode="json"),
        )
        session.add(command)
        await session.flush()
        return _run_response(task, command)

    async def _require_no_active_short_medium_document_run(
        self,
        session: AsyncSession,
        user_id: str,
        novel_id: str,
    ) -> None:
        rows = (
            await session.execute(
                select(WritingRunCommand.payloadJson)
                .join(WritingTask, WritingTask.id == WritingRunCommand.taskId)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(
                    Novel.userId == user_id,
                    WritingTask.novelId == novel_id,
                    WritingRunCommand.status.in_(ACTIVE_COMMAND_STATUSES),
                )
                .with_for_update(of=WritingRunCommand)
            )
        ).all()
        for row in rows:
            payload_json = row[0]
            if not isinstance(payload_json, str):
                continue
            payload = _load_json_object(payload_json, field="payloadJson")
            if payload.get("workflow") == "short_medium" and payload.get(
                "operation"
            ) in {
                "generate_outline",
                "generate_manuscript",
                "replace_selection",
            }:
                raise ApiError(
                    status_code=409,
                    code="SHORT_MEDIUM_DOCUMENT_RUN_ACTIVE",
                    message="该中短篇作品已有文档任务正在处理",
                )

    async def get_run_status(
        self, user_id: str, task_id: str
    ) -> WritingRunStatusResponse:
        from .run_queries import WritingRunQueryRepository

        return await WritingRunQueryRepository(self._session_factory).get_run(
            user_id, task_id
        )

    async def list_run_statuses(
        self,
        user_id: str,
        *,
        novel_id: str,
        chapter_id: str | None,
        writing_session_id: str | None,
        operation: str | None,
        outcome: str | None,
        cursor: str | None,
        limit: int,
    ) -> WritingRunListResponse:
        from .run_queries import WritingRunQueryRepository

        return await WritingRunQueryRepository(self._session_factory).list_runs(
            user_id,
            novel_id=novel_id,
            chapter_id=chapter_id,
            writing_session_id=writing_session_id,
            operation=operation,
            outcome=outcome,
            cursor=cursor,
            limit=limit,
        )

    async def create_resume_with_message(
        self,
        user_id: str,
        task_id: str,
        request: ResumeWritingRunRequest,
    ) -> ResumeWritingRunResponse:
        normalized = normalize_json_value(
            request.model_dump(mode="json", exclude={"clientRequestId"})
        )
        if not isinstance(normalized, dict):
            raise RuntimeError("写作恢复请求规范化后不是 JSON 对象")
        normalized_body = normalized
        resource_identity: dict[str, JsonValue] = {"taskId": task_id}
        fingerprint = request_fingerprint(
            command_kind="resume",
            resource_identity=resource_identity,
            body=normalized_body,
        )
        key = enveloped_command_idempotency_key(
            user_id,
            request.clientRequestId,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await acquire_idempotency_lock(
                        session,
                        user_id=user_id,
                        client_request_id=request.clientRequestId,
                    )
                    replay = await _resolve_long_serial_resume_response(
                        self,
                        session,
                        user_id=user_id,
                        task_id=task_id,
                        client_request_id=request.clientRequestId,
                        fingerprint=fingerprint,
                    )
                    if replay is not None:
                        return replay
                    novel_id, chapter_id = await self._require_owned_task_identity(
                        session, user_id, task_id
                    )
                    current_command_id = await self._find_current_command_id(
                        session, task_id
                    )
                    locked_rows = await lock_writing_rows(
                        session,
                        user_id=user_id,
                        request=WritingLockRequest(
                            novel_id=novel_id,
                            chapter_ids=(chapter_id,) if chapter_id is not None else (),
                            task_id=task_id,
                            command_id=current_command_id,
                        ),
                    )
                    task = locked_rows.task
                    if task is None:
                        raise RuntimeError("统一写作锁未返回请求的任务")
                    replay = await _resolve_long_serial_resume_response(
                        self,
                        session,
                        user_id=user_id,
                        task_id=task_id,
                        client_request_id=request.clientRequestId,
                        fingerprint=fingerprint,
                    )
                    if replay is not None:
                        return replay
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
                    awaiting_artifact = await session.scalar(
                        select(ReviewArtifact.id).where(
                            ReviewArtifact.taskId == task.id,
                            ReviewArtifact.novelId == task.novelId,
                            ReviewArtifact.chapterId == task.chapterId,
                            ReviewArtifact.status == "awaiting_user",
                        )
                    )
                    if awaiting_artifact is not None:
                        raise ApiError(
                            status_code=409,
                            code="ARTIFACT_DECISION_REQUIRED",
                            message="存在等待用户决策的审核产物，必须先提交审核决定",
                        )
                    visible_message = (request.userMessage or "").strip()
                    if not visible_message and resolve_recoverable_checkpoint(
                        task, [locked_rows.command] if locked_rows.command else []
                    ) is None:
                        raise ApiError(
                            status_code=409,
                            code="WRITING_RUN_NOT_RECOVERABLE",
                            message="当前写作任务没有可恢复的持久检查点",
                        )
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
                    long_serial_job = await _load_long_serial_resume_job(
                        session,
                        task,
                        resume_input,
                    )
                    job = (
                        long_serial_job
                        if long_serial_job is not None
                        else {
                            "version": 1,
                            "resume": True,
                            "chapterId": task.chapterId,
                            "writingSessionId": task.writingSessionId,
                            "resumeInput": resume_input,
                        }
                    )
                    envelope = {
                        "_inkforgeCommand": {
                            "schemaVersion": 1,
                            "clientRequestId": request.clientRequestId,
                            "commandKind": "resume",
                            "resourceIdentity": resource_identity,
                            "normalizedBody": normalized_body,
                            "requestFingerprint": fingerprint,
                        },
                        "job": job,
                    }
                    command = _new_command(
                        task,
                        kind="resume",
                        key=key,
                        payload=envelope,
                    )
                    session.add(command)
                    await session.flush()
                    await supersede_waiting_for_new_command(
                        session,
                        task_id=task.id,
                    )
                    return _resume_response(command)
        except IntegrityError as exc:
            async with self._session_factory() as session:
                replay = await _resolve_long_serial_resume_response(
                    self,
                    session,
                    user_id=user_id,
                    task_id=task_id,
                    client_request_id=request.clientRequestId,
                    fingerprint=fingerprint,
                )
            if replay is not None:
                return replay
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
                await supersede_waiting_for_new_command(
                    session,
                    task_id=task.id,
                )
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
        key = enveloped_command_idempotency_key(user_id, client_request_id)
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
                job = payload.get("job")
                resume_input = job.get("resumeInput") if isinstance(job, dict) else None
                if isinstance(resume_input, dict):
                    long_serial_job = await _load_long_serial_resume_job(
                        session,
                        task,
                        resume_input,
                    )
                    if long_serial_job is not None:
                        payload = {**payload, "job": long_serial_job}
                persisted_result = {
                    **result,
                    ARTIFACT_DECISION_ACCEPTED_RESPONSE_FIELD: dict(result),
                }
                command = WritingRunCommand(
                    id=command_id,
                    taskId=task_id,
                    kind="artifact_decision",
                    artifactId=artifact_id,
                    decision=decision,
                    payloadJson=_dump_json(payload),
                    resultJson=_dump_json(persisted_result),
                    idempotencyKey=key,
                    status="pending",
                    attemptCount=0,
                    nextAttemptAt=utc_now(),
                )
                session.add(command)
                await session.flush()
                await supersede_waiting_for_new_command(
                    session,
                    task_id=task.id,
                )
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

    async def settle_cancel_dispatch(self, command_id: str) -> WritingCommandRecord:
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
                row = await self._get_by_id(session, command_id, for_update=True)
                if row is None:
                    raise ApiError(
                        status_code=404,
                        code="WRITING_COMMAND_NOT_FOUND",
                        message="写作命令不存在",
                    )
                command, task, owner_id = row
                if logical_command_kind(command.kind, command.payloadJson) != "cancel":
                    raise ApiError(
                        status_code=409,
                        code="WRITING_COMMAND_STATE_CONFLICT",
                        message="只有取消命令可以按取消投递收敛",
                    )
                if command.status in TERMINAL_COMMAND_STATUSES:
                    return _command_record(command, task, owner_id)
                now = utc_now()
                command.status = "succeeded"
                command.completedAt = now
                command.updatedAt = now
                command.lastError = None
                command.resultJson = _dump_json({"effective": True})
                if task.phase not in {"completed", "error"}:
                    mark_task_failed_state(task, "WRITING_RUN_CANCELLED_BY_USER")
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

    async def _require_owned_task_identity(
        self,
        session: AsyncSession,
        user_id: str,
        task_id: str,
    ) -> tuple[str, str | None]:
        row = (
            await session.execute(
                select(WritingTask.novelId, WritingTask.chapterId)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(WritingTask.id == task_id, Novel.userId == user_id)
            )
        ).one_or_none()
        if row is None:
            raise ApiError(
                status_code=404,
                code="WRITING_TASK_NOT_FOUND",
                message="写作任务不存在",
            )
        novel_id, chapter_id = row
        return cast(str, novel_id), cast(str | None, chapter_id)

    async def _find_current_command_id(
        self, session: AsyncSession, task_id: str
    ) -> str | None:
        return cast(
            str | None,
            await session.scalar(
                select(WritingRunCommand.id)
                .where(WritingRunCommand.taskId == task_id)
                .order_by(
                    WritingRunCommand.createdAt.desc(),
                    WritingRunCommand.id.desc(),
                )
                .limit(1)
            ),
        )

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


def _long_serial_operation_definition(
    request: LongSerialStartWritingRunRequest,
) -> PublicOperationDefinition:
    definition = PUBLIC_LONG_SERIAL_OPERATIONS.get(request.operation)
    if definition is None:
        raise ApiError(
            status_code=409,
            code="LONG_SCOPE_NOT_SUPPORTED",
            message="当前长篇操作、目标或范围尚不受支持",
        )
    scope_supported = request.scope.kind in definition.allowedScopeKinds
    identity_supported = False
    if request.operation == "rewrite_outline_selection":
        selection = request.selectionTarget
        if selection is not None and selection.resourceType == "outline_content":
            identity_supported = isinstance(request.scope, NovelScope)
        elif selection is not None and selection.resourceType == "outline_node_content":
            identity_supported = (
                isinstance(request.scope, OutlineNodeScope)
                and request.scope.outlineNodeId == selection.resourceId
            )
    else:
        identity_supported = (
            isinstance(request.scope, ChapterScope)
            and request.scope.chapterId == request.chapterId
        )
    if (
        request.target.type != definition.targetKind
        or request.target.id != request.chapterId
        or not scope_supported
        or not identity_supported
    ):
        raise ApiError(
            status_code=409,
            code="LONG_SCOPE_NOT_SUPPORTED",
            message="当前长篇操作、目标或范围尚不受支持",
        )
    return definition


def _selection_preview(text: str, limit: int = 48) -> str:
    points = list(text)
    if len(points) <= limit:
        return text
    head = (limit + 1) // 2
    tail = limit // 2
    return "".join(points[:head]) + "…" + "".join(points[-tail:])


def _validate_selection_attachment_metadata(
    metadata: SelectionAttachmentMetadata,
    target: SelectionTarget,
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """验证客户端来源卡只引用 Core 已锁定的选区快照。"""

    expected = {
        "resourceType": snapshot["resourceType"],
        "resourceId": snapshot["resourceId"],
        "baseUpdatedAt": _canonical_iso_datetime(str(snapshot["baseUpdatedAt"])),
        "baseContentHash": snapshot["baseContentHash"],
        "selectionStart": snapshot["selectionStart"],
        "selectionEnd": snapshot["selectionEnd"],
        "selectedTextHash": snapshot["selectedTextHash"],
        "selectionPreview": _selection_preview(str(snapshot["selectedText"])),
    }
    actual = metadata.model_dump(mode="json")
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            raise _selection_conflict(target)
    return actual


def _canonical_iso_datetime(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def _capture_selection_snapshot(
    session: AsyncSession,
    *,
    novel_id: str,
    chapter_id: str,
    operation: str,
    target: SelectionTarget,
) -> dict[str, Any]:
    """锁定并从权威文本生成一次性选区快照。"""

    resource_type = target.resourceType
    resource_id = target.resourceId
    content: str | None
    updated_at: datetime | None
    owner_novel_id: str | None
    if resource_type == "chapter_content":
        chapter = await session.scalar(
            select(Chapter)
            .where(Chapter.id == resource_id)
            .with_for_update()
        )
        content = chapter.content if chapter is not None else None
        updated_at = chapter.updatedAt if chapter is not None else None
        owner_novel_id = chapter.novelId if chapter is not None else None
    elif resource_type == "outline_content":
        outline = await session.scalar(
            select(Outline)
            .where(Outline.id == resource_id)
            .with_for_update()
        )
        content = outline.content if outline is not None else None
        updated_at = outline.updatedAt if outline is not None else None
        owner_novel_id = outline.novelId if outline is not None else None
    else:
        node = await session.scalar(
            select(OutlineNode)
            .where(OutlineNode.id == resource_id)
            .with_for_update()
        )
        content = node.content if node is not None else None
        updated_at = node.updatedAt if node is not None else None
        owner_novel_id = node.novelId if node is not None else None

    if (
        owner_novel_id != novel_id
        or content is None
        or updated_at is None
        or (
            resource_type == "chapter_content"
            and resource_id != chapter_id
        )
    ):
        raise _selection_conflict(target)
    if operation == "rewrite_chapter_selection" and resource_type != "chapter_content":
        raise _selection_conflict(target)
    if operation == "rewrite_outline_selection" and resource_type == "chapter_content":
        raise _selection_conflict(target)

    normalized_updated_at = _aware_utc(updated_at)
    full_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    start = target.selectionStart
    end = target.selectionEnd
    if start < 0 or end > len(content) or start >= end:
        raise _selection_conflict(target)
    selected = content[start:end]
    selected_hash = hashlib.sha256(selected.encode("utf-8")).hexdigest()
    if (
        normalized_updated_at != target.baseUpdatedAt.astimezone(UTC)
        or full_hash != target.baseContentHash
        or selected_hash != target.selectedTextHash
    ):
        raise _selection_conflict(target)

    context_size = 1000
    return {
        "resourceType": resource_type,
        "resourceId": resource_id,
        "baseUpdatedAt": normalized_updated_at.isoformat(),
        "baseContentHash": full_hash,
        "selectionStart": start,
        "selectionEnd": end,
        "selectedTextHash": selected_hash,
        "selectedText": selected,
        "contextBefore": content[max(0, start - context_size) : start],
        "contextAfter": content[end : min(len(content), end + context_size)],
        "sourceSnapshot": {
            "resourceType": resource_type,
            "resourceId": resource_id,
            "content": content,
            "updatedAt": normalized_updated_at.isoformat(),
            "contentSha256": full_hash,
        },
    }


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _selection_conflict(target: SelectionTarget) -> ApiError:
    return ApiError(
        status_code=409,
        code="LONG_SELECTION_SOURCE_CONFLICT",
        message="选区来源版本、范围或哈希已变化，请重新选择",
        details={
            "resourceType": target.resourceType,
            "resourceId": target.resourceId,
        },
    )


async def _require_long_serial_profile(
    session: AsyncSession,
    novel_id: str,
) -> None:
    profile = await _story_length_profile(session, novel_id)
    if profile != "long_serial":
        raise ApiError(
            status_code=409,
            code="LONG_WORKFLOW_MISMATCH",
            message="目标小说不是长篇作品",
            details={"novelId": novel_id},
        )


async def _story_length_profile(
    session: AsyncSession,
    novel_id: str,
) -> str | None:
    return cast(
        str | None,
        await session.scalar(
            select(WritingBible.storyLengthProfile)
            .where(WritingBible.novelId == novel_id)
            .with_for_update()
        ),
    )


async def _require_no_active_long_serial_mutation(
    session: AsyncSession,
    chapter_id: str,
) -> None:
    rows = (
        await session.execute(
            select(WritingTask, WritingRunCommand.payloadJson)
            .outerjoin(
                WritingRunCommand,
                and_(
                    WritingRunCommand.taskId == WritingTask.id,
                    WritingRunCommand.kind == "start",
                ),
            )
            .where(
                WritingTask.chapterId == chapter_id,
                WritingTask.phase.not_in(("completed", "error")),
            )
            .order_by(WritingTask.createdAt.asc(), WritingTask.id.asc())
            .with_for_update(of=WritingTask)
        )
    ).all()
    seen: set[str] = set()
    for task, payload_json in rows:
        if task.id in seen:
            continue
        seen.add(task.id)
        if _start_payload_is_mutating(payload_json):
            raise ApiError(
                status_code=409,
                code="WRITING_TARGET_BUSY",
                message="该章节已有正在进行的写入任务",
                details={"taskId": task.id},
            )


def _start_payload_is_mutating(payload_json: object) -> bool:
    if not isinstance(payload_json, str):
        return True
    try:
        payload = _load_json_object(payload_json, field="payloadJson")
        metadata = parse_command_envelope(payload)
    except (RuntimeError, ValueError):
        return True
    if metadata is None:
        return True
    job = payload.get("job")
    if not isinstance(job, dict) or job.get("workflow") != "long_serial":
        return True
    operation = job.get("operation")
    if not isinstance(operation, str):
        return True
    definition = PUBLIC_LONG_SERIAL_OPERATIONS.get(operation)
    return definition is None or definition.mutating


async def _load_long_serial_resume_job(
    session: AsyncSession,
    task: WritingTask,
    resume_input: dict[str, Any],
) -> dict[str, Any] | None:
    start_payload_json = await session.scalar(
        select(WritingRunCommand.payloadJson)
        .where(
            WritingRunCommand.taskId == task.id,
            WritingRunCommand.kind == "start",
        )
        .order_by(WritingRunCommand.createdAt.asc(), WritingRunCommand.id.asc())
        .limit(1)
    )
    if not isinstance(start_payload_json, str):
        return None
    payload = _load_json_object(start_payload_json, field="payloadJson")
    try:
        metadata = parse_command_envelope(payload)
    except ValueError as exc:
        raise RuntimeError("显式长篇启动命令 envelope 无效") from exc
    if metadata is None:
        return None
    job = payload.get("job")
    declares_long_serial = metadata.normalizedBody.get("workflow") == "long_serial"
    if not declares_long_serial and (
        not isinstance(job, dict) or job.get("workflow") != "long_serial"
    ):
        return None
    if (
        metadata.commandKind != "start"
        or set(payload) != {"_inkforgeCommand", "job"}
        or not isinstance(job, dict)
    ):
        raise RuntimeError("显式长篇启动命令缺少权威 job")
    try:
        start = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(job)
    except ValidationError as exc:
        raise RuntimeError("显式长篇启动命令 job 无效") from exc
    if start.resume:
        raise RuntimeError("显式长篇启动命令不能是恢复载荷")
    if (
        start.chapterId != task.chapterId
        or start.writingSessionId != task.writingSessionId
        or start.target.id != task.chapterId
    ):
        raise RuntimeError("显式长篇启动命令与任务身份不一致")
    raw_resume = {
        **start.model_dump(mode="json"),
        "resume": True,
        "resumeInput": resume_input,
    }
    try:
        resume = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(raw_resume)
    except ValidationError as exc:
        raise RuntimeError("显式长篇恢复 job 无效") from exc
    serialized = resume.model_dump(mode="json")
    if resume.selectionTarget is None:
        serialized.pop("selectionTarget", None)
        serialized.pop("selectionSnapshot", None)
    if resume.resumeInput is not None:
        serialized["resumeInput"] = resume.resumeInput.model_dump(
            mode="json",
            exclude_none=True,
        )
    return serialized


async def _resolve_long_serial_resume_response(
    repository: WritingRunCommandRepository,
    session: AsyncSession,
    *,
    user_id: str,
    task_id: str,
    client_request_id: str,
    fingerprint: str,
) -> ResumeWritingRunResponse | None:
    resolution = await resolve_idempotency(
        session,
        user_id=user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
    )
    if resolution is None:
        return None
    if resolution.record_kind != "writing_command":
        raise _idempotency_reused_error(client_request_id)
    row = await repository._get_by_id(
        session,
        resolution.record_id,
        for_update=False,
    )
    if row is None:
        raise _idempotency_reused_error(client_request_id)
    command, task, owner_id = row
    if (
        owner_id != user_id
        or task.id != task_id
        or command.kind != "resume"
    ):
        raise _idempotency_reused_error(client_request_id)
    payload = _load_json_object(command.payloadJson, field="payloadJson")
    job = payload.get("job")
    if (
        set(payload) != {"_inkforgeCommand", "job"}
        or not isinstance(job, dict)
        or job.get("resume") is not True
    ):
        raise _idempotency_reused_error(client_request_id)
    return _resume_response(command)


async def _resolve_long_serial_start_response(
    repository: WritingRunCommandRepository,
    session: AsyncSession,
    *,
    user_id: str,
    client_request_id: str,
    fingerprint: str,
) -> WritingRunResponse | None:
    resolution = await resolve_idempotency(
        session,
        user_id=user_id,
        client_request_id=client_request_id,
        request_fingerprint=fingerprint,
    )
    if resolution is None:
        return None
    if resolution.record_kind != "writing_command":
        raise _idempotency_reused_error(client_request_id)
    row = await repository._get_by_id(
        session,
        resolution.record_id,
        for_update=False,
    )
    if row is None:
        raise _idempotency_reused_error(client_request_id)
    command, task, owner_id = row
    if owner_id != user_id or command.kind != "start":
        raise _idempotency_reused_error(client_request_id)
    payload = _load_json_object(command.payloadJson, field="payloadJson")
    job = payload.get("job")
    if not isinstance(job, dict) or job.get("workflow") != "long_serial":
        raise _idempotency_reused_error(client_request_id)
    return _run_response(task, command)


def _idempotency_reused_error(client_request_id: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        message="同一幂等标识已绑定其他请求",
        details={"clientRequestId": client_request_id},
    )


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
        _load_status_result(command.resultJson)
        if command.resultJson is not None
        else None
    )
    return WritingCommandRecord(
        id=command.id,
        task=_task_record(task, user_id),
        kind=cast(
            WritingCommandKind,
            logical_command_kind(command.kind, command.payloadJson),
        ),
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


def _load_status_result(value: str) -> dict[str, Any]:
    try:
        result = _load_json_object(value, field="resultJson")
    except RuntimeError:
        return {}
    result.pop(TERMINAL_CALLBACK_RESULT_FIELD, None)
    return result


def _dump_json(value: Any) -> str:
    return json.dumps(
        value if value is not None else {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _short_medium_operation_label(operation: str) -> str:
    return {
        "generate_outline": "生成中短篇大纲",
        "generate_manuscript": "生成中短篇正文",
        "replace_selection": "修改中短篇选区",
        "full_check": "检查中短篇全文",
    }[operation]

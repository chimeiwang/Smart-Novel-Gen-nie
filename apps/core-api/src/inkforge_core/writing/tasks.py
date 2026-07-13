from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

from inkforge_contracts.events import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import Chapter, Novel, WritingMessage, WritingSession, WritingTask
from ..errors import ApiError
from .recovery import (
    InvalidGraphSnapshotError,
    deserialize_graph_snapshot,
    validate_resume_session_binding,
)
from .schemas import StartWritingRunRequest, WritingRunResponse
from .sse import EventSequenceGap, WritingEvent

TERMINAL_TASK_PHASES = frozenset({"completed", "error"})


@dataclass(frozen=True, slots=True)
class TaskRecord:
    id: str
    user_id: str
    novel_id: str
    chapter_id: str
    writing_session_id: str | None
    phase: str
    graph_state_json: str | None


class WritingTaskSubmitter(Protocol):
    async def submit(
        self,
        task: TaskRecord,
        *,
        resume: bool,
        resume_input: dict[str, Any] | None = None,
    ) -> None: ...


class WritingTaskRepositoryPort(Protocol):
    async def create_task(
        self, user_id: str, request: StartWritingRunRequest
    ) -> WritingRunResponse: ...

    async def require_task(self, user_id: str, task_id: str) -> TaskRecord: ...

    async def persist_workflow_message(
        self,
        task_id: str,
        *,
        role: str,
        content: str,
        event_type: str,
        agent_id: str | None = None,
    ) -> None: ...

    async def list_reconcilable(self, limit: int) -> list[TaskRecord]: ...


class EventStorePort(Protocol):
    async def append_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, Any],
    ) -> WritingEvent: ...


class WritingCallbackRepositoryPort(Protocol):
    async def persist_workflow_message(
        self,
        task_id: str,
        *,
        role: str,
        content: str,
        event_type: str,
        agent_id: str | None = None,
    ) -> None: ...

    async def save_checkpoint(self, task_id: str, serialized: str, phase: str) -> None: ...

    async def complete(self, task_id: str, result: dict[str, Any]) -> None: ...

    async def fail(self, task_id: str, code: str) -> None: ...


class WritingTaskRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_task(
        self, user_id: str, request: StartWritingRunRequest
    ) -> WritingRunResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await _require_chapter(session, user_id, request.novelId, request.chapterId)
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
                    conversationHistory=json.dumps(
                        [{"role": "user", "content": request.userMessage}],
                        ensure_ascii=False,
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
                            metadata_=_workflow_message_metadata(
                                task.id,
                                event_type="user",
                                content=request.userMessage,
                            ),
                        )
                    )
                    await session.execute(
                        update(WritingSession)
                        .where(WritingSession.id == request.writingSessionId)
                        .values(updatedAt=utc_now())
                    )
            return _task_response(task)

    async def require_task(self, user_id: str, task_id: str) -> TaskRecord:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(WritingTask, Novel.userId)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(WritingTask.id == task_id, Novel.userId == user_id)
                )
            ).one_or_none()
            if row is None:
                raise ApiError(
                    status_code=403,
                    code="WRITING_TASK_FORBIDDEN",
                    message="无权访问该写作任务",
                )
            task, owner_id = row
            return _task_record(task, cast(str, owner_id))

    async def get_task_resources(self, task_id: str) -> tuple[str, str]:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(WritingTask.novelId, Novel.userId)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(WritingTask.id == task_id)
                )
            ).one_or_none()
        if row is None or row.userId is None:
            raise ApiError(
                status_code=404,
                code="WRITING_TASK_NOT_FOUND",
                message="写作任务不存在或缺少归属",
            )
        return row.novelId, row.userId

    async def list_reconcilable(self, limit: int) -> list[TaskRecord]:
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(WritingTask, Novel.userId)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(
                        WritingTask.phase.not_in(TERMINAL_TASK_PHASES),
                        Novel.userId.is_not(None),
                    )
                    .order_by(WritingTask.updatedAt, WritingTask.id)
                    .limit(limit)
                )
            ).all()
        return [_task_record(task, cast(str, owner_id)) for task, owner_id in rows]

    async def save_checkpoint(self, task_id: str, serialized: str, phase: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(WritingTask)
                        .where(
                            WritingTask.id == task_id,
                            WritingTask.phase.not_in(TERMINAL_TASK_PHASES),
                        )
                        .values(
                            graphStateJson=serialized,
                            phase=phase,
                            updatedAt=utc_now(),
                        )
                    ),
                )
                if outcome.rowcount != 1:
                    raise ApiError(
                        status_code=409,
                        code="WRITING_TASK_TERMINAL",
                        message="终态写作任务不能更新检查点",
                    )

    async def complete(self, task_id: str, result: dict[str, Any]) -> None:
        values: dict[str, Any] = {"phase": "completed", "updatedAt": utc_now()}
        final_content = result.get("finalContent", result.get("finalResponse"))
        if isinstance(final_content, str):
            values["finalContent"] = final_content
        if result.get("agentOutputs") is not None:
            values["agentOutputs"] = json.dumps(result["agentOutputs"], ensure_ascii=False)
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    update(WritingTask)
                    .where(
                        WritingTask.id == task_id,
                        WritingTask.phase.not_in(TERMINAL_TASK_PHASES),
                    )
                    .values(**values)
                )

    async def persist_workflow_message(
        self,
        task_id: str,
        *,
        role: str,
        content: str,
        event_type: str,
        agent_id: str | None = None,
    ) -> None:
        visible_content = content.strip()
        if not visible_content:
            return
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(WritingTask, task_id)
                if task is None or task.writingSessionId is None:
                    return
                metadata = _workflow_message_metadata(
                    task_id,
                    event_type=event_type,
                    content=visible_content,
                    agent_id=agent_id,
                )
                existing = await session.scalar(
                    select(WritingMessage.id).where(
                        WritingMessage.sessionId == task.writingSessionId,
                        WritingMessage.metadata_ == metadata,
                    )
                )
                if existing is not None:
                    return
                session.add(
                    WritingMessage(
                        sessionId=task.writingSessionId,
                        role=role,
                        agentId=agent_id,
                        content=visible_content,
                        metadata_=metadata,
                    )
                )
                await session.execute(
                    update(WritingSession)
                    .where(WritingSession.id == task.writingSessionId)
                    .values(updatedAt=utc_now())
                )

    async def fail(self, task_id: str, code: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(WritingTask, task_id)
                if task is None or task.phase in TERMINAL_TASK_PHASES:
                    return
                snapshot: dict[str, Any] = {}
                if task.graphStateJson:
                    try:
                        value = json.loads(task.graphStateJson)
                        if isinstance(value, dict):
                            snapshot = value
                    except json.JSONDecodeError:
                        snapshot = {}
                if snapshot:
                    snapshot["errorMessage"] = f"智能体运行失败：{code}"
                    task.graphStateJson = json.dumps(snapshot, ensure_ascii=False)
                task.phase = "error"


class WritingTaskService:
    def __init__(
        self,
        repository: WritingTaskRepositoryPort,
        submitter: WritingTaskSubmitter | None,
    ) -> None:
        self._repository = repository
        self._submitter = submitter

    async def start(self, user_id: str, request: StartWritingRunRequest) -> WritingRunResponse:
        if self._submitter is None:
            raise ApiError(
                status_code=503,
                code="AGENT_RUN_UNAVAILABLE",
                message="智能体运行队列暂时不可用",
            )
        response = await self._repository.create_task(user_id, request)
        task = await self._repository.require_task(user_id, response.id)
        await self._submitter.submit(task, resume=False, resume_input=None)
        return response

    async def resume(
        self,
        user_id: str,
        task_id: str,
        requested_session_id: str | None,
        resume_input: dict[str, Any] | None = None,
    ) -> None:
        task = await self._repository.require_task(user_id, task_id)
        if task.phase in TERMINAL_TASK_PHASES:
            raise ApiError(
                status_code=409,
                code="WRITING_TASK_TERMINAL",
                message="已完成或失败的任务不能继续恢复",
            )
        try:
            validate_resume_session_binding(requested_session_id, task.writing_session_id)
        except ValueError as exc:
            raise ApiError(
                status_code=409,
                code="WRITING_SESSION_MISMATCH",
                message=str(exc),
            ) from exc
        if self._submitter is None:
            raise ApiError(
                status_code=503,
                code="AGENT_RUN_UNAVAILABLE",
                message="智能体运行队列暂时不可用",
            )
        user_message = resume_input.get("userMessage") if resume_input is not None else None
        if isinstance(user_message, str) and user_message.strip():
            await self._repository.persist_workflow_message(
                task_id,
                role="user",
                content=user_message,
                event_type="user",
            )
        await self._submitter.submit(
            task,
            resume=True,
            resume_input=resume_input,
        )


class WritingCallbackService:
    def __init__(
        self, repository: WritingCallbackRepositoryPort, event_store: EventStorePort
    ) -> None:
        self._repository = repository
        self._events = event_store

    async def accept_event(self, body: AgentEvent) -> None:
        await self._append(
            body.taskId,
            body.eventId,
            body.sequence,
            body.event,
            body.data,
        )

    async def save_checkpoint(
        self, body: CheckpointCallback, *, user_id: str, novel_id: str
    ) -> None:
        serialized = json.dumps(body.checkpoint, ensure_ascii=False)
        try:
            deserialize_graph_snapshot(
                serialized,
                expected_task_id=body.taskId,
                expected_user_id=user_id,
                expected_novel_id=novel_id,
            )
        except InvalidGraphSnapshotError as exc:
            raise ApiError(
                status_code=409,
                code="WRITING_SNAPSHOT_INVALID",
                message=str(exc),
            ) from exc
        await self._append(
            body.taskId,
            body.eventId,
            body.sequence,
            "checkpoint",
            {"phase": body.checkpoint.get("phase")},
        )
        phase = body.checkpoint.get("phase")
        persisted_phase = phase if isinstance(phase, str) else "active"
        await self._repository.save_checkpoint(body.taskId, serialized, persisted_phase)

    async def complete(self, body: RunCompletionCallback) -> None:
        final_response = body.result.get("finalResponse")
        visible_response = final_response.strip() if isinstance(final_response, str) else ""
        event_data: dict[str, Any] = {"taskId": body.taskId}
        if visible_response:
            event_data["finalContent"] = visible_response
        await self._append(
            body.taskId,
            body.eventId,
            body.sequence,
            "completed",
            event_data,
        )
        if visible_response:
            await self._repository.persist_workflow_message(
                body.taskId,
                role="agent",
                content=visible_response,
                event_type="done",
            )
        await self._repository.complete(body.taskId, body.result)

    async def fail(self, body: RunFailureCallback) -> None:
        await self._append(
            body.taskId,
            body.eventId,
            body.sequence,
            "error",
            {
                "message": "智能体运行失败",
                "code": body.code,
                "recoverable": body.recoverable,
            },
        )
        await self._repository.fail(body.taskId, body.code)

    async def _append(
        self,
        task_id: str,
        event_id: str,
        sequence: int,
        event: str,
        data: dict[str, Any],
    ) -> None:
        try:
            await self._events.append_agent_event(
                task_id,
                source_event_id=event_id,
                sequence=sequence,
                event=event,
                data=data,
            )
        except EventSequenceGap as exc:
            raise ApiError(
                status_code=409,
                code="AGENT_EVENT_SEQUENCE_GAP",
                message="智能体事件序号不连续，需要状态对账",
                details={
                    "expectedSequence": exc.expected_sequence,
                    "receivedSequence": exc.received_sequence,
                    "recoverable": True,
                },
            ) from exc


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


def _task_response(task: WritingTask) -> WritingRunResponse:
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
    )


def _workflow_message_metadata(
    task_id: str,
    *,
    event_type: str,
    content: str,
    agent_id: str | None = None,
) -> str:
    return json.dumps(
        {
            "source": "workflow",
            "taskId": task_id,
            "eventType": event_type,
            "agentId": agent_id,
            "contentHash": hashlib.sha256(content.strip().encode()).hexdigest()[:24],
        },
        ensure_ascii=False,
        sort_keys=True,
    )

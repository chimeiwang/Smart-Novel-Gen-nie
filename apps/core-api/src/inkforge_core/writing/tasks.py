from __future__ import annotations

import json
import logging
from typing import Any, Protocol, cast

from inkforge_contracts.events import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from inkforge_contracts.jobs import AgentJobStatus
from sqlalchemy import exists, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import Novel, WritingMessage, WritingRunCommand, WritingSession, WritingTask
from ..errors import ApiError
from .message_metadata import workflow_message_metadata
from .records import TaskRecord
from .recovery import (
    InvalidGraphSnapshotError,
    deserialize_graph_snapshot,
)
from .schemas import (
    ResumeWritingRunRequest,
    ResumeWritingRunResponse,
    StartWritingRunRequest,
    WritingRunResponse,
)
from .sse import EventSequenceGap, WritingEvent

TERMINAL_TASK_PHASES = frozenset({"completed", "error"})
LEGACY_RECONCILABLE_PHASES = frozenset({"active", "waiting_call"})
logger = logging.getLogger(__name__)


class WritingCommandRepositoryPort(Protocol):
    async def create_start_with_task(
        self, user_id: str, request: StartWritingRunRequest
    ) -> WritingRunResponse: ...

    async def create_resume_with_message(
        self,
        user_id: str,
        task_id: str,
        request: ResumeWritingRunRequest,
    ) -> ResumeWritingRunResponse: ...


class ImmediateCommandDispatcher(Protocol):
    async def run_once(self) -> int: ...


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
    async def mark_command_processing(self, task_id: str) -> None: ...

    async def save_checkpoint(self, task_id: str, serialized: str, phase: str) -> None: ...

    async def complete_with_message_and_command(
        self, task_id: str, result: dict[str, Any], visible_response: str
    ) -> None: ...

    async def fail_with_command(self, task_id: str, code: str) -> None: ...


class WritingTaskRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

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
                        WritingTask.phase.in_(LEGACY_RECONCILABLE_PHASES),
                        Novel.userId.is_not(None),
                        ~exists(
                            select(WritingRunCommand.id).where(
                                WritingRunCommand.taskId == WritingTask.id,
                                WritingRunCommand.status.in_(
                                    ("pending", "submitted", "processing")
                                ),
                            )
                        ),
                    )
                    .order_by(WritingTask.updatedAt, WritingTask.id)
                    .limit(limit)
                )
            ).all()
        return [_task_record(task, cast(str, owner_id)) for task, owner_id in rows]

    async def settle_reconciliation_terminal(
        self,
        expected: TaskRecord,
        agent_status: AgentJobStatus,
    ) -> None:
        if agent_status in {"queued", "running"}:
            raise ValueError("活动 Agent job 不能按终态收敛")
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(
                    WritingTask,
                    expected.id,
                    with_for_update=True,
                )
                if (
                    task is None
                    or task.phase != expected.phase
                    or task.graphStateJson != expected.graph_state_json
                    or task.phase not in LEGACY_RECONCILABLE_PHASES
                ):
                    return
                active_command_id = await session.scalar(
                    select(WritingRunCommand.id).where(
                        WritingRunCommand.taskId == task.id,
                        WritingRunCommand.status.in_(
                            ("pending", "submitted", "processing")
                        ),
                    )
                )
                if active_command_id is not None:
                    return
                mark_task_failed_state(
                    task,
                    f"AGENT_JOB_TERMINAL_{agent_status.upper()}",
                )

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
                await _transition_active_command(
                    session,
                    task_id,
                    "succeeded" if phase == "awaiting_user_review" else "processing",
                )

    async def mark_command_processing(self, task_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await _transition_active_command(session, task_id, "processing")

    async def complete_with_message_and_command(
        self, task_id: str, result: dict[str, Any], visible_response: str
    ) -> None:
        values: dict[str, Any] = {"phase": "completed", "updatedAt": utc_now()}
        final_content = result.get("finalContent", result.get("finalResponse"))
        if isinstance(final_content, str):
            values["finalContent"] = final_content
        if result.get("agentOutputs") is not None:
            values["agentOutputs"] = json.dumps(
                result["agentOutputs"], ensure_ascii=False
            )
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(WritingTask, task_id, with_for_update=True)
                if task is None:
                    raise ApiError(
                        status_code=404,
                        code="WRITING_TASK_NOT_FOUND",
                        message="写作任务不存在",
                    )
                if visible_response:
                    await _persist_workflow_message(
                        session,
                        task,
                        role="agent",
                        content=visible_response,
                        event_type="done",
                    )
                if task.phase not in TERMINAL_TASK_PHASES:
                    for name, value in values.items():
                        setattr(task, name, value)
                await _transition_active_command(
                    session,
                    task_id,
                    "succeeded",
                    result=result,
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
                if task is None:
                    return
                await _persist_workflow_message(
                    session,
                    task,
                    role=role,
                    content=visible_content,
                    event_type=event_type,
                    agent_id=agent_id,
                )

    async def fail_with_command(self, task_id: str, code: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(WritingTask, task_id, with_for_update=True)
                if task is None:
                    return
                mark_task_failed_state(task, code)
                await _transition_active_command(
                    session,
                    task_id,
                    "failed",
                    result={"code": code},
                )


class WritingTaskService:
    def __init__(
        self,
        repository: WritingCommandRepositoryPort,
        dispatcher: ImmediateCommandDispatcher | None,
    ) -> None:
        self._repository = repository
        self._dispatcher = dispatcher

    async def start(self, user_id: str, request: StartWritingRunRequest) -> WritingRunResponse:
        response = await self._repository.create_start_with_task(user_id, request)
        await self._kick_dispatcher()
        return response

    async def resume(
        self,
        user_id: str,
        task_id: str,
        request: ResumeWritingRunRequest,
    ) -> ResumeWritingRunResponse:
        response = await self._repository.create_resume_with_message(
            user_id, task_id, request
        )
        await self._kick_dispatcher()
        return response

    async def _kick_dispatcher(self) -> None:
        if self._dispatcher is None:
            return
        try:
            await self._dispatcher.run_once()
        except Exception:
            logger.warning("写作命令即时投递失败，已交由后台重试")


class WritingCallbackService:
    def __init__(
        self, repository: WritingCallbackRepositoryPort, event_store: EventStorePort
    ) -> None:
        self._repository = repository
        self._events = event_store

    async def accept_event(self, body: AgentEvent) -> None:
        await self._repository.mark_command_processing(body.taskId)
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
        phase = body.checkpoint.get("phase")
        persisted_phase = phase if isinstance(phase, str) else "active"
        await self._repository.save_checkpoint(body.taskId, serialized, persisted_phase)
        await self._append(
            body.taskId,
            body.eventId,
            body.sequence,
            "checkpoint",
            {"phase": body.checkpoint.get("phase")},
        )

    async def complete(self, body: RunCompletionCallback) -> None:
        final_response = body.result.get("finalResponse")
        visible_response = final_response.strip() if isinstance(final_response, str) else ""
        event_data: dict[str, Any] = {"taskId": body.taskId}
        if visible_response:
            event_data["finalContent"] = visible_response
        await self._repository.complete_with_message_and_command(
            body.taskId, body.result, visible_response
        )
        await self._append(
            body.taskId,
            body.eventId,
            body.sequence,
            "completed",
            event_data,
        )

    async def fail(self, body: RunFailureCallback) -> None:
        await self._repository.fail_with_command(body.taskId, body.code)
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


async def _persist_workflow_message(
    session: AsyncSession,
    task: WritingTask,
    *,
    role: str,
    content: str,
    event_type: str,
    agent_id: str | None = None,
) -> None:
    visible_content = content.strip()
    if not visible_content or task.writingSessionId is None:
        return
    metadata = workflow_message_metadata(
        task.id,
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


async def _transition_active_command(
    session: AsyncSession,
    task_id: str,
    target: str,
    *,
    result: dict[str, Any] | None = None,
) -> None:
    command = await session.scalar(
        select(WritingRunCommand)
        .where(
            WritingRunCommand.taskId == task_id,
            WritingRunCommand.status.in_(("pending", "submitted", "processing")),
        )
        .with_for_update()
    )
    if command is None:
        return
    now = utc_now()
    if target == "processing":
        if command.status == "processing":
            return
        command.status = "processing"
        command.submittedAt = command.submittedAt or now
        command.lastError = None
        command.updatedAt = now
        return
    command.status = target
    command.completedAt = now
    command.updatedAt = now
    if command.resultJson is None and result is not None:
        command.resultJson = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def mark_task_failed_state(task: WritingTask, code: str) -> None:
    if task.phase in TERMINAL_TASK_PHASES:
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
    task.updatedAt = utc_now()


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

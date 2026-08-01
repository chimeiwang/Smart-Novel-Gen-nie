from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol, cast

from inkforge_contracts.events import (
    AgentEvent,
    CallbackReceipt,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from inkforge_contracts.jobs import AgentJobStatus
from pydantic import JsonValue
from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import Novel, WritingMessage, WritingRunCommand, WritingSession, WritingTask
from ..errors import ApiError
from ..short_medium.completion import finalize_short_medium_completion
from .job_identity import build_writing_job_id
from .message_metadata import workflow_message_metadata
from .outbox import BoundaryEvent, OutboxRegistration, enqueue_boundary_event
from .records import TaskRecord
from .recovery import (
    InvalidGraphSnapshotError,
    deserialize_graph_snapshot,
)
from .schemas import (
    ResumeWritingRunRequest,
    ResumeWritingRunResponse,
    WritingCommandStatus,
    WritingRunResponse,
    WritingRunStartRequest,
    WritingRunStatusResponse,
)
from .sse import EventSequenceGap, EventSourceConflict, WritingEvent

TERMINAL_TASK_PHASES = frozenset({"completed", "error"})
LEGACY_RECONCILABLE_PHASES = frozenset({"active", "waiting_call"})
ACTIVE_CALLBACK_COMMAND_STATUSES = frozenset({"pending", "submitted", "processing"})
CALLBACK_JOB_ID_FIELD = "callbackJobId"
JOB_MISMATCH_CODE = "WRITING_JOB_MISMATCH"
SEQUENCE_STALE_CODE = "WRITING_CALLBACK_SEQUENCE_STALE"
ALREADY_APPLIED_CODE = "WRITING_CALLBACK_ALREADY_APPLIED"
STATE_NOOP_CODE = "WRITING_CALLBACK_STATE_NOOP"
CHECKPOINT_CONFLICT_CODE = "WRITING_CHECKPOINT_CONFLICT"
CALLBACK_RESULT_CONFLICT_CODE = "WRITING_CALLBACK_RESULT_CONFLICT"
OUTBOX_BOUNDARY_CONFLICT_CODE = "WRITING_OUTBOX_BOUNDARY_CONFLICT"
EVENT_SOURCE_CONFLICT_CODE = "WRITING_EVENT_SOURCE_CONFLICT"
TERMINAL_CALLBACK_RESULT_FIELD = "_inkforgeTerminalCallbackResult"
logger = logging.getLogger(__name__)


class WritingCommandRepositoryPort(Protocol):
    async def create_start_with_task(
        self, user_id: str, request: WritingRunStartRequest
    ) -> WritingRunResponse: ...

    async def get_run_status(
        self, user_id: str, task_id: str
    ) -> WritingRunStatusResponse: ...

    async def create_resume_with_message(
        self,
        user_id: str,
        task_id: str,
        request: ResumeWritingRunRequest,
    ) -> ResumeWritingRunResponse: ...


class ImmediateCommandDispatcher(Protocol):
    async def run_once(self) -> int: ...


class EventStorePort(Protocol):
    async def validate_agent_event_source(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, Any],
    ) -> bool: ...

    async def validate_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, Any],
        durable_baseline: int,
        allow_rebase: bool,
    ) -> bool: ...

    async def append_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
        event: str,
        data: dict[str, Any],
        durable_baseline: int,
        allow_rebase: bool,
    ) -> WritingEvent: ...


@dataclass(frozen=True, slots=True)
class CallbackAcceptance:
    accepted: bool
    persisted_sequence: int
    already_applied: bool = False
    rejection_code: str | None = None
    task_phase: str | None = None
    command_status: WritingCommandStatus | None = None
    outbox_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class _CallbackTarget:
    task: WritingTask
    command: WritingRunCommand | None
    already_applied: bool


@dataclass(frozen=True, slots=True)
class _CallbackPreparation:
    should_continue: bool
    should_publish: bool
    durable_baseline: int
    acceptance: CallbackAcceptance


class WritingCallbackRepositoryPort(Protocol):
    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance: ...

    async def mark_command_processing(
        self, task_id: str, job_id: str, sequence: int
    ) -> CallbackAcceptance: ...

    async def save_checkpoint(
        self,
        task_id: str,
        job_id: str,
        serialized: str,
        phase: str,
        sequence: int,
        boundary: BoundaryEvent | None = None,
    ) -> CallbackAcceptance: ...

    async def complete_with_message_and_command(
        self,
        task_id: str,
        job_id: str,
        result: dict[str, Any],
        visible_response: str,
        sequence: int,
        boundary: BoundaryEvent | None = None,
    ) -> CallbackAcceptance: ...

    async def fail_with_command(
        self,
        task_id: str,
        job_id: str,
        code: str,
        sequence: int,
        boundary: BoundaryEvent | None = None,
    ) -> CallbackAcceptance: ...


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

    async def create_reconciliation_command(self, expected: TaskRecord) -> bool:
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
                    return False
                active_command_id = await session.scalar(
                    select(WritingRunCommand.id).where(
                        WritingRunCommand.taskId == task.id,
                        WritingRunCommand.status.in_(ACTIVE_CALLBACK_COMMAND_STATUSES),
                    )
                )
                if active_command_id is not None:
                    return False
                resume = task.graphStateJson is not None
                command_id = build_writing_job_id(
                    task.id,
                    resume=resume,
                    graph_state_json=task.graphStateJson,
                )
                existing = await session.get(
                    WritingRunCommand,
                    command_id,
                    with_for_update=True,
                )
                if existing is not None:
                    return False
                payload = {
                    "version": 1,
                    "resume": resume,
                    "chapterId": task.chapterId,
                    "writingSessionId": task.writingSessionId,
                    "resumeInput": None,
                    "force": True,
                }
                session.add(
                    WritingRunCommand(
                        id=command_id,
                        taskId=task.id,
                        kind="resume" if resume else "start",
                        payloadJson=json.dumps(
                            payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        idempotencyKey=f"reconcile:{command_id}",
                        status="pending",
                        attemptCount=0,
                        nextAttemptAt=utc_now(),
                    )
                )
                await session.flush()
                return True

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

    async def authorize_callback(
        self, task_id: str, job_id: str
    ) -> CallbackAcceptance:
        async with self._session_factory() as session:
            async with session.begin():
                target = await _lock_callback_target(session, task_id, job_id)
                if target is None:
                    return CallbackAcceptance(
                        False, 0, rejection_code=JOB_MISMATCH_CODE
                    )
                return _target_acceptance(
                    target,
                    accepted=True,
                    persisted_sequence=_persisted_event_sequence(target.task),
                    already_applied=target.already_applied,
                )

    async def save_checkpoint(
        self,
        task_id: str,
        job_id: str,
        serialized: str,
        phase: str,
        sequence: int,
        boundary: BoundaryEvent | None = None,
    ) -> CallbackAcceptance:
        async with self._session_factory() as session:
            async with session.begin():
                target = await _lock_callback_target(session, task_id, job_id)
                if target is None:
                    return CallbackAcceptance(
                        False, 0, rejection_code=JOB_MISMATCH_CODE
                    )
                persisted_sequence = _persisted_event_sequence(target.task)
                if sequence < persisted_sequence:
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=SEQUENCE_STALE_CODE,
                    )
                if sequence == persisted_sequence:
                    identical = target.task.graphStateJson == serialized
                    registration = (
                        await _enqueue_target_boundary(
                            session,
                            target,
                            boundary,
                            durable_baseline=None,
                        )
                        if identical
                        else OutboxRegistration(outbox_id=None)
                    )
                    if registration.conflict:
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                        )
                    return _target_acceptance(
                        target,
                        accepted=identical,
                        persisted_sequence=persisted_sequence,
                        already_applied=identical,
                        rejection_code=(
                            None if identical else CHECKPOINT_CONFLICT_CODE
                        ),
                        outbox_event_id=registration.outbox_id,
                    )
                if target.already_applied or target.task.phase in TERMINAL_TASK_PHASES:
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=ALREADY_APPLIED_CODE,
                    )
                phase = _checkpoint_phase_for_locked_command(
                    target.command,
                    target.task,
                    serialized,
                    fallback_phase=phase,
                )
                registration = await _enqueue_target_boundary(
                    session,
                    target,
                    boundary,
                    durable_baseline=persisted_sequence,
                )
                if registration.conflict:
                    return _target_acceptance(
                        target,
                        accepted=False,
                        persisted_sequence=persisted_sequence,
                        rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                    )
                target.task.graphStateJson = serialized
                target.task.phase = phase
                target.task.updatedAt = utc_now()
                _transition_callback_command(
                    target.command,
                    "succeeded" if phase == "awaiting_user_review" else "processing",
                )
                return _target_acceptance(
                    target,
                    accepted=True,
                    persisted_sequence=persisted_sequence,
                    outbox_event_id=registration.outbox_id,
                )

    async def mark_command_processing(
        self, task_id: str, job_id: str, sequence: int
    ) -> CallbackAcceptance:
        async with self._session_factory() as session:
            async with session.begin():
                target = await _lock_callback_target(session, task_id, job_id)
                if target is None:
                    return CallbackAcceptance(
                        False, 0, rejection_code=JOB_MISMATCH_CODE
                    )
                persisted_sequence = _persisted_event_sequence(target.task)
                if sequence <= persisted_sequence:
                    return _target_acceptance(
                        target,
                        accepted=False,
                        persisted_sequence=persisted_sequence,
                        rejection_code=SEQUENCE_STALE_CODE,
                    )
                if target.already_applied:
                    return _target_acceptance(
                        target,
                        accepted=False,
                        persisted_sequence=persisted_sequence,
                        rejection_code=ALREADY_APPLIED_CODE,
                    )
                _transition_callback_command(target.command, "processing")
                return _target_acceptance(
                    target,
                    accepted=True,
                    persisted_sequence=persisted_sequence,
                )

    async def complete_with_message_and_command(
        self,
        task_id: str,
        job_id: str,
        result: dict[str, Any],
        visible_response: str,
        sequence: int,
        boundary: BoundaryEvent | None = None,
    ) -> CallbackAcceptance:
        callback_result = dict(result)
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
                target = await _lock_callback_target(session, task_id, job_id)
                if target is None:
                    return CallbackAcceptance(
                        False, 0, rejection_code=JOB_MISMATCH_CODE
                    )
                task = target.task
                persisted_sequence = _persisted_event_sequence(task)
                if sequence <= persisted_sequence:
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=SEQUENCE_STALE_CODE,
                    )
                if target.command is None and task.phase in TERMINAL_TASK_PHASES:
                    if task.phase != "completed":
                        return CallbackAcceptance(
                            False,
                            persisted_sequence,
                            rejection_code=STATE_NOOP_CODE,
                        )
                    if not _task_completion_result_compatible(task, result):
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=CALLBACK_RESULT_CONFLICT_CODE,
                        )
                    registration = await _enqueue_target_boundary(
                        session,
                        target,
                        boundary,
                        durable_baseline=persisted_sequence,
                    )
                    if registration.conflict:
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                        )
                    for name, value in values.items():
                        if name != "phase":
                            setattr(task, name, value)
                    return _target_acceptance(
                        target,
                        accepted=True,
                        persisted_sequence=persisted_sequence,
                        already_applied=True,
                        outbox_event_id=registration.outbox_id,
                    )
                if target.already_applied:
                    accepted = (
                        target.command is not None
                        and target.command.status == "succeeded"
                    )
                    if accepted and not _completion_result_compatible(
                        task,
                        target.command,
                        result,
                    ):
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=CALLBACK_RESULT_CONFLICT_CODE,
                        )
                    registration = (
                        await _enqueue_target_boundary(
                            session,
                            target,
                            boundary,
                            durable_baseline=persisted_sequence,
                        )
                        if accepted
                        else OutboxRegistration(outbox_id=None)
                    )
                    if registration.conflict:
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                        )
                    return _target_acceptance(
                        target,
                        accepted=accepted,
                        persisted_sequence=persisted_sequence,
                        already_applied=accepted,
                        rejection_code=None if accepted else STATE_NOOP_CODE,
                        outbox_event_id=registration.outbox_id,
                    )
                if task.phase == "error":
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=STATE_NOOP_CODE,
                    )
                registration = await _enqueue_target_boundary(
                    session,
                    target,
                    boundary,
                    durable_baseline=persisted_sequence,
                )
                if registration.conflict:
                    return _target_acceptance(
                        target,
                        accepted=False,
                        persisted_sequence=persisted_sequence,
                        rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                    )
                if (
                    target.command is not None
                    and _is_short_medium_command(target.command)
                ):
                    result = await finalize_short_medium_completion(
                        session,
                        task,
                        target.command,
                        result,
                    )
                if visible_response:
                    await _persist_workflow_message(
                        session,
                        task,
                        role="agent",
                        content=visible_response,
                        event_type="done",
                    )
                for name, value in values.items():
                    if name != "phase" or task.phase not in TERMINAL_TASK_PHASES:
                        setattr(task, name, value)
                _transition_callback_command(
                    target.command,
                    "succeeded",
                    result=result,
                    callback_result=callback_result,
                )
                return _target_acceptance(
                    target,
                    accepted=True,
                    persisted_sequence=persisted_sequence,
                    outbox_event_id=registration.outbox_id,
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

    async def fail_with_command(
        self,
        task_id: str,
        job_id: str,
        code: str,
        sequence: int,
        boundary: BoundaryEvent | None = None,
    ) -> CallbackAcceptance:
        async with self._session_factory() as session:
            async with session.begin():
                target = await _lock_callback_target(session, task_id, job_id)
                if target is None:
                    return CallbackAcceptance(
                        False, 0, rejection_code=JOB_MISMATCH_CODE
                    )
                persisted_sequence = _persisted_event_sequence(target.task)
                if sequence <= persisted_sequence:
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=SEQUENCE_STALE_CODE,
                    )
                if (
                    target.command is None
                    and target.task.phase in TERMINAL_TASK_PHASES
                ):
                    accepted = target.task.phase == "error"
                    if accepted and not _task_failure_result_compatible(
                        target.task,
                        code,
                    ):
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=CALLBACK_RESULT_CONFLICT_CODE,
                        )
                    registration = (
                        await _enqueue_target_boundary(
                            session,
                            target,
                            boundary,
                            durable_baseline=persisted_sequence,
                        )
                        if accepted
                        else OutboxRegistration(outbox_id=None)
                    )
                    if registration.conflict:
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                        )
                    return _target_acceptance(
                        target,
                        accepted=accepted,
                        persisted_sequence=persisted_sequence,
                        already_applied=accepted,
                        rejection_code=None if accepted else STATE_NOOP_CODE,
                        outbox_event_id=registration.outbox_id,
                    )
                if target.already_applied:
                    accepted = (
                        target.command is not None and target.command.status == "failed"
                    )
                    if accepted and not _failure_result_compatible(
                        target.task,
                        target.command,
                        code,
                    ):
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=CALLBACK_RESULT_CONFLICT_CODE,
                        )
                    registration = (
                        await _enqueue_target_boundary(
                            session,
                            target,
                            boundary,
                            durable_baseline=persisted_sequence,
                        )
                        if accepted
                        else OutboxRegistration(outbox_id=None)
                    )
                    if registration.conflict:
                        return _target_acceptance(
                            target,
                            accepted=False,
                            persisted_sequence=persisted_sequence,
                            rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                        )
                    return _target_acceptance(
                        target,
                        accepted=accepted,
                        persisted_sequence=persisted_sequence,
                        already_applied=accepted,
                        rejection_code=None if accepted else STATE_NOOP_CODE,
                        outbox_event_id=registration.outbox_id,
                    )
                registration = await _enqueue_target_boundary(
                    session,
                    target,
                    boundary,
                    durable_baseline=persisted_sequence,
                )
                if registration.conflict:
                    return _target_acceptance(
                        target,
                        accepted=False,
                        persisted_sequence=persisted_sequence,
                        rejection_code=OUTBOX_BOUNDARY_CONFLICT_CODE,
                    )
                mark_task_failed_state(target.task, code)
                _transition_callback_command(
                    target.command,
                    "failed",
                    result={"code": code},
                    callback_result={"code": code},
                )
                return _target_acceptance(
                    target,
                    accepted=True,
                    persisted_sequence=persisted_sequence,
                    outbox_event_id=registration.outbox_id,
                )


class WritingTaskService:
    def __init__(
        self,
        repository: WritingCommandRepositoryPort,
        dispatcher: ImmediateCommandDispatcher | None,
    ) -> None:
        self._repository = repository
        self._dispatcher = dispatcher

    async def start(
        self, user_id: str, request: WritingRunStartRequest
    ) -> WritingRunResponse:
        response = await self._repository.create_start_with_task(user_id, request)
        await self._kick_dispatcher()
        return response

    async def get_status(
        self, user_id: str, task_id: str
    ) -> WritingRunStatusResponse:
        return await self._repository.get_run_status(user_id, task_id)

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

    async def accept_event(self, body: AgentEvent) -> CallbackReceipt:
        preparation = await self._prepare_callback(
            task_id=body.taskId,
            job_id=body.jobId,
            event_id=body.eventId,
            sequence=body.sequence,
            callback_event=body.event,
            callback_data=body.data,
            ignore_when_already_applied=True,
        )
        if not preparation.should_continue:
            return _callback_receipt(preparation.acceptance)
        acceptance = await self._repository.mark_command_processing(
            body.taskId, body.jobId, body.sequence
        )
        if not acceptance.accepted:
            _log_callback_outcome(
                acceptance.rejection_code or STATE_NOOP_CODE,
                body.taskId,
                body.jobId,
                body.eventId,
            )
            return _callback_receipt(acceptance)
        if preparation.should_publish:
            try:
                await self._append(
                    body.taskId,
                    body.eventId,
                    body.sequence,
                    body.event,
                    body.data,
                    durable_baseline=preparation.durable_baseline,
                )
            except EventSourceConflict:
                return _callback_receipt(
                    _callback_rejection(acceptance, EVENT_SOURCE_CONFLICT_CODE)
                )
        return _callback_receipt(acceptance)

    async def save_checkpoint(
        self, body: CheckpointCallback, *, user_id: str, novel_id: str
    ) -> CallbackReceipt:
        checkpoint = dict(body.checkpoint)
        checkpoint[CALLBACK_JOB_ID_FIELD] = body.jobId
        serialized = json.dumps(checkpoint, ensure_ascii=False)
        is_short_medium = checkpoint.get("workflow") == "short_medium"
        if is_short_medium:
            if checkpoint.get("operation") not in {
                "generate_outline",
                "generate_manuscript",
                "replace_selection",
                "full_check",
            } or checkpoint.get("phase") not in {"generating", "completed"}:
                raise ApiError(
                    status_code=409,
                    code="WRITING_SNAPSHOT_INVALID",
                    message="中短篇检查点格式无效",
                )
        else:
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
        checkpoint_sequence = _checkpoint_event_sequence(checkpoint)
        if checkpoint_sequence != body.sequence:
            raise ApiError(
                status_code=409,
                code="WRITING_CHECKPOINT_SEQUENCE_MISMATCH",
                message="检查点事件序号与回调序号不一致",
            )
        phase = checkpoint.get("phase")
        persisted_phase = (
            "active"
            if is_short_medium
            else phase if isinstance(phase, str) else "active"
        )
        waiting_payload: dict[str, JsonValue] = {"taskId": body.taskId}
        artifact_id = checkpoint.get("activeArtifactId")
        if isinstance(artifact_id, str) and artifact_id:
            waiting_payload["artifactId"] = artifact_id
            active_agent = checkpoint.get("activeAgent")
            waiting_payload["agentId"] = (
                active_agent
                if isinstance(active_agent, str) and active_agent
                else "系统"
            )
        boundary = (
            BoundaryEvent(
                source_event_id=body.eventId,
                source_sequence=body.sequence,
                dedupe_key=f"writing:{body.jobId}:waiting:{body.sequence}",
                event_type="artifact_awaiting_user_approval",
                payload=waiting_payload,
            )
            if not is_short_medium and persisted_phase == "awaiting_user_review"
            else None
        )
        if boundary is not None:
            acceptance = await self._repository.save_checkpoint(
                body.taskId,
                body.jobId,
                serialized,
                persisted_phase,
                body.sequence,
                boundary,
            )
            if not acceptance.accepted:
                _log_callback_outcome(
                    acceptance.rejection_code or STATE_NOOP_CODE,
                    body.taskId,
                    body.jobId,
                    body.eventId,
                )
            return _callback_receipt(acceptance)

        preparation = await self._prepare_callback(
            task_id=body.taskId,
            job_id=body.jobId,
            event_id=body.eventId,
            sequence=body.sequence,
            callback_event="checkpoint",
            callback_data={"phase": checkpoint.get("phase")},
            allow_persisted_equal=True,
            continue_on_duplicate=True,
        )
        if not preparation.should_continue:
            return _callback_receipt(preparation.acceptance)
        acceptance = await self._repository.save_checkpoint(
            body.taskId,
            body.jobId,
            serialized,
            persisted_phase,
            body.sequence,
            None,
        )
        if not acceptance.accepted:
            _log_callback_outcome(
                acceptance.rejection_code or STATE_NOOP_CODE,
                body.taskId,
                body.jobId,
                body.eventId,
            )
            return _callback_receipt(acceptance)
        if preparation.should_publish:
            try:
                await self._append(
                    body.taskId,
                    body.eventId,
                    body.sequence,
                    "checkpoint",
                    {"phase": checkpoint.get("phase")},
                    durable_baseline=preparation.durable_baseline,
                )
            except EventSourceConflict:
                return _callback_receipt(
                    _callback_rejection(acceptance, EVENT_SOURCE_CONFLICT_CODE)
                )
        return _callback_receipt(acceptance)

    async def complete(self, body: RunCompletionCallback) -> CallbackReceipt:
        final_response = body.result.get("finalResponse")
        visible_response = final_response.strip() if isinstance(final_response, str) else ""
        boundary = BoundaryEvent(
            source_event_id=body.eventId,
            source_sequence=body.sequence,
            dedupe_key=f"writing:{body.jobId}:terminal",
            event_type="completed",
            payload={
                "taskId": body.taskId,
                "resultSha256": _callback_result_digest(body.result),
            },
        )
        acceptance = await self._repository.complete_with_message_and_command(
            body.taskId,
            body.jobId,
            body.result,
            visible_response,
            body.sequence,
            boundary,
        )
        if not acceptance.accepted:
            _log_callback_outcome(
                acceptance.rejection_code or STATE_NOOP_CODE,
                body.taskId,
                body.jobId,
                body.eventId,
            )
        return _callback_receipt(acceptance)

    async def fail(self, body: RunFailureCallback) -> CallbackReceipt:
        boundary = BoundaryEvent(
            source_event_id=body.eventId,
            source_sequence=body.sequence,
            dedupe_key=f"writing:{body.jobId}:terminal",
            event_type="error",
            payload={
                "message": "智能体运行失败",
                "code": body.code,
                "recoverable": body.recoverable,
            },
        )
        acceptance = await self._repository.fail_with_command(
            body.taskId,
            body.jobId,
            body.code,
            body.sequence,
            boundary,
        )
        if not acceptance.accepted:
            _log_callback_outcome(
                acceptance.rejection_code or STATE_NOOP_CODE,
                body.taskId,
                body.jobId,
                body.eventId,
            )
        return _callback_receipt(acceptance)

    async def _prepare_callback(
        self,
        *,
        task_id: str,
        job_id: str,
        event_id: str,
        sequence: int,
        callback_event: str,
        callback_data: dict[str, Any],
        allow_persisted_equal: bool = False,
        ignore_when_already_applied: bool = False,
        continue_on_duplicate: bool = False,
    ) -> _CallbackPreparation:
        authorization = await self._repository.authorize_callback(task_id, job_id)
        if not authorization.accepted:
            rejection = _callback_rejection(
                authorization,
                authorization.rejection_code or JOB_MISMATCH_CODE,
            )
            _log_callback_outcome(
                rejection.rejection_code or JOB_MISMATCH_CODE,
                task_id,
                job_id,
                event_id,
            )
            return _CallbackPreparation(
                should_continue=False,
                should_publish=False,
                durable_baseline=authorization.persisted_sequence,
                acceptance=rejection,
            )
        try:
            source_unseen = await self._events.validate_agent_event_source(
                task_id,
                source_event_id=event_id,
                sequence=sequence,
                event=callback_event,
                data=callback_data,
            )
        except EventSourceConflict:
            rejection = _callback_rejection(
                authorization,
                EVENT_SOURCE_CONFLICT_CODE,
            )
            _log_callback_outcome(
                EVENT_SOURCE_CONFLICT_CODE,
                task_id,
                job_id,
                event_id,
            )
            return _CallbackPreparation(
                should_continue=False,
                should_publish=False,
                durable_baseline=authorization.persisted_sequence,
                acceptance=rejection,
            )
        if not source_unseen and not continue_on_duplicate:
            return _CallbackPreparation(
                should_continue=False,
                should_publish=False,
                durable_baseline=authorization.persisted_sequence,
                acceptance=replace(authorization, already_applied=True),
            )
        if ignore_when_already_applied and authorization.already_applied:
            _log_callback_outcome(
                ALREADY_APPLIED_CODE,
                task_id,
                job_id,
                event_id,
            )
            return _CallbackPreparation(
                should_continue=False,
                should_publish=False,
                durable_baseline=authorization.persisted_sequence,
                acceptance=authorization,
            )
        if sequence < authorization.persisted_sequence:
            rejection = _callback_rejection(authorization, SEQUENCE_STALE_CODE)
            _log_callback_outcome(
                SEQUENCE_STALE_CODE,
                task_id,
                job_id,
                event_id,
            )
            return _CallbackPreparation(
                should_continue=False,
                should_publish=False,
                durable_baseline=authorization.persisted_sequence,
                acceptance=rejection,
            )
        if sequence == authorization.persisted_sequence:
            if not allow_persisted_equal:
                rejection = _callback_rejection(
                    authorization, SEQUENCE_STALE_CODE
                )
                _log_callback_outcome(
                    SEQUENCE_STALE_CODE,
                    task_id,
                    job_id,
                    event_id,
                )
                return _CallbackPreparation(
                    should_continue=False,
                    should_publish=False,
                    durable_baseline=authorization.persisted_sequence,
                    acceptance=rejection,
                )
            durable_baseline = max(0, sequence - 1)
        else:
            durable_baseline = authorization.persisted_sequence
        try:
            should_publish = await self._validate_event_sequence(
                task_id,
                event_id,
                sequence,
                event=callback_event,
                data=callback_data,
                durable_baseline=durable_baseline,
            )
        except EventSourceConflict:
            rejection = _callback_rejection(
                authorization,
                EVENT_SOURCE_CONFLICT_CODE,
            )
            _log_callback_outcome(
                EVENT_SOURCE_CONFLICT_CODE,
                task_id,
                job_id,
                event_id,
            )
            return _CallbackPreparation(
                should_continue=False,
                should_publish=False,
                durable_baseline=durable_baseline,
                acceptance=rejection,
            )
        if not should_publish and not continue_on_duplicate:
            return _CallbackPreparation(
                should_continue=False,
                should_publish=False,
                durable_baseline=durable_baseline,
                acceptance=replace(authorization, already_applied=True),
            )
        return _CallbackPreparation(
            should_continue=True,
            should_publish=should_publish,
            durable_baseline=durable_baseline,
            acceptance=authorization,
        )

    async def _validate_event_sequence(
        self,
        task_id: str,
        event_id: str,
        sequence: int,
        *,
        event: str,
        data: dict[str, Any],
        durable_baseline: int,
    ) -> bool:
        try:
            return await self._events.validate_agent_event(
                task_id,
                source_event_id=event_id,
                sequence=sequence,
                event=event,
                data=data,
                durable_baseline=durable_baseline,
                allow_rebase=True,
            )
        except EventSequenceGap as exc:
            raise _event_sequence_gap_error(exc) from exc

    async def _append(
        self,
        task_id: str,
        event_id: str,
        sequence: int,
        event: str,
        data: dict[str, Any],
        *,
        durable_baseline: int,
    ) -> None:
        try:
            await self._events.append_agent_event(
                task_id,
                source_event_id=event_id,
                sequence=sequence,
                event=event,
                data=data,
                durable_baseline=durable_baseline,
                allow_rebase=True,
            )
        except EventSequenceGap as exc:
            raise _event_sequence_gap_error(exc) from exc


def _callback_rejection(
    acceptance: CallbackAcceptance,
    code: str,
) -> CallbackAcceptance:
    return CallbackAcceptance(
        accepted=False,
        persisted_sequence=acceptance.persisted_sequence,
        rejection_code=code,
        task_phase=acceptance.task_phase,
        command_status=acceptance.command_status,
        outbox_event_id=acceptance.outbox_event_id,
    )


def _callback_receipt(acceptance: CallbackAcceptance) -> CallbackReceipt:
    disposition: Literal["applied", "already_applied", "rejected"]
    if acceptance.accepted and acceptance.already_applied:
        disposition = "already_applied"
        reason_code = ALREADY_APPLIED_CODE
    elif acceptance.accepted:
        disposition = "applied"
        reason_code = "WRITING_CALLBACK_APPLIED"
    else:
        disposition = "rejected"
        reason_code = acceptance.rejection_code or STATE_NOOP_CODE
    return CallbackReceipt(
        protocolVersion="1.0",
        disposition=disposition,
        reasonCode=reason_code,
        recoverable=False,
        taskPhase=acceptance.task_phase or "unknown",
        commandStatus=acceptance.command_status,
        outboxEventId=acceptance.outbox_event_id,
    )


def _event_sequence_gap_error(exc: EventSequenceGap) -> ApiError:
    return ApiError(
        status_code=409,
        code="AGENT_EVENT_SEQUENCE_GAP",
        message="智能体事件序号不连续，需要状态对账",
        details={
            "expectedSequence": exc.expected_sequence,
            "receivedSequence": exc.received_sequence,
            "recoverable": True,
        },
    )


def _checkpoint_event_sequence(checkpoint: dict[str, Any]) -> int:
    value = checkpoint.get("eventSequence")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ApiError(
            status_code=409,
            code="WRITING_CHECKPOINT_SEQUENCE_INVALID",
            message="检查点缺少有效事件序号",
        )
    return value


def _persisted_event_sequence(task: WritingTask) -> int:
    if task.graphStateJson is None:
        return 0
    try:
        snapshot = json.loads(task.graphStateJson)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApiError(
            status_code=409,
            code="WRITING_SNAPSHOT_INVALID",
            message="持久写作快照不是有效 JSON",
        ) from exc
    if not isinstance(snapshot, dict):
        raise ApiError(
            status_code=409,
            code="WRITING_SNAPSHOT_INVALID",
            message="持久写作快照格式无效",
        )
    value = snapshot.get("eventSequence", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ApiError(
            status_code=409,
            code="WRITING_SNAPSHOT_INVALID",
            message="持久写作快照事件序号无效",
        )
    return cast(int, value)


def _target_acceptance(
    target: _CallbackTarget,
    *,
    accepted: bool,
    persisted_sequence: int,
    already_applied: bool = False,
    rejection_code: str | None = None,
    outbox_event_id: str | None = None,
) -> CallbackAcceptance:
    return CallbackAcceptance(
        accepted=accepted,
        persisted_sequence=persisted_sequence,
        already_applied=already_applied,
        rejection_code=rejection_code,
        task_phase=target.task.phase,
        command_status=(
            cast(WritingCommandStatus, target.command.status)
            if target.command is not None
            else None
        ),
        outbox_event_id=outbox_event_id,
    )


async def _enqueue_target_boundary(
    session: AsyncSession,
    target: _CallbackTarget,
    boundary: BoundaryEvent | None,
    *,
    durable_baseline: int | None,
) -> OutboxRegistration:
    if boundary is None:
        return OutboxRegistration(outbox_id=None)
    return await enqueue_boundary_event(
        session,
        task_id=target.task.id,
        command_id=target.command.id if target.command is not None else None,
        boundary=boundary,
        durable_baseline=durable_baseline,
    )


async def _lock_callback_target(
    session: AsyncSession,
    task_id: str,
    job_id: str,
) -> _CallbackTarget | None:
    task = await session.get(WritingTask, task_id, with_for_update=True)
    if task is None:
        return None
    command = await session.get(WritingRunCommand, job_id, with_for_update=True)
    active_command_id = await session.scalar(
        select(WritingRunCommand.id)
        .where(
            WritingRunCommand.taskId == task_id,
            WritingRunCommand.status.in_(ACTIVE_CALLBACK_COMMAND_STATUSES),
        )
        .with_for_update()
    )
    if active_command_id is not None and active_command_id != job_id:
        return None
    latest_command_id = active_command_id
    if latest_command_id is None:
        latest_command_id = await session.scalar(
            select(WritingRunCommand.id)
            .where(WritingRunCommand.taskId == task_id)
            .order_by(
                WritingRunCommand.createdAt.desc(),
                WritingRunCommand.id.desc(),
            )
            .limit(1)
            .with_for_update()
        )
    if command is not None:
        if command.taskId != task_id or latest_command_id != job_id:
            return None
        return _CallbackTarget(
            task=task,
            command=command,
            already_applied=command.status not in ACTIVE_CALLBACK_COMMAND_STATUSES,
        )
    if latest_command_id is not None:
        return None
    if job_id != _legacy_callback_job_id(task):
        return None
    return _CallbackTarget(
        task=task,
        command=None,
        already_applied=task.phase in TERMINAL_TASK_PHASES,
    )


def _legacy_callback_job_id(task: WritingTask) -> str:
    if task.graphStateJson is None:
        return build_writing_job_id(
            task.id,
            resume=False,
            graph_state_json=None,
        )
    try:
        snapshot = json.loads(task.graphStateJson)
    except (json.JSONDecodeError, TypeError):
        snapshot = None
    if isinstance(snapshot, dict):
        callback_job_id = snapshot.get(CALLBACK_JOB_ID_FIELD)
        if isinstance(callback_job_id, str) and callback_job_id.strip():
            return callback_job_id
    return build_writing_job_id(
        task.id,
        resume=True,
        graph_state_json=task.graphStateJson,
    )


def _log_callback_outcome(
    code: str,
    task_id: str,
    job_id: str,
    event_id: str,
) -> None:
    logger.warning(
        "%s task_id=%s job_id=%s event_id=%s",
        code,
        task_id,
        job_id,
        event_id,
    )


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


def _transition_callback_command(
    command: WritingRunCommand | None,
    target: str,
    *,
    result: dict[str, Any] | None = None,
    callback_result: dict[str, Any] | None = None,
) -> None:
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
    if callback_result is not None:
        persisted_result = _terminal_result_payload(command, result)
        persisted_result[TERMINAL_CALLBACK_RESULT_FIELD] = callback_result
        command.resultJson = json.dumps(
            persisted_result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    elif command.resultJson is None and result is not None:
        command.resultJson = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _command_result_contains(
    command: WritingRunCommand | None,
    incoming: dict[str, Any],
) -> bool:
    if command is None or command.resultJson is None:
        return False
    try:
        stored = json.loads(command.resultJson)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(stored, dict):
        return False
    callback_result = stored.get(TERMINAL_CALLBACK_RESULT_FIELD)
    if isinstance(callback_result, dict):
        return callback_result == incoming
    comparable = dict(stored)
    if _is_short_medium_command(command):
        try:
            payload = json.loads(command.payloadJson)
        except (json.JSONDecodeError, TypeError):
            return False
        if not isinstance(payload, dict):
            return False
        enrichment_key = (
            "checkReport"
            if payload.get("operation") == "full_check"
            else "candidateVersionId"
        )
        comparable.pop(enrichment_key, None)
    return comparable == incoming


def _completion_result_compatible(
    task: WritingTask,
    command: WritingRunCommand | None,
    incoming: dict[str, Any],
) -> bool:
    if command is not None and (
        command.kind != "artifact_decision"
        or _has_terminal_callback_result(command)
    ):
        return _command_result_contains(command, incoming)
    return _task_completion_result_compatible(task, incoming)


def _failure_result_compatible(
    task: WritingTask,
    command: WritingRunCommand | None,
    code: str,
) -> bool:
    if command is not None and (
        command.kind != "artifact_decision"
        or _has_terminal_callback_result(command)
    ):
        return _command_result_contains(command, {"code": code})
    return _task_failure_result_compatible(task, code)


def _task_completion_result_compatible(
    task: WritingTask,
    incoming: dict[str, Any],
) -> bool:
    supported_fields = {"finalContent", "finalResponse", "agentOutputs"}
    if set(incoming) - supported_fields:
        return False
    incoming_final_content = incoming.get("finalContent")
    incoming_final_response = incoming.get("finalResponse")
    if (
        isinstance(incoming_final_content, str)
        and isinstance(incoming_final_response, str)
        and incoming_final_content != incoming_final_response
    ):
        return False
    final_content = incoming.get("finalContent", incoming.get("finalResponse"))
    if task.finalContent is not None and (
        not isinstance(final_content, str) or task.finalContent != final_content
    ):
        return False
    if task.finalContent is None and isinstance(final_content, str):
        return False
    agent_outputs = incoming.get("agentOutputs")
    if task.agentOutputs is None:
        return agent_outputs is None
    if agent_outputs is None:
        return False
    try:
        stored_outputs: object = json.loads(task.agentOutputs)
        return bool(stored_outputs == agent_outputs)
    except (json.JSONDecodeError, TypeError):
        return False


def _has_terminal_callback_result(command: WritingRunCommand) -> bool:
    if command.resultJson is None:
        return False
    try:
        result = json.loads(command.resultJson)
    except (json.JSONDecodeError, TypeError):
        return False
    return (
        isinstance(result, dict)
        and isinstance(result.get(TERMINAL_CALLBACK_RESULT_FIELD), dict)
    )


def _terminal_result_payload(
    command: WritingRunCommand,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    if command.kind != "artifact_decision":
        return dict(result or {})
    if command.resultJson is None:
        return dict(result or {})
    try:
        existing = json.loads(command.resultJson)
    except (json.JSONDecodeError, TypeError):
        return dict(result or {})
    return dict(existing) if isinstance(existing, dict) else dict(result or {})


def _callback_result_digest(result: dict[str, Any]) -> str:
    canonical = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _task_failure_result_compatible(task: WritingTask, code: str) -> bool:
    if task.graphStateJson is None:
        return True
    try:
        snapshot = json.loads(task.graphStateJson)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(snapshot, dict):
        return False
    error_message = snapshot.get("errorMessage")
    if not isinstance(error_message, str):
        return True
    if not error_message.startswith("智能体运行失败："):
        return True
    return error_message.endswith(code)


def _is_short_medium_command(command: WritingRunCommand) -> bool:
    try:
        payload = json.loads(command.payloadJson)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("workflow") == "short_medium"


def _checkpoint_phase_for_locked_command(
    command: WritingRunCommand | None,
    task: WritingTask,
    serialized: str,
    *,
    fallback_phase: str,
) -> str:
    try:
        checkpoint = json.loads(serialized)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ApiError(
            status_code=409,
            code="WRITING_SNAPSHOT_INVALID",
            message="持久写作快照不是有效 JSON",
        ) from exc
    if not isinstance(checkpoint, dict):
        raise ApiError(
            status_code=409,
            code="WRITING_SNAPSHOT_INVALID",
            message="持久写作快照格式无效",
        )
    command_payload: dict[str, Any] = {}
    if command is not None:
        try:
            value = json.loads(command.payloadJson)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ApiError(
                status_code=409,
                code="WRITING_COMMAND_PAYLOAD_INVALID",
                message="写作命令载荷无效",
            ) from exc
        if isinstance(value, dict):
            command_payload = value
    command_is_short = command_payload.get("workflow") == "short_medium"
    checkpoint_is_short = checkpoint.get("workflow") == "short_medium"
    if command_is_short != checkpoint_is_short:
        raise ApiError(
            status_code=409,
            code="WRITING_CHECKPOINT_COMMAND_MISMATCH",
            message="检查点 workflow 与锁定命令不一致",
        )
    if command_is_short:
        if checkpoint.get("operation") != command_payload.get("operation"):
            raise ApiError(
                status_code=409,
                code="WRITING_CHECKPOINT_COMMAND_MISMATCH",
                message="检查点 operation 与锁定命令不一致",
            )
        if checkpoint.get("phase") not in {"generating", "completed"}:
            raise ApiError(
                status_code=409,
                code="WRITING_SNAPSHOT_INVALID",
                message="中短篇检查点阶段无效",
            )
        return "active"
    try:
        deserialize_graph_snapshot(
            serialized,
            expected_task_id=task.id,
            expected_novel_id=task.novelId,
            expected_chapter_id=task.chapterId,
        )
    except InvalidGraphSnapshotError as exc:
        raise ApiError(
            status_code=409,
            code="WRITING_SNAPSHOT_INVALID",
            message=str(exc),
        ) from exc
    if fallback_phase in TERMINAL_TASK_PHASES:
        return "active"
    return fallback_phase


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

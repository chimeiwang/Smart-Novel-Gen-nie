from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol, cast

from inkforge_contracts.events import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from inkforge_contracts.jobs import AgentJobStatus, WritingJobPayload
from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Novel,
    ReviewArtifact,
    WritingBible,
    WritingMessage,
    WritingRunCommand,
    WritingSession,
    WritingTask,
)
from ..errors import ApiError
from .job_identity import build_writing_job_id
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
ACTIVE_CALLBACK_COMMAND_STATUSES = frozenset({"pending", "submitted", "processing"})
CALLBACK_JOB_ID_FIELD = "callbackJobId"
JOB_MISMATCH_CODE = "WRITING_JOB_MISMATCH"
SEQUENCE_STALE_CODE = "WRITING_CALLBACK_SEQUENCE_STALE"
ALREADY_APPLIED_CODE = "WRITING_CALLBACK_ALREADY_APPLIED"
STATE_NOOP_CODE = "WRITING_CALLBACK_STATE_NOOP"
CHECKPOINT_CONFLICT_CODE = "WRITING_CHECKPOINT_CONFLICT"
logger = logging.getLogger(__name__)


async def _reconciliation_workflow_identity(
    session: AsyncSession,
    task: WritingTask,
) -> dict[str, Any]:
    bible = await session.scalar(
        select(WritingBible).where(WritingBible.novelId == task.novelId)
    )
    serialized = await session.scalar(
        select(WritingRunCommand.payloadJson)
        .where(WritingRunCommand.taskId == task.id)
        .order_by(WritingRunCommand.createdAt.desc(), WritingRunCommand.id.desc())
        .limit(1)
    )
    persisted_profile = bible.storyLengthProfile if bible is not None else "long_serial"
    legacy_long_identity = {
        "workflowKind": "long_serial",
        "operation": None,
        "targetTotalWordCount": (
            bible.targetTotalWordCount if bible is not None else None
        ),
        "source": None,
    }
    if serialized is None:
        if persisted_profile == "short_medium":
            raise _reconciliation_identity_missing()
        return legacy_long_identity
    try:
        raw_payload = json.loads(serialized)
    except (json.JSONDecodeError, TypeError):
        raise _reconciliation_identity_invalid() from None
    if not isinstance(raw_payload, dict):
        raise _reconciliation_identity_invalid()
    if "workflowKind" not in raw_payload:
        if persisted_profile == "short_medium":
            raise _reconciliation_identity_missing()
        return legacy_long_identity
    try:
        latest = WritingJobPayload.model_validate(raw_payload)
    except ValueError:
        raise _reconciliation_identity_invalid() from None
    if latest.chapterId != task.chapterId or latest.workflowKind != persisted_profile:
        raise _reconciliation_identity_mismatch()
    if latest.workflowKind == "short_medium":
        target = bible.targetTotalWordCount if bible is not None else None
        if (
            target is None
            or latest.targetTotalWordCount != target
            or task.targetWordCount != target
        ):
            raise _reconciliation_identity_mismatch()
    return {
        "workflowKind": latest.workflowKind,
        "operation": latest.operation,
        "targetTotalWordCount": latest.targetTotalWordCount,
        "source": (
            latest.source.model_dump(mode="json")
            if latest.source is not None
            else None
        ),
    }


def _reconciliation_identity_missing() -> ApiError:
    return ApiError(
        status_code=409,
        code="WRITING_RECONCILIATION_IDENTITY_MISSING",
        message="中短篇遗留任务缺少可验证的持久写作身份，不能自动对账",
    )


def _reconciliation_identity_invalid() -> ApiError:
    return ApiError(
        status_code=409,
        code="WRITING_RECONCILIATION_IDENTITY_INVALID",
        message="最近写作命令载荷无效，不能自动对账",
    )


def _reconciliation_identity_mismatch() -> ApiError:
    return ApiError(
        status_code=409,
        code="WRITING_RECONCILIATION_IDENTITY_MISMATCH",
        message="最近写作命令与作品篇幅身份不一致，不能自动对账",
    )


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
    async def validate_agent_event(
        self,
        task_id: str,
        *,
        source_event_id: str,
        sequence: int,
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


@dataclass(frozen=True, slots=True)
class _CallbackTarget:
    task: WritingTask
    command: WritingRunCommand | None
    already_applied: bool


@dataclass(frozen=True, slots=True)
class _CallbackPreparation:
    should_publish: bool
    durable_baseline: int


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
    ) -> CallbackAcceptance: ...

    async def complete_with_message_and_command(
        self,
        task_id: str,
        job_id: str,
        result: dict[str, Any],
        visible_response: str,
        sequence: int,
    ) -> CallbackAcceptance: ...

    async def fail_with_command(
        self, task_id: str, job_id: str, code: str, sequence: int
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
                identity = await _reconciliation_workflow_identity(session, task)
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
                payload = WritingJobPayload.model_validate(
                    {
                        "version": 1,
                        "resume": resume,
                        "chapterId": task.chapterId,
                        "writingSessionId": task.writingSessionId,
                        "resumeInput": None,
                        **identity,
                        "force": True,
                    }
                ).model_dump(mode="json")
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
                return CallbackAcceptance(
                    True,
                    _persisted_event_sequence(target.task),
                    already_applied=target.already_applied,
                )

    async def save_checkpoint(
        self,
        task_id: str,
        job_id: str,
        serialized: str,
        phase: str,
        sequence: int,
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
                    return CallbackAcceptance(
                        identical,
                        persisted_sequence,
                        already_applied=identical,
                        rejection_code=None if identical else CHECKPOINT_CONFLICT_CODE,
                    )
                if target.already_applied or target.task.phase in TERMINAL_TASK_PHASES:
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=ALREADY_APPLIED_CODE,
                    )
                target.task.graphStateJson = serialized
                target.task.phase = phase
                target.task.updatedAt = utc_now()
                _transition_callback_command(
                    target.command,
                    "succeeded" if phase == "awaiting_user_review" else "processing",
                )
                return CallbackAcceptance(True, persisted_sequence)

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
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=SEQUENCE_STALE_CODE,
                    )
                if target.already_applied:
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=ALREADY_APPLIED_CODE,
                    )
                _transition_callback_command(target.command, "processing")
                return CallbackAcceptance(True, persisted_sequence)

    async def complete_with_message_and_command(
        self,
        task_id: str,
        job_id: str,
        result: dict[str, Any],
        visible_response: str,
        sequence: int,
    ) -> CallbackAcceptance:
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
                    if visible_response:
                        await _persist_workflow_message(
                            session,
                            task,
                            role="agent",
                            content=visible_response,
                            event_type="done",
                        )
                    for name, value in values.items():
                        if name != "phase":
                            setattr(task, name, value)
                    return CallbackAcceptance(True, persisted_sequence)
                if target.already_applied:
                    accepted = (
                        target.command is not None
                        and target.command.status == "succeeded"
                    )
                    return CallbackAcceptance(
                        accepted,
                        persisted_sequence,
                        already_applied=accepted,
                        rejection_code=None if accepted else STATE_NOOP_CODE,
                    )
                if task.phase == "error":
                    return CallbackAcceptance(
                        False,
                        persisted_sequence,
                        rejection_code=STATE_NOOP_CODE,
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
                _transition_callback_command(target.command, "succeeded", result=result)
                return CallbackAcceptance(True, persisted_sequence)

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
        self, task_id: str, job_id: str, code: str, sequence: int
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
                    return CallbackAcceptance(
                        accepted,
                        persisted_sequence,
                        already_applied=accepted,
                        rejection_code=None if accepted else STATE_NOOP_CODE,
                    )
                if target.already_applied:
                    accepted = (
                        target.command is not None and target.command.status == "failed"
                    )
                    return CallbackAcceptance(
                        accepted,
                        persisted_sequence,
                        already_applied=accepted,
                        rejection_code=None if accepted else STATE_NOOP_CODE,
                    )
                recovered = await _restore_short_story_artifact_after_failure(
                    session,
                    target,
                    sequence,
                )
                if not recovered:
                    mark_task_failed_state(target.task, code)
                _transition_callback_command(
                    target.command,
                    "failed",
                    result={"code": code},
                )
                return CallbackAcceptance(True, persisted_sequence)


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
        preparation = await self._prepare_callback(
            task_id=body.taskId,
            job_id=body.jobId,
            event_id=body.eventId,
            sequence=body.sequence,
            ignore_when_already_applied=True,
        )
        if preparation is None:
            return
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
            return
        if preparation.should_publish:
            await self._append(
                body.taskId,
                body.eventId,
                body.sequence,
                body.event,
                body.data,
                durable_baseline=preparation.durable_baseline,
            )

    async def save_checkpoint(
        self, body: CheckpointCallback, *, user_id: str, novel_id: str
    ) -> None:
        checkpoint = dict(body.checkpoint)
        checkpoint[CALLBACK_JOB_ID_FIELD] = body.jobId
        serialized = json.dumps(checkpoint, ensure_ascii=False)
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
        persisted_phase = phase if isinstance(phase, str) else "active"
        preparation = await self._prepare_callback(
            task_id=body.taskId,
            job_id=body.jobId,
            event_id=body.eventId,
            sequence=body.sequence,
            allow_persisted_equal=True,
        )
        if preparation is None:
            return
        acceptance = await self._repository.save_checkpoint(
            body.taskId,
            body.jobId,
            serialized,
            persisted_phase,
            body.sequence,
        )
        if not acceptance.accepted:
            _log_callback_outcome(
                acceptance.rejection_code or STATE_NOOP_CODE,
                body.taskId,
                body.jobId,
                body.eventId,
            )
            return
        if preparation.should_publish:
            await self._append(
                body.taskId,
                body.eventId,
                body.sequence,
                "checkpoint",
                {"phase": checkpoint.get("phase")},
                durable_baseline=preparation.durable_baseline,
            )

    async def complete(self, body: RunCompletionCallback) -> None:
        final_response = body.result.get("finalResponse")
        visible_response = final_response.strip() if isinstance(final_response, str) else ""
        event_data: dict[str, Any] = {"taskId": body.taskId}
        if visible_response:
            event_data["finalContent"] = visible_response
        preparation = await self._prepare_callback(
            task_id=body.taskId,
            job_id=body.jobId,
            event_id=body.eventId,
            sequence=body.sequence,
        )
        if preparation is None:
            return
        acceptance = await self._repository.complete_with_message_and_command(
            body.taskId,
            body.jobId,
            body.result,
            visible_response,
            body.sequence,
        )
        if not acceptance.accepted:
            _log_callback_outcome(
                acceptance.rejection_code or STATE_NOOP_CODE,
                body.taskId,
                body.jobId,
                body.eventId,
            )
            return
        if preparation.should_publish:
            await self._append(
                body.taskId,
                body.eventId,
                body.sequence,
                "completed",
                event_data,
                durable_baseline=preparation.durable_baseline,
            )

    async def fail(self, body: RunFailureCallback) -> None:
        preparation = await self._prepare_callback(
            task_id=body.taskId,
            job_id=body.jobId,
            event_id=body.eventId,
            sequence=body.sequence,
        )
        if preparation is None:
            return
        acceptance = await self._repository.fail_with_command(
            body.taskId, body.jobId, body.code, body.sequence
        )
        if not acceptance.accepted:
            _log_callback_outcome(
                acceptance.rejection_code or STATE_NOOP_CODE,
                body.taskId,
                body.jobId,
                body.eventId,
            )
            return
        if preparation.should_publish:
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
                durable_baseline=preparation.durable_baseline,
            )

    async def _prepare_callback(
        self,
        *,
        task_id: str,
        job_id: str,
        event_id: str,
        sequence: int,
        allow_persisted_equal: bool = False,
        ignore_when_already_applied: bool = False,
    ) -> _CallbackPreparation | None:
        authorization = await self._repository.authorize_callback(task_id, job_id)
        if not authorization.accepted:
            _log_callback_outcome(
                authorization.rejection_code or JOB_MISMATCH_CODE,
                task_id,
                job_id,
                event_id,
            )
            return None
        if ignore_when_already_applied and authorization.already_applied:
            _log_callback_outcome(
                ALREADY_APPLIED_CODE,
                task_id,
                job_id,
                event_id,
            )
            return None
        if sequence < authorization.persisted_sequence:
            _log_callback_outcome(
                SEQUENCE_STALE_CODE,
                task_id,
                job_id,
                event_id,
            )
            return None
        if sequence == authorization.persisted_sequence:
            if not allow_persisted_equal:
                _log_callback_outcome(
                    SEQUENCE_STALE_CODE,
                    task_id,
                    job_id,
                    event_id,
                )
                return None
            durable_baseline = max(0, sequence - 1)
        else:
            durable_baseline = authorization.persisted_sequence
        should_publish = await self._validate_event_sequence(
            task_id,
            event_id,
            sequence,
            durable_baseline=durable_baseline,
        )
        return _CallbackPreparation(
            should_publish=should_publish,
            durable_baseline=durable_baseline,
        )

    async def _validate_event_sequence(
        self,
        task_id: str,
        event_id: str,
        sequence: int,
        *,
        durable_baseline: int,
    ) -> bool:
        try:
            return await self._events.validate_agent_event(
                task_id,
                source_event_id=event_id,
                sequence=sequence,
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


async def _restore_short_story_artifact_after_failure(
    session: AsyncSession,
    target: _CallbackTarget,
    sequence: int,
) -> bool:
    command = target.command
    if command is None:
        return False
    try:
        command_payload = WritingJobPayload.model_validate_json(command.payloadJson)
    except ValueError:
        return False
    if command_payload.workflowKind != "short_medium":
        return False
    operation = command_payload.operation
    if operation == "develop_short_outline":
        expected_kind = "outline_draft"
    elif operation == "write_short_story":
        expected_kind = "chapter_draft"
    else:
        return False
    base_conditions = [
        ReviewArtifact.taskId == target.task.id,
        ReviewArtifact.kind == expected_kind,
        ReviewArtifact.status.in_(("draft", "under_review", "awaiting_user")),
    ]
    exact_artifact_id = _failure_recovery_artifact_id(target.task, command)
    if command.kind == "artifact_decision" and exact_artifact_id is None:
        return False
    if exact_artifact_id is not None:
        artifact = await session.scalar(
            select(ReviewArtifact)
            .where(
                *base_conditions,
                ReviewArtifact.id == exact_artifact_id,
            )
            .with_for_update()
        )
    else:
        candidates = list(
            await session.scalars(
                select(ReviewArtifact)
                .where(*base_conditions)
                .with_for_update()
            )
        )
        artifact = candidates[0] if len(candidates) == 1 else None
    if artifact is None:
        return False
    if not _is_typed_short_story_artifact(artifact, expected_kind):
        return False
    serialized = await _recoverable_short_story_snapshot(
        session,
        target.task,
        command,
        command_payload,
        artifact.id,
        sequence,
    )
    if serialized is None:
        return False
    artifact.status = "awaiting_user"
    target.task.graphStateJson = serialized
    target.task.phase = "awaiting_user_review"
    target.task.updatedAt = utc_now()
    return True


def _failure_recovery_artifact_id(
    task: WritingTask,
    command: WritingRunCommand,
) -> str | None:
    if command.artifactId is not None:
        return command.artifactId
    if not task.graphStateJson:
        return None
    try:
        snapshot = json.loads(task.graphStateJson)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(snapshot, dict):
        return None
    artifact_review = snapshot.get("artifactReview")
    if isinstance(artifact_review, dict):
        value = artifact_review.get("activeArtifactId")
        if isinstance(value, str) and value:
            return value
    value = snapshot.get("activeArtifactId")
    return value if isinstance(value, str) and value else None


def _is_typed_short_story_artifact(
    artifact: ReviewArtifact,
    expected_kind: str,
) -> bool:
    try:
        artifact_payload = json.loads(artifact.payloadJson)
    except (json.JSONDecodeError, TypeError):
        return False
    if (
        not isinstance(artifact_payload, dict)
        or artifact_payload.get("storyLengthProfile") != "short_medium"
        or artifact_payload.get("kind") != expected_kind
    ):
        return False
    return True


async def _recoverable_short_story_snapshot(
    session: AsyncSession,
    task: WritingTask,
    command: WritingRunCommand,
    command_payload: WritingJobPayload,
    artifact_id: str,
    sequence: int,
) -> str | None:
    owner_id = await session.scalar(
        select(Novel.userId).where(Novel.id == task.novelId)
    )
    if not isinstance(owner_id, str) or not owner_id:
        return None
    snapshot = _load_snapshot_object(task.graphStateJson)
    history = _snapshot_conversation_history(snapshot, task.conversationHistory)
    operation = command_payload.operation
    if operation not in {"develop_short_outline", "write_short_story"}:
        return None
    persisted_operation = snapshot.get("currentOperation")
    persisted_goal = (
        persisted_operation.get("userGoal")
        if isinstance(persisted_operation, dict)
        else None
    )
    current_operation = _short_story_recovery_operation(
        operation,
        (
            persisted_goal
            if isinstance(persisted_goal, str) and persisted_goal.strip()
            else _latest_user_message(history)
        ),
    )
    snapshot.update(
        {
            "taskId": task.id,
            "userId": owner_id,
            "novelId": task.novelId,
            "chapterId": task.chapterId,
            "targetWordCount": task.targetWordCount,
            "conversationHistory": history,
            "currentOperation": current_operation,
            "operationStage": "等待用户决策",
            "operationStep": "await_user_decision",
            "workflowKind": "short_medium",
            "explicitOperation": operation,
            "commandId": command.id,
            "targetTotalWordCount": command_payload.targetTotalWordCount,
            "commandSource": (
                command_payload.source.model_dump(mode="json")
                if command_payload.source is not None
                else None
            ),
            "phase": "awaiting_user_review",
            "activeArtifactId": artifact_id,
            "artifactStatus": "awaiting_user",
            "pendingUserResponse": True,
            "artifactMode": "review_loop",
            "eventSequence": sequence,
        }
    )
    snapshot.pop("errorMessage", None)
    artifact_review = snapshot.get("artifactReview")
    review_state = dict(artifact_review) if isinstance(artifact_review, dict) else {}
    review_state.update(
        {
            "activeArtifactId": artifact_id,
            "status": "awaiting_user",
        }
    )
    snapshot["artifactReview"] = review_state
    serialized = json.dumps(snapshot, ensure_ascii=False)
    try:
        deserialize_graph_snapshot(
            serialized,
            expected_task_id=task.id,
            expected_user_id=owner_id,
            expected_novel_id=task.novelId,
            expected_chapter_id=task.chapterId,
        )
    except InvalidGraphSnapshotError:
        return None
    return serialized


def _load_snapshot_object(serialized: str | None) -> dict[str, Any]:
    if not serialized:
        return {}
    try:
        value = json.loads(serialized)
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _snapshot_conversation_history(
    snapshot: dict[str, Any],
    serialized_history: str | None,
) -> list[dict[str, Any]]:
    value = snapshot.get("conversationHistory")
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if serialized_history:
        try:
            persisted = json.loads(serialized_history)
        except (json.JSONDecodeError, TypeError):
            persisted = None
        if isinstance(persisted, list):
            return [dict(item) for item in persisted if isinstance(item, dict)]
    return []


def _latest_user_message(history: list[dict[str, Any]]) -> str:
    for item in reversed(history):
        content = item.get("content")
        if item.get("role") == "user" and isinstance(content, str) and content.strip():
            return content
    return "继续处理中短篇草案"


def _short_story_recovery_operation(
    operation: str,
    user_goal: str,
) -> dict[str, Any]:
    if operation == "develop_short_outline":
        return {
            "kind": operation,
            "targetType": "outline",
            "userGoal": user_goal,
            "primaryAgent": "剧情",
            "reviewers": [],
            "outputKind": "outline_proposal",
            "requiresArtifact": True,
            "requiresUserApproval": True,
            "confidence": 1,
            "reasoning": "根据 Core 持久化的中短篇 Operation 恢复用户决策。",
        }
    return {
        "kind": operation,
        "targetType": "chapter",
        "userGoal": user_goal,
        "primaryAgent": "写作",
        "reviewers": ["编辑", "校验"],
        "outputKind": "chapter_text",
        "requiresArtifact": True,
        "requiresUserApproval": True,
        "confidence": 1,
        "reasoning": "根据 Core 持久化的中短篇 Operation 恢复用户决策。",
    }


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

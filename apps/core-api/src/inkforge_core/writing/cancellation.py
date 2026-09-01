from __future__ import annotations

import json
import logging
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import generate_id, utc_now
from ..db.models import Novel, ReviewArtifact, WritingRunCommand, WritingTask
from ..errors import ApiError
from .commands import ARTIFACT_DECISION_ACCEPTED_RESPONSE_FIELD
from .idempotency import (
    JsonValue,
    acquire_idempotency_lock,
    enveloped_command_idempotency_key,
    logical_command_kind,
    request_fingerprint,
    resolve_idempotency,
)
from .run_queries import project_run_status
from .schemas import (
    CancelWritingRunRequest,
    CancelWritingRunResponse,
    WritingCommandStatus,
)
from .transaction_locks import WritingLockRequest, lock_writing_rows

logger = logging.getLogger(__name__)


class ImmediateCommandDispatcher(Protocol):
    async def run_once(self) -> int: ...


class WritingRunCancellationService:
    def __init__(
        self,
        repository: WritingRunCancellationRepository,
        dispatcher: ImmediateCommandDispatcher | None,
    ) -> None:
        self._repository = repository
        self._dispatcher = dispatcher

    async def cancel(
        self,
        user_id: str,
        task_id: str,
        request: CancelWritingRunRequest,
    ) -> CancelWritingRunResponse:
        response = await self._repository.create_cancel(user_id, task_id, request)
        if response.commandStatus == "pending" and self._dispatcher is not None:
            try:
                await self._dispatcher.run_once()
            except Exception:
                logger.warning("写作取消命令即时投递失败，已交由后台重试")
        return response


class WritingRunCancellationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_cancel(
        self,
        user_id: str,
        task_id: str,
        request: CancelWritingRunRequest,
    ) -> CancelWritingRunResponse:
        fingerprint = request_fingerprint(
            command_kind="cancel",
            resource_identity={"taskId": task_id},
            body={},
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await acquire_idempotency_lock(
                        session,
                        user_id=user_id,
                        client_request_id=request.clientRequestId,
                    )
                    replay = await self._resolve_replay(
                        session,
                        user_id=user_id,
                        task_id=task_id,
                        client_request_id=request.clientRequestId,
                        fingerprint=fingerprint,
                    )
                    if replay is not None:
                        return replay

                    novel_id, chapter_id = await self._task_identity(
                        session, user_id, task_id
                    )
                    await lock_writing_rows(
                        session,
                        user_id=user_id,
                        request=WritingLockRequest(
                            novel_id=novel_id,
                            chapter_ids=(chapter_id,) if chapter_id is not None else (),
                            task_id=task_id,
                        ),
                    )
                    artifact_id = await self._awaiting_artifact_id(session, task_id)
                    current_command_id = await self._current_command_id(session, task_id)
                    locked = await lock_writing_rows(
                        session,
                        user_id=user_id,
                        request=WritingLockRequest(
                            novel_id=novel_id,
                            chapter_ids=(chapter_id,) if chapter_id is not None else (),
                            task_id=task_id,
                            artifact_id=artifact_id,
                            command_id=current_command_id,
                        ),
                    )
                    task = locked.task
                    if task is None:
                        raise RuntimeError("统一写作锁未返回取消任务")
                    replay = await self._resolve_replay(
                        session,
                        user_id=user_id,
                        task_id=task_id,
                        client_request_id=request.clientRequestId,
                        fingerprint=fingerprint,
                    )
                    if replay is not None:
                        return replay
                    if locked.artifact is not None and locked.artifact.status == "awaiting_user":
                        raise ApiError(
                            status_code=409,
                            code="ARTIFACT_DECISION_REQUIRED",
                            message="存在等待用户决策的审核产物，必须先提交审核决策",
                        )

                    commands = list(
                        (
                            await session.scalars(
                                select(WritingRunCommand)
                                .where(WritingRunCommand.taskId == task.id)
                                .order_by(
                                    WritingRunCommand.createdAt.desc(),
                                    WritingRunCommand.id.desc(),
                                )
                            )
                        ).all()
                    )
                    artifacts = list(
                        (
                            await session.scalars(
                                select(ReviewArtifact)
                                .where(ReviewArtifact.taskId == task.id)
                                .order_by(
                                    ReviewArtifact.createdAt.desc(),
                                    ReviewArtifact.id.desc(),
                                )
                            )
                        ).all()
                    )
                    prior_outcome = _prior_outcome(task, commands, artifacts)
                    current = locked.command
                    terminal = task.phase in {"completed", "error"}
                    cancel_id = generate_id()
                    cancelled_command_id: str | None = None
                    cancelled_job_id: str | None = None
                    if not terminal and current is not None:
                        cancelled_command_id = current.id
                        cancelled_job_id = current.id
                        await _retire_active_command_for_cancel(
                            session,
                            current,
                            cancel_command_id=cancel_id,
                        )
                    else:
                        terminal = True

                    payload = build_cancel_command_payload(
                        client_request_id=request.clientRequestId,
                        task_id=task.id,
                        cancelled_command_id=cancelled_command_id,
                        cancelled_job_id=cancelled_job_id,
                    )
                    command = WritingRunCommand(
                        id=cancel_id,
                        taskId=task.id,
                        kind="resume",
                        payloadJson=_dump_json(payload),
                        resultJson=(
                            _dump_json(
                                {
                                    "effective": False,
                                    "priorOutcome": prior_outcome,
                                }
                            )
                            if terminal
                            else None
                        ),
                        idempotencyKey=enveloped_command_idempotency_key(
                            user_id, request.clientRequestId
                        ),
                        status="succeeded" if terminal else "pending",
                        attemptCount=0,
                        nextAttemptAt=utc_now(),
                        completedAt=utc_now() if terminal else None,
                    )
                    session.add(command)
                    await session.flush()
                    return _response(
                        command,
                        effective=not terminal,
                        already_terminal=terminal,
                        cancelled_command_id=cancelled_command_id,
                        cancelled_job_id=cancelled_job_id,
                    )
        except IntegrityError as exc:
            async with self._session_factory() as session:
                replay = await self._resolve_replay(
                    session,
                    user_id=user_id,
                    task_id=task_id,
                    client_request_id=request.clientRequestId,
                    fingerprint=fingerprint,
                )
            if replay is not None:
                return replay
            raise ApiError(
                status_code=409,
                code="WRITING_COMMAND_CONFLICT",
                message="写作取消请求发生并发冲突",
            ) from exc

    async def _resolve_replay(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        task_id: str,
        client_request_id: str,
        fingerprint: str,
    ) -> CancelWritingRunResponse | None:
        resolution = await resolve_idempotency(
            session,
            user_id=user_id,
            client_request_id=client_request_id,
            request_fingerprint=fingerprint,
        )
        if resolution is None:
            return None
        if resolution.record_kind != "writing_command":
            raise _idempotency_reused(client_request_id)
        row = (
            await session.execute(
                select(WritingRunCommand, WritingTask, Novel.userId)
                .join(WritingTask, WritingTask.id == WritingRunCommand.taskId)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(WritingRunCommand.id == resolution.record_id)
            )
        ).one_or_none()
        if row is None:
            raise _idempotency_reused(client_request_id)
        command, task, owner_id = cast(tuple[WritingRunCommand, WritingTask, str], row)
        if (
            owner_id != user_id
            or task.id != task_id
            or logical_command_kind(command.kind, command.payloadJson) != "cancel"
        ):
            raise _idempotency_reused(client_request_id)
        payload = _json_object(command.payloadJson)
        job = payload.get("job")
        if (
            set(payload) != {"_inkforgeCommand", "job"}
            or not isinstance(job, dict)
            or set(job) != {"cancelledCommandId", "cancelledJobId"}
        ):
            raise _idempotency_reused(client_request_id)
        result = _json_object(command.resultJson)
        effective = result.get("effective")
        cancelled_command_id = job.get("cancelledCommandId")
        cancelled_job_id = job.get("cancelledJobId")
        if any(
            value is not None and not isinstance(value, str)
            for value in (cancelled_command_id, cancelled_job_id)
        ):
            raise _idempotency_reused(client_request_id)
        return _response(
            command,
            effective=effective is True or command.status != "succeeded",
            already_terminal=effective is False,
            cancelled_command_id=(
                cancelled_command_id if isinstance(cancelled_command_id, str) else None
            ),
            cancelled_job_id=(
                cancelled_job_id if isinstance(cancelled_job_id, str) else None
            ),
        )

    async def _task_identity(
        self, session: AsyncSession, user_id: str, task_id: str
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

    async def _awaiting_artifact_id(
        self, session: AsyncSession, task_id: str
    ) -> str | None:
        return cast(
            str | None,
            await session.scalar(
                select(ReviewArtifact.id)
                .where(
                    ReviewArtifact.taskId == task_id,
                    ReviewArtifact.status == "awaiting_user",
                )
                .order_by(ReviewArtifact.createdAt.desc(), ReviewArtifact.id.desc())
                .limit(1)
            ),
        )

    async def _current_command_id(
        self, session: AsyncSession, task_id: str
    ) -> str | None:
        return cast(
            str | None,
            await session.scalar(
                select(WritingRunCommand.id)
                .where(WritingRunCommand.taskId == task_id)
                .order_by(
                    WritingRunCommand.createdAt.desc(), WritingRunCommand.id.desc()
                )
                .limit(1)
            ),
        )


def build_cancel_command_payload(
    *,
    client_request_id: str,
    task_id: str,
    cancelled_command_id: str | None,
    cancelled_job_id: str | None,
) -> dict[str, object]:
    resource_identity: dict[str, JsonValue] = {"taskId": task_id}
    normalized_body: dict[str, JsonValue] = {}
    return {
        "_inkforgeCommand": {
            "schemaVersion": 1,
            "clientRequestId": client_request_id,
            "commandKind": "cancel",
            "resourceIdentity": resource_identity,
            "normalizedBody": normalized_body,
            "requestFingerprint": request_fingerprint(
                command_kind="cancel",
                resource_identity=resource_identity,
                body=normalized_body,
            ),
        },
        "job": {
            "cancelledCommandId": cancelled_command_id,
            "cancelledJobId": cancelled_job_id,
        },
    }


async def _retire_active_command_for_cancel(
    session: AsyncSession,
    command: WritingRunCommand,
    *,
    cancel_command_id: str,
) -> None:
    now = utc_now()
    command.status = "failed"
    command.completedAt = now
    command.updatedAt = now
    command.lastError = "WRITING_RUN_CANCELLED_BY_USER"
    command.resultJson = _dump_json(
        build_cancelled_command_result(
            command,
            cancel_command_id=cancel_command_id,
            cancelled_job_id=command.id,
        )
    )
    await session.flush()


def build_cancelled_command_result(
    command: WritingRunCommand,
    *,
    cancel_command_id: str,
    cancelled_job_id: str,
) -> dict[str, object]:
    result: dict[str, object] = {
        "code": "WRITING_RUN_CANCELLED_BY_USER",
        "cancelCommandId": cancel_command_id,
        "cancelledJobId": cancelled_job_id,
    }
    if command.kind != "artifact_decision":
        return result
    persisted = _json_object(command.resultJson)
    accepted = persisted.get(ARTIFACT_DECISION_ACCEPTED_RESPONSE_FIELD)
    if not isinstance(accepted, dict):
        accepted = persisted
    if accepted:
        result[ARTIFACT_DECISION_ACCEPTED_RESPONSE_FIELD] = accepted
    return result


def _prior_outcome(
    task: WritingTask,
    commands: list[WritingRunCommand],
    artifacts: list[ReviewArtifact],
) -> dict[str, object]:
    outcome = project_run_status(task, commands=commands, artifacts=artifacts).outcome
    return {
        "state": outcome.state,
        "code": outcome.code,
        "result": outcome.result.model_dump(mode="json"),
        "currentCommand": (
            outcome.currentCommand.model_dump(mode="json")
            if outcome.currentCommand is not None
            else None
        ),
    }


def _response(
    command: WritingRunCommand,
    *,
    effective: bool,
    already_terminal: bool,
    cancelled_command_id: str | None,
    cancelled_job_id: str | None,
) -> CancelWritingRunResponse:
    return CancelWritingRunResponse(
        engineVersion=1,
        runId=command.taskId,
        taskId=command.taskId,
        commandId=command.id,
        commandStatus=cast(WritingCommandStatus, command.status),
        effective=effective,
        alreadyTerminal=already_terminal,
        cancelledCommandId=cancelled_command_id,
        cancelledJobId=cancelled_job_id,
    )


def _json_object(value: str | None) -> dict[str, object]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return cast(dict[str, object], parsed) if isinstance(parsed, dict) else {}


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _idempotency_reused(client_request_id: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="IDEMPOTENCY_KEY_REUSED",
        message="同一幂等标识已绑定其他请求",
        details={"clientRequestId": client_request_id},
    )

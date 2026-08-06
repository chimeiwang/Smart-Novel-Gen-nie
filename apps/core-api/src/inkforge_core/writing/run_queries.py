from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import JsonValue
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import Novel, ReviewArtifact, WritingRunCommand, WritingTask
from ..errors import ApiError
from ..http.cursor import InvalidCursorError, decode_run_cursor, encode_run_cursor
from .idempotency import logical_command_kind
from .outcome import WritingRunOutcomeFacts, project_writing_run_outcome
from .recoverability import resolve_recoverable_checkpoint
from .schemas import (
    WritingCommandStatus,
    WritingRunCheckpointResponse,
    WritingRunListItem,
    WritingRunListResponse,
    WritingRunStatusResponse,
)
from .tasks import TERMINAL_CALLBACK_RESULT_FIELD

_PUBLIC_OPERATIONS = frozenset(
    {
        "generate_outline",
        "generate_manuscript",
        "replace_selection",
        "full_check",
        "plan_chapter",
        "write_chapter",
        "review_chapter",
    }
)
_LONG_ARTIFACT_KINDS = {
    "plan_chapter": "beat_plan",
    "write_chapter": "chapter_draft",
}
_ACTIVE_OUTCOMES = frozenset({"queued", "running", "waiting_user"})
_SCAN_BATCH_SIZE = 200


class WritingRunQueryRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_run(self, user_id: str, task_id: str) -> WritingRunStatusResponse:
        async with self._session_factory() as session:
            owned = (
                await session.execute(
                    select(WritingTask, Novel.userId)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(WritingTask.id == task_id, Novel.userId == user_id)
                )
            ).one_or_none()
            if owned is None:
                raise ApiError(
                    status_code=403,
                    code="WRITING_TASK_FORBIDDEN",
                    message="无权访问该写作任务",
                )
            task = cast(WritingTask, owned[0])
            if hasattr(session, "scalars"):
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
            else:
                current = await session.scalar(
                    select(WritingRunCommand)
                    .where(WritingRunCommand.taskId == task.id)
                    .order_by(
                        WritingRunCommand.createdAt.desc(),
                        WritingRunCommand.id.desc(),
                    )
                    .limit(1)
                )
                commands = [current] if current is not None else []
                payload = _command_job(current)
                result = _full_result(current)
                artifact_id: str | None = None
                if task.phase == "awaiting_user_review":
                    artifact_id = _snapshot_active_artifact_id(task.graphStateJson)
                elif payload.get("workflow") == "short_medium" and payload.get(
                    "operation"
                ) in {
                    "generate_outline",
                    "generate_manuscript",
                    "replace_selection",
                }:
                    candidate_id = result.get("candidateVersionId")
                    artifact_id = candidate_id if isinstance(candidate_id, str) else None
                artifact = (
                    await session.scalar(
                        select(ReviewArtifact)
                        .where(ReviewArtifact.id == artifact_id)
                    )
                    if artifact_id is not None
                    else None
                )
                artifacts = [artifact] if isinstance(artifact, ReviewArtifact) else []
        return project_run_status(task, commands=commands, artifacts=artifacts)

    async def list_runs(
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
        if operation is not None and operation not in _PUBLIC_OPERATIONS:
            raise ApiError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="任务 operation 过滤值无效",
            )
        position = _decode_cursor(cursor)
        matched: list[WritingRunListItem] = []
        scan_position = position
        async with self._session_factory() as session:
            while len(matched) < limit + 1:
                statement = (
                    select(WritingTask)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(
                        Novel.userId == user_id,
                        WritingTask.novelId == novel_id,
                    )
                    .order_by(WritingTask.createdAt.desc(), WritingTask.id.desc())
                    .limit(_SCAN_BATCH_SIZE)
                )
                if chapter_id is not None:
                    statement = statement.where(WritingTask.chapterId == chapter_id)
                if writing_session_id is not None:
                    statement = statement.where(
                        WritingTask.writingSessionId == writing_session_id
                    )
                if scan_position is not None:
                    created_at, task_id = scan_position
                    statement = statement.where(
                        or_(
                            WritingTask.createdAt < created_at,
                            and_(
                                WritingTask.createdAt == created_at,
                                WritingTask.id < task_id,
                            ),
                        )
                    )
                tasks = list((await session.scalars(statement)).all())
                if not tasks:
                    break
                task_ids = [task.id for task in tasks]
                commands = list(
                    (
                        await session.scalars(
                            select(WritingRunCommand)
                            .where(WritingRunCommand.taskId.in_(task_ids))
                            .order_by(
                                WritingRunCommand.taskId,
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
                            .where(ReviewArtifact.taskId.in_(task_ids))
                            .order_by(
                                ReviewArtifact.taskId,
                                ReviewArtifact.createdAt.desc(),
                                ReviewArtifact.id.desc(),
                            )
                        )
                    ).all()
                )
                commands_by_task: dict[str, list[WritingRunCommand]] = defaultdict(list)
                artifacts_by_task: dict[str, list[ReviewArtifact]] = defaultdict(list)
                for command in commands:
                    commands_by_task[command.taskId].append(command)
                for artifact in artifacts:
                    if artifact.taskId is not None:
                        artifacts_by_task[artifact.taskId].append(artifact)
                for task in tasks:
                    status = project_run_status(
                        task,
                        commands=commands_by_task[task.id],
                        artifacts=artifacts_by_task[task.id],
                    )
                    if operation is not None and status.operation != operation:
                        continue
                    if outcome is not None and status.outcome.state != outcome:
                        continue
                    matched.append(_list_item(status))
                    if len(matched) == limit + 1:
                        break
                last_task = tasks[-1]
                scan_position = (last_task.createdAt, last_task.id)
                if len(tasks) < _SCAN_BATCH_SIZE:
                    break

        page = matched[:limit]
        next_cursor = None
        if len(matched) > limit and page:
            last_item = page[-1]
            next_cursor = encode_run_cursor(
                created_at=last_item.createdAt,
                task_id=last_item.taskId,
            )
        return WritingRunListResponse(items=page, nextCursor=next_cursor)


def project_run_status(
    task: WritingTask,
    *,
    commands: list[WritingRunCommand],
    artifacts: list[ReviewArtifact],
) -> WritingRunStatusResponse:
    commands = sorted(commands, key=lambda item: (item.createdAt, item.id), reverse=True)
    artifacts = sorted(artifacts, key=lambda item: (item.createdAt, item.id), reverse=True)
    current = commands[0] if commands else None
    start = next((item for item in reversed(commands) if item.kind == "start"), current)
    start_payload = _command_job(start)
    snapshot_payload = _json_object(task.graphStateJson)
    workflow: Literal["long_serial", "short_medium"] = (
        "short_medium"
        if start_payload.get("workflow") == "short_medium"
        or snapshot_payload.get("workflow") == "short_medium"
        else "long_serial"
    )
    operation_value = start_payload.get("operation")
    if operation_value is None and workflow == "short_medium":
        operation_value = snapshot_payload.get("operation")
    operation = (
        operation_value
        if isinstance(operation_value, str) and operation_value in _PUBLIC_OPERATIONS
        else None
    )
    target = _object_or_chapter_target(start_payload.get("target"), task.chapterId)
    scope = _object_or_chapter_scope(start_payload.get("scope"), task.chapterId)
    checkpoint = _checkpoint(task.graphStateJson)

    effective, cancel_effective, chain_valid = _resolve_effective_command(current, commands)
    result_kind = "none"
    result_id: str | None = None
    result_ready = False
    active_artifact_id: str | None = None
    review_report: str | None = None
    candidate_version_id: str | None = None
    check_report: dict[str, JsonValue] | None = None
    effective_result = _full_result(effective)

    if workflow == "short_medium":
        candidate_version = effective_result.get("candidateVersionId")
        candidate_version_id = candidate_version if isinstance(candidate_version, str) else None
        if operation in {"generate_outline", "generate_manuscript", "replace_selection"}:
            result_kind = "short_candidate"
            result_id = candidate_version_id
            candidate = _artifact_by_id(artifacts, candidate_version_id)
            result_ready = _short_candidate_ready(
                task,
                effective,
                start_payload,
                candidate_version_id,
                candidate,
            )
        elif operation == "full_check":
            result_kind = "check_report"
            result_id = effective.id if effective is not None else None
            report = effective_result.get("checkReport")
            if isinstance(report, dict):
                check_report = cast(dict[str, JsonValue], report)
                result_ready = True
    elif operation in _LONG_ARTIFACT_KINDS:
        expected_kind = _LONG_ARTIFACT_KINDS[operation]
        decision_artifact_id = _decision_artifact_id(effective)
        persisted_decision_artifact = _artifact_by_id(artifacts, decision_artifact_id)
        artifact_hint = decision_artifact_id or _snapshot_active_artifact_id(
            task.graphStateJson
        )
        artifact = _long_artifact(
            task,
            artifacts,
            expected_kind=expected_kind,
            artifact_id=artifact_hint,
        )
        result_kind = "review_artifact"
        result_id = artifact.id if artifact is not None else decision_artifact_id
        if artifact is not None and _awaiting_artifact_ready(task, effective, artifact):
            active_artifact_id = artifact.id
            result_ready = True
        elif _applied_artifact_ready(task, effective, artifact):
            result_ready = True
        elif (
            task.phase == "completed"
            and persisted_decision_artifact is None
            and _discard_decision_ready(effective, task, result_id)
        ):
            result_ready = True
    elif operation == "review_chapter":
        result_kind = "final_message"
        callback = effective_result.get(TERMINAL_CALLBACK_RESULT_FIELD)
        report = callback.get("finalResponse") if isinstance(callback, dict) else None
        if (
            effective is not None
            and effective.status == "succeeded"
            and task.phase == "completed"
            and isinstance(report, str)
            and report.strip()
        ):
            review_report = report
            result_ready = True
    else:
        active_id = _snapshot_active_artifact_id(task.graphStateJson)
        artifact = _artifact_by_id(artifacts, active_id)
        if active_id is not None:
            result_kind = "review_artifact"
            result_id = active_id
            result_ready = artifact is not None and _artifact_is_authoritative(
                task, artifact, "awaiting_user"
            )
            if result_ready:
                active_artifact_id = active_id

    outcome = project_writing_run_outcome(
        WritingRunOutcomeFacts(
            task_phase=task.phase,
            task_updated_at=task.updatedAt,
            workflow="short_medium" if workflow == "short_medium" else "long_form",
            command_id=current.id if current is not None else None,
            command_kind=(
                logical_command_kind(current.kind, current.payloadJson)
                if current is not None
                else None
            ),
            command_status=current.status if current is not None else None,
            command_updated_at=current.updatedAt if current is not None else None,
            operation=operation,
            result_kind=cast(Any, result_kind),
            result_id=result_id,
            result_ready=result_ready,
            effective_command_status=effective.status if effective is not None else None,
            cancel_effective=cancel_effective,
            cancel_chain_valid=chain_valid,
        )
    )
    explicit_long = workflow == "long_serial" and operation in {
        "plan_chapter",
        "write_chapter",
        "review_chapter",
    }
    if (
        explicit_long
        and task.phase == "completed"
        and outcome.state == "succeeded"
        and not result_ready
    ):
        outcome = outcome.model_copy(
            update={
                "state": "inconsistent",
                "code": "LONG_SERIAL_RESULT_MISSING",
                "streamShouldClose": True,
                "reconciliationRequired": True,
                "result": outcome.result.model_copy(update={"ready": False}),
            }
        )
    error = _command_error(effective, effective_result)
    recoverable = bool(
        outcome.state in _ACTIVE_OUTCOMES
        and resolve_recoverable_checkpoint(task, commands) is not None
    )
    return WritingRunStatusResponse(
        taskId=task.id,
        novelId=task.novelId,
        chapterId=task.chapterId,
        writingSessionId=task.writingSessionId,
        workflow=workflow,
        operation=cast(Any, operation),
        target=target,
        scope=scope,
        phase=task.phase,
        checkpoint=checkpoint,
        activeArtifactId=active_artifact_id,
        recoverable=recoverable,
        reviewReport=review_report,
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
        commandId=current.id if current is not None else None,
        commandStatus=(
            cast(WritingCommandStatus, current.status) if current is not None else None
        ),
        candidateVersionId=candidate_version_id,
        checkReport=check_report,
        error=error,
        outcome=outcome,
    )


def _decode_cursor(value: str | None) -> tuple[datetime, str] | None:
    if value is None:
        return None
    try:
        created_at, task_id = decode_run_cursor(value)
    except InvalidCursorError as exc:
        raise ApiError(
            status_code=422,
            code="WRITING_RUN_CURSOR_INVALID",
            message="任务游标无效",
        ) from exc
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(UTC).replace(tzinfo=None)
    return created_at, task_id


def _list_item(status: WritingRunStatusResponse) -> WritingRunListItem:
    if status.createdAt is None or status.target is None or status.scope is None:
        raise RuntimeError("统一任务投影缺少列表必需字段")
    return WritingRunListItem(
        taskId=status.taskId,
        novelId=status.novelId,
        chapterId=status.chapterId,
        writingSessionId=status.writingSessionId,
        workflow=status.workflow,
        operation=status.operation,
        target=status.target,
        scope=status.scope,
        phase=status.phase,
        outcome=status.outcome,
        activeArtifactId=status.activeArtifactId,
        recoverable=status.recoverable,
        createdAt=status.createdAt,
        updatedAt=status.updatedAt,
    )


def _command_job(command: WritingRunCommand | None) -> dict[str, Any]:
    payload = _json_object(command.payloadJson if command is not None else None)
    job = payload.get("job")
    return cast(dict[str, Any], job) if isinstance(job, dict) else payload


def _full_result(command: WritingRunCommand | None) -> dict[str, Any]:
    return _json_object(command.resultJson if command is not None else None)


def _json_object(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return cast(dict[str, Any], parsed) if isinstance(parsed, dict) else {}


def _resolve_effective_command(
    current: WritingRunCommand | None,
    commands: list[WritingRunCommand],
) -> tuple[WritingRunCommand | None, bool | None, bool]:
    if (
        current is None
        or logical_command_kind(current.kind, current.payloadJson) != "cancel"
        or current.status != "succeeded"
    ):
        return current, None, True
    result = _full_result(current)
    effective = result.get("effective")
    if effective is True:
        return current, True, True
    if effective is not False:
        return current, False, False
    by_id = {command.id: command for command in commands}
    seen = {current.id}
    candidate = current
    while logical_command_kind(candidate.kind, candidate.payloadJson) == "cancel":
        if candidate.status == "failed":
            return candidate, False, True
        if candidate.status != "succeeded":
            return current, False, False
        result = _full_result(candidate)
        effective = result.get("effective")
        if effective is True:
            return candidate, True, True
        if effective is not False:
            return current, False, False
        prior = result.get("priorOutcome")
        prior_command = prior.get("currentCommand") if isinstance(prior, dict) else None
        prior_id = prior_command.get("id") if isinstance(prior_command, dict) else None
        if not isinstance(prior_id, str) or prior_id in seen:
            return current, False, False
        previous = by_id.get(prior_id)
        if previous is None or previous.taskId != current.taskId:
            return current, False, False
        seen.add(prior_id)
        candidate = previous
    return candidate, False, True


def _checkpoint(value: str | None) -> WritingRunCheckpointResponse | None:
    snapshot = _json_object(value)
    sequence = snapshot.get("eventSequence")
    phase = snapshot.get("phase")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or not isinstance(phase, str):
        return None
    stage = snapshot.get("operationStage")
    step = snapshot.get("operationStep")
    return WritingRunCheckpointResponse(
        eventSequence=sequence,
        phase=phase,
        operationStage=stage if isinstance(stage, str) else None,
        operationStep=step if isinstance(step, str) else None,
    )


def _snapshot_active_artifact_id(value: str | None) -> str | None:
    artifact_review = _json_object(value).get("artifactReview")
    artifact_id = (
        artifact_review.get("activeArtifactId")
        if isinstance(artifact_review, dict)
        else None
    )
    return artifact_id if isinstance(artifact_id, str) else None


def _object_or_chapter_target(value: object, chapter_id: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return cast(dict[str, JsonValue], value)
    return {"type": "chapter", "id": chapter_id}


def _object_or_chapter_scope(value: object, chapter_id: str) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return cast(dict[str, JsonValue], value)
    return {"kind": "chapter", "chapterId": chapter_id}


def _artifact_by_id(
    artifacts: list[ReviewArtifact], artifact_id: str | None
) -> ReviewArtifact | None:
    if artifact_id is None:
        return None
    return next((item for item in artifacts if item.id == artifact_id), None)


def _long_artifact(
    task: WritingTask,
    artifacts: list[ReviewArtifact],
    *,
    expected_kind: str,
    artifact_id: str | None,
) -> ReviewArtifact | None:
    candidates = [
        item
        for item in artifacts
        if (artifact_id is None or item.id == artifact_id)
        and item.taskId == task.id
        and item.novelId == task.novelId
        and item.chapterId == task.chapterId
        and item.kind == expected_kind
    ]
    if len(candidates) != 1:
        return None
    return candidates[0]


def _artifact_is_authoritative(
    task: WritingTask, artifact: ReviewArtifact, status: str
) -> bool:
    return bool(
        artifact.taskId == task.id
        and artifact.novelId == task.novelId
        and artifact.chapterId == task.chapterId
        and artifact.status == status
    )


def _decision_artifact_id(command: WritingRunCommand | None) -> str | None:
    if command is None or command.kind != "artifact_decision":
        return None
    return command.artifactId


def _awaiting_artifact_ready(
    task: WritingTask,
    command: WritingRunCommand | None,
    artifact: ReviewArtifact | None,
) -> bool:
    if (
        task.phase != "awaiting_user_review"
        or artifact is None
        or not _artifact_is_authoritative(task, artifact, "awaiting_user")
        or command is None
        or command.taskId != task.id
        or command.status != "succeeded"
    ):
        return False
    if command.kind == "start":
        return True
    return bool(
        _artifact_decision_matches(command, task, artifact.id, "revise")
        and artifact.revision >= 2
        and artifact.updatedAt >= command.createdAt
    )


def _applied_artifact_ready(
    task: WritingTask,
    command: WritingRunCommand | None,
    artifact: ReviewArtifact | None,
) -> bool:
    return bool(
        task.phase == "completed"
        and artifact is not None
        and _artifact_is_authoritative(task, artifact, "applied")
        and _artifact_decision_matches(command, task, artifact.id, "approve")
    )


def _artifact_decision_matches(
    command: WritingRunCommand | None,
    task: WritingTask,
    artifact_id: str,
    decision: str,
) -> bool:
    if command is None:
        return False
    payload = _command_job(command)
    resume_input = payload.get("resumeInput")
    result = _full_result(command)
    return bool(
        command.taskId == task.id
        and command.kind == "artifact_decision"
        and command.status == "succeeded"
        and command.decision == decision
        and command.artifactId == artifact_id
        and payload.get("resume") is True
        and isinstance(resume_input, dict)
        and resume_input.get("artifactId") == artifact_id
        and resume_input.get("decision") == decision
        and result.get("artifactId") == artifact_id
        and result.get("taskId") == task.id
        and result.get("commandId") == command.id
        and result.get("decision") == decision
        and result.get("status")
        in {"pending", "submitted", "processing", "succeeded", "failed"}
    )


def _discard_decision_ready(
    command: WritingRunCommand | None,
    task: WritingTask,
    artifact_id: str | None,
) -> bool:
    result = _full_result(command)
    return bool(
        artifact_id is not None
        and _artifact_decision_matches(command, task, artifact_id, "discard")
        and result.get("deleted") is True
    )


def _has_recoverable_command(
    task: WritingTask,
    command: WritingRunCommand | None,
) -> bool:
    if (
        command is None
        or command.taskId != task.id
        or not command.kind
        or command.status
        not in {"pending", "submitted", "processing", "succeeded", "failed"}
    ):
        return False
    try:
        payload = json.loads(command.payloadJson)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict)


def _short_candidate_ready(
    task: WritingTask,
    command: WritingRunCommand | None,
    payload: dict[str, Any],
    candidate_id: str | None,
    candidate: ReviewArtifact | None,
) -> bool:
    if command is None or candidate_id is None or candidate is None:
        return False
    if (
        candidate.id != candidate_id
        or command.artifactId != candidate_id
        or candidate.taskId != task.id
        or candidate.novelId != task.novelId
        or candidate.status not in {"awaiting_user", "applied"}
    ):
        return False
    operation = payload.get("operation")
    document_type = payload.get("documentType")
    if operation == "generate_outline" and document_type != "outline":
        return False
    if operation == "generate_manuscript" and document_type != "manuscript":
        return False
    if document_type == "outline":
        return candidate.kind == "outline_draft" and candidate.chapterId is None
    if document_type == "manuscript":
        return bool(
            payload.get("chapterId") == task.chapterId
            and candidate.kind == "chapter_draft"
            and candidate.chapterId == task.chapterId
        )
    return False


def _command_error(
    command: WritingRunCommand | None,
    result: dict[str, Any],
) -> dict[str, JsonValue] | None:
    if command is None or command.status != "failed":
        return None
    error: dict[str, JsonValue] = {
        "code": command.lastError
        or (result.get("code") if isinstance(result.get("code"), str) else None)
        or "WRITING_RUN_FAILED"
    }
    message = result.get("message")
    if isinstance(message, str):
        error["message"] = message
    return error

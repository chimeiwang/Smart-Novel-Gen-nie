from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from inkforge_contracts.long_serial import SourceBinding
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Chapter,
    Novel,
    Outline,
    OutlineNode,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    ReviewArtifactRevision,
    WritingRunCommand,
    WritingTask,
)
from ..errors import ApiError
from ..short_medium.repository import is_short_medium_artifact_key
from ..writing.source_bindings import verify_source_bindings
from ..writing.transaction_locks import WritingLockRequest, lock_writing_rows
from .schemas import (
    ArtifactEvaluationResponse,
    ArtifactKind,
    ArtifactStatus,
    CreateArtifactRequest,
    EvaluationVerdict,
    ReviewArtifactResponse,
    SourceBindingStatus,
    SubmitArtifactEvaluationRequest,
    assert_status_transition,
)

_SOURCE_BOUND_KINDS = frozenset({"beat_plan", "chapter_draft"})


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    id: str
    novel_id: str
    chapter_id: str | None
    task_id: str | None
    workflow_run_id: str | None
    artifact_key: str | None
    kind: str
    status: str
    title: str | None
    summary: str | None
    payload: dict[str, Any]
    diff: Any
    created_by_agent: str | None
    updated_by_agent: str | None
    reviewer_agent: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class ReviewRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def require_artifact(self, user_id: str, artifact_id: str) -> ArtifactRecord:
        async with self._session_factory() as session:
            artifact = await _owned_artifact(session, user_id, artifact_id)
            if artifact is None:
                raise ApiError(
                    status_code=403,
                    code="REVIEW_ARTIFACT_FORBIDDEN",
                    message="无权访问该待审核草案",
                )
            return _record(artifact)

    async def lock_decision_scope(
        self, user_id: str, artifact_id: str
    ) -> ArtifactRecord:
        async with self._session_factory() as session:
            async with session.begin():
                identity = (
                    await session.execute(
                        select(
                            ReviewArtifact.novelId,
                            ReviewArtifact.chapterId,
                            ReviewArtifact.taskId,
                        )
                        .join(Novel, Novel.id == ReviewArtifact.novelId)
                        .where(
                            ReviewArtifact.id == artifact_id,
                            Novel.userId == user_id,
                        )
                    )
                ).one_or_none()
                if identity is None:
                    raise ApiError(
                        status_code=403,
                        code="REVIEW_ARTIFACT_FORBIDDEN",
                        message="无权访问该待审核草案",
                    )
                novel_id, chapter_id, task_id = identity
                if task_id is None:
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_TASK_MISSING",
                        message="待审核草案没有关联写作任务",
                    )
                current_command_id = await _latest_command_id(session, task_id)
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
                artifact = locked.artifact
                task = locked.task
                if artifact is None or task is None:
                    raise RuntimeError("统一写作锁未返回草案决定资源")
                if await _latest_command_id(session, task_id, lock=True) != current_command_id:
                    raise ApiError(
                        status_code=409,
                        code="WRITING_COMMAND_ACTIVE",
                        message="写作任务的当前命令已变化",
                    )
                active_command_id = await session.scalar(
                    select(WritingRunCommand.id)
                    .where(
                        WritingRunCommand.taskId == task_id,
                        WritingRunCommand.status.in_(("pending", "submitted", "processing")),
                    )
                    .with_for_update()
                )
                if active_command_id is not None:
                    raise ApiError(
                        status_code=409,
                        code="WRITING_COMMAND_ACTIVE",
                        message="该写作任务已有正在处理的命令",
                        details={"taskId": task_id},
                    )
                if task.phase != "awaiting_user_review":
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_NOT_AWAITING_USER",
                        message="当前写作任务不在等待草案决定状态",
                    )
                await _lock_artifact_source_commands(session, artifact)
                return _record(artifact)

    async def prepare_decision(
        self,
        user_id: str,
        artifact_id: str,
        *,
        expected_revision: int,
        decision: str,
    ) -> ArtifactRecord:
        async with self._session_factory() as session:
            async with session.begin():
                artifact = await session.scalar(
                    select(ReviewArtifact)
                    .join(Novel, Novel.id == ReviewArtifact.novelId)
                    .where(ReviewArtifact.id == artifact_id, Novel.userId == user_id)
                    .with_for_update()
                )
                if artifact is None:
                    raise ApiError(
                        status_code=403,
                        code="REVIEW_ARTIFACT_FORBIDDEN",
                        message="无权访问该待审核草案",
                    )
                if artifact.revision != expected_revision:
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_REVISION_CONFLICT",
                        message="待审核草案修订号已变化",
                        details={
                            "expectedRevision": expected_revision,
                            "currentRevision": artifact.revision,
                        },
                    )
                if artifact.status != "awaiting_user":
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_NOT_AWAITING_USER",
                        message="当前草案状态不能接受用户决定",
                    )
                if decision != "discard" and await _artifact_requires_source_bindings(
                    session, artifact
                ):
                    bindings = await _decision_source_bindings(session, artifact)
                    await verify_source_bindings(
                        session,
                        tuple(SourceBinding.model_validate(item) for item in bindings),
                    )
                return _record(artifact)

    async def get_response(self, user_id: str, artifact_id: str) -> ReviewArtifactResponse:
        async with self._session_factory() as session:
            artifact = await _owned_artifact(session, user_id, artifact_id)
            if artifact is None:
                raise ApiError(
                    status_code=403,
                    code="REVIEW_ARTIFACT_FORBIDDEN",
                    message="无权访问该待审核草案",
                )
            evaluations = (
                await session.execute(
                    select(ReviewArtifactEvaluation)
                    .where(ReviewArtifactEvaluation.artifactId == artifact_id)
                    .order_by(ReviewArtifactEvaluation.createdAt.desc())
                )
            ).scalars()
            source_bindings, source_binding_status = await _source_binding_view(session, artifact)
            return _response(
                artifact,
                list(evaluations),
                source_bindings=source_bindings,
                source_binding_status=source_binding_status,
            )

    async def get_task_artifact(self, user_id: str, task_id: str) -> ReviewArtifactResponse | None:
        async with self._session_factory() as session:
            owned_task_id = await session.scalar(
                select(WritingTask.id)
                .join(Novel, Novel.id == WritingTask.novelId)
                .where(
                    WritingTask.id == task_id,
                    Novel.userId == user_id,
                )
            )
            if owned_task_id is None:
                raise ApiError(
                    status_code=404,
                    code="WRITING_TASK_NOT_FOUND",
                    message="写作任务不存在",
                )
            artifact = (
                await session.execute(
                    select(ReviewArtifact)
                    .join(Novel, Novel.id == ReviewArtifact.novelId)
                    .where(
                        ReviewArtifact.taskId == task_id,
                        Novel.userId == user_id,
                        ReviewArtifact.status.in_(
                            ("draft", "under_review", "awaiting_user", "applying")
                        ),
                    )
                    .order_by(ReviewArtifact.updatedAt.desc(), ReviewArtifact.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if artifact is None:
                return None
            evaluations = (
                await session.execute(
                    select(ReviewArtifactEvaluation)
                    .where(ReviewArtifactEvaluation.artifactId == artifact.id)
                    .order_by(ReviewArtifactEvaluation.createdAt.desc())
                )
            ).scalars()
            source_bindings, source_binding_status = await _source_binding_view(session, artifact)
            return _response(
                artifact,
                list(evaluations),
                source_bindings=source_bindings,
                source_binding_status=source_binding_status,
            )

    async def list_task_artifacts(
        self,
        user_id: str,
        novel_id: str,
        task_id: str,
        status: str | None,
        kind: str | None,
    ) -> list[dict[str, Any]]:
        conditions = [
            ReviewArtifact.novelId == novel_id,
            ReviewArtifact.taskId == task_id,
            Novel.userId == user_id,
        ]
        if status is not None:
            conditions.append(ReviewArtifact.status == status)
        if kind is not None:
            conditions.append(ReviewArtifact.kind == kind)
        async with self._session_factory() as session:
            artifacts = list(
                (
                    await session.scalars(
                        select(ReviewArtifact)
                        .join(Novel, Novel.id == ReviewArtifact.novelId)
                        .where(*conditions)
                        .order_by(ReviewArtifact.updatedAt.desc(), ReviewArtifact.id.desc())
                    )
                ).all()
            )
        return [
            {
                "id": artifact.id,
                "novelId": artifact.novelId,
                "chapterId": artifact.chapterId,
                "taskId": artifact.taskId,
                "artifactKey": artifact.artifactKey,
                "kind": artifact.kind,
                "status": artifact.status,
                "title": artifact.title,
                "summary": artifact.summary,
                "revision": artifact.revision,
                "updatedByAgent": artifact.updatedByAgent,
                "reviewerAgent": artifact.reviewerAgent,
                "updatedAt": artifact.updatedAt.isoformat(),
            }
            for artifact in artifacts
        ]

    async def list_artifacts(
        self,
        user_id: str,
        *,
        novel_id: str,
        chapter_id: str | None,
        task_id: str | None,
        status: str | None,
        kind: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ReviewArtifactResponse], str | None]:
        conditions = [ReviewArtifact.novelId == novel_id, Novel.userId == user_id]
        if chapter_id is not None:
            conditions.append(ReviewArtifact.chapterId == chapter_id)
        if task_id is not None:
            conditions.append(ReviewArtifact.taskId == task_id)
        if status is not None:
            conditions.append(ReviewArtifact.status == status)
        if kind is not None:
            conditions.append(ReviewArtifact.kind == kind)
        if cursor is not None:
            created_at, artifact_id = _decode_cursor(cursor)
            conditions.append(
                or_(
                    ReviewArtifact.createdAt < created_at,
                    and_(ReviewArtifact.createdAt == created_at, ReviewArtifact.id < artifact_id),
                )
            )
        async with self._session_factory() as session:
            artifacts = list(
                (
                    await session.scalars(
                        select(ReviewArtifact)
                        .join(Novel, Novel.id == ReviewArtifact.novelId)
                        .where(*conditions)
                        .order_by(ReviewArtifact.createdAt.desc(), ReviewArtifact.id.desc())
                        .limit(limit + 1)
                    )
                ).all()
            )
            has_more = len(artifacts) > limit
            artifacts = artifacts[:limit]
            source_views = await _source_binding_views(session, artifacts)
            responses = [
                _response(
                    artifact,
                    [],
                    source_bindings=source_views[artifact.id][0],
                    source_binding_status=source_views[artifact.id][1],
                )
                for artifact in artifacts
            ]
        next_cursor = _encode_cursor(artifacts[-1]) if has_more and artifacts else None
        return responses, next_cursor

    async def transition(self, artifact_id: str, current: str, target: str) -> None:
        values: dict[str, object] = {"status": target, "updatedAt": utc_now()}
        if target == "applied":
            values["appliedAt"] = utc_now()
        async with self._session_factory() as session:
            async with session.begin():
                outcome = cast(
                    CursorResult[Any],
                    await session.execute(
                        update(ReviewArtifact)
                        .where(
                            ReviewArtifact.id == artifact_id,
                            ReviewArtifact.status == current,
                        )
                        .values(**values)
                    ),
                )
                if outcome.rowcount != 1:
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_STATUS_CONFLICT",
                        message="待审核草案状态已被其他请求修改",
                    )

    async def discard(self, user_id: str, artifact_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                artifact = await _owned_artifact(session, user_id, artifact_id)
                if artifact is None:
                    return
                if is_short_medium_artifact_key(artifact.artifactKey):
                    raise ApiError(
                        status_code=409,
                        code="SHORT_MEDIUM_VERSION_ROUTE_REQUIRED",
                        message="中短篇版本只能通过专用版本接口操作",
                    )
                await session.execute(
                    delete(ReviewArtifact).where(ReviewArtifact.id == artifact_id)
                )

    async def create_or_revise(
        self, user_id: str, request: CreateArtifactRequest
    ) -> ReviewArtifactResponse:
        if is_short_medium_artifact_key(request.artifactKey):
            raise ApiError(
                status_code=409,
                code="SHORT_MEDIUM_VERSION_ROUTE_REQUIRED",
                message="中短篇版本只能通过专用版本接口创建",
            )
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.scalar(
                    select(WritingTask)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(
                        WritingTask.id == request.taskId,
                        WritingTask.novelId == request.novelId,
                        Novel.userId == user_id,
                    )
                    .with_for_update()
                )
                if task is None or (
                    request.chapterId is not None and task.chapterId != request.chapterId
                ):
                    raise ApiError(
                        status_code=403,
                        code="ARTIFACT_TASK_MISMATCH",
                        message="待审核草案与写作任务资源不匹配",
                    )
                await _require_current_writing_job(session, task.id, request.jobId)
                existing: ReviewArtifact | None = None
                if request.artifactKey is not None:
                    existing = await session.scalar(
                        select(ReviewArtifact)
                        .where(
                            ReviewArtifact.novelId == request.novelId,
                            ReviewArtifact.taskId == request.taskId,
                            ReviewArtifact.artifactKey == request.artifactKey,
                            ReviewArtifact.status.in_(("draft", "under_review", "awaiting_user")),
                        )
                        .with_for_update()
                    )
                payload = dict(request.payload)
                await _materialize_selection_payload(
                    session, payload, kind=request.kind, novel_id=request.novelId
                )
                if await _artifact_kind_requires_source_bindings(
                    session, request.kind, task.id
                ):
                    source_command_id: str
                    if existing is None:
                        source_command_id, _bindings = await _source_bindings_for_task(
                            session, task.id
                        )
                    else:
                        existing_payload = _parse_json(existing.payloadJson, {})
                        control = (
                            existing_payload.get("_inkforgeControl")
                            if isinstance(existing_payload, dict)
                            else None
                        )
                        inherited_source_command_id = (
                            control.get("sourceCommandId")
                            if isinstance(control, dict)
                            else None
                        )
                        if (
                            not isinstance(inherited_source_command_id, str)
                            or not inherited_source_command_id
                        ):
                            raise ApiError(
                                status_code=409,
                                code="ARTIFACT_SOURCE_BINDINGS_MISSING",
                                message="待审核草案缺少可继承的来源命令",
                            )
                        source_command_id = inherited_source_command_id
                    payload["_inkforgeControl"] = {
                        "sourceCommandId": source_command_id
                    }
                payload_json = json.dumps(payload, ensure_ascii=False)
                materialized_diff = _selection_diff(payload)
                diff_json = (
                    json.dumps(materialized_diff, ensure_ascii=False)
                    if materialized_diff is not None
                    else (
                        json.dumps(request.diff, ensure_ascii=False)
                        if request.diff is not None
                        else None
                    )
                )
                if existing is None:
                    artifact = ReviewArtifact(
                        novelId=request.novelId,
                        chapterId=request.chapterId,
                        taskId=request.taskId,
                        workflowRunId=request.workflowRunId,
                        artifactKey=request.artifactKey,
                        kind=request.kind,
                        status=request.status,
                        title=request.title,
                        summary=request.summary,
                        payloadJson=payload_json,
                        diffJson=diff_json,
                        createdByAgent=request.createdByAgent,
                        updatedByAgent=request.createdByAgent,
                        reviewerAgent=request.reviewerAgent,
                        revision=1,
                    )
                    session.add(artifact)
                    await session.flush()
                else:
                    if existing.kind != request.kind:
                        raise ApiError(
                            status_code=409,
                            code="ARTIFACT_KIND_CONFLICT",
                            message="同一草案标识不能变更草案类型",
                        )
                    try:
                        assert_status_transition(existing.status, request.status)
                    except ValueError as exc:
                        raise ApiError(
                            status_code=409,
                            code="ARTIFACT_STATUS_CONFLICT",
                            message=str(exc),
                        ) from exc
                    existing.status = request.status
                    existing.kind = request.kind
                    existing.title = request.title
                    existing.summary = request.summary
                    existing.payloadJson = payload_json
                    existing.diffJson = diff_json
                    existing.updatedByAgent = request.createdByAgent
                    existing.reviewerAgent = request.reviewerAgent
                    existing.revision += 1
                    artifact = existing
                session.add(
                    ReviewArtifactRevision(
                        artifactId=artifact.id,
                        revision=artifact.revision,
                        summary=request.summary,
                        payloadJson=payload_json,
                        diffJson=diff_json,
                        createdByAgent=request.createdByAgent,
                    )
                )
        return await self.get_response(user_id, artifact.id)

    async def submit_evaluation(
        self,
        user_id: str,
        artifact_id: str,
        request: SubmitArtifactEvaluationRequest,
    ) -> ReviewArtifactResponse:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.scalar(
                    select(WritingTask)
                    .join(Novel, Novel.id == WritingTask.novelId)
                    .where(
                        WritingTask.id == request.taskId,
                        WritingTask.novelId == request.novelId,
                        Novel.userId == user_id,
                    )
                    .with_for_update()
                )
                if task is None:
                    raise ApiError(
                        status_code=403,
                        code="ARTIFACT_TASK_MISMATCH",
                        message="复审结论与待审核草案资源不匹配",
                    )
                artifact = await session.scalar(
                    select(ReviewArtifact)
                    .join(Novel, Novel.id == ReviewArtifact.novelId)
                    .where(
                        ReviewArtifact.id == artifact_id,
                        ReviewArtifact.novelId == request.novelId,
                        ReviewArtifact.taskId == request.taskId,
                        Novel.userId == user_id,
                    )
                    .with_for_update()
                )
                if artifact is None:
                    raise ApiError(
                        status_code=403,
                        code="ARTIFACT_TASK_MISMATCH",
                        message="复审结论与待审核草案资源不匹配",
                    )
                await _require_current_writing_job(session, task.id, request.jobId)
                if artifact.revision != request.revision:
                    raise ApiError(
                        status_code=409,
                        code="ARTIFACT_REVISION_CONFLICT",
                        message="复审结论对应的草案修订号已过期",
                    )
                existing = await session.scalar(
                    select(ReviewArtifactEvaluation).where(
                        ReviewArtifactEvaluation.artifactId == artifact_id,
                        ReviewArtifactEvaluation.revision == request.revision,
                        ReviewArtifactEvaluation.evaluatorAgent == request.evaluatorAgent,
                    )
                )
                if existing is not None:
                    same = (
                        existing.verdict == request.verdict
                        and existing.summary == request.summary
                        and existing.requiredChanges == request.requiredChanges
                    )
                    if not same:
                        raise ApiError(
                            status_code=409,
                            code="ARTIFACT_EVALUATION_CONFLICT",
                            message="同一复审智能体重复提交了不同结论",
                        )
                else:
                    session.add(
                        ReviewArtifactEvaluation(
                            artifactId=artifact_id,
                            revision=request.revision,
                            evaluatorAgent=request.evaluatorAgent,
                            verdict=request.verdict,
                            summary=request.summary,
                            requiredChanges=request.requiredChanges,
                        )
                    )
        return await self.get_response(user_id, artifact_id)


async def _owned_artifact(
    session: AsyncSession, user_id: str, artifact_id: str
) -> ReviewArtifact | None:
    return (
        await session.execute(
            select(ReviewArtifact)
            .join(Novel, Novel.id == ReviewArtifact.novelId)
            .where(ReviewArtifact.id == artifact_id, Novel.userId == user_id)
        )
    ).scalar_one_or_none()


async def _materialize_selection_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    kind: str,
    novel_id: str,
) -> None:
    target = payload.get("target")
    mode = target.get("mode") if isinstance(target, dict) else None
    selection_modes = {
        "replace_selection",
        "outline_content_selection",
        "outline_node_content_selection",
    }
    if mode not in selection_modes:
        return
    if kind not in {"chapter_draft", "outline_draft"}:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_SELECTION_TARGET_INVALID",
            message="閫夊尯鑽夋 target mode 涓庣被鍨嬩笉鍖归厤",
        )
    expected_type = {
        "replace_selection": "chapter_content",
        "outline_content_selection": "outline_content",
        "outline_node_content_selection": "outline_node_content",
    }[mode]
    target_identity: dict[str, Any] = dict(target) if isinstance(target, dict) else {}
    identity: dict[str, Any] = dict(target_identity)
    identity_fields = (
        "resourceType",
        "resourceId",
        "baseUpdatedAt",
        "baseContentHash",
        "selectionStart",
        "selectionEnd",
        "selectedTextHash",
    )
    for key in identity_fields:
        if key in target_identity and key in payload and target_identity[key] != payload[key]:
            raise _selection_artifact_conflict(
                payload.get("resourceType"), payload.get("resourceId")
            )
        if key in payload:
            identity[key] = payload[key]
    resource_type = identity.get("resourceType")
    resource_id = identity.get("resourceId")
    if resource_type != expected_type or not isinstance(resource_id, str) or not resource_id:
        raise _selection_artifact_conflict(resource_type, resource_id)
    start = identity.get("selectionStart")
    end = identity.get("selectionEnd")
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or start < 0
        or end <= start
    ):
        raise _selection_artifact_conflict(resource_type, resource_id)
    base_hash = identity.get("baseContentHash")
    selected_hash = identity.get("selectedTextHash")
    base_updated_raw = identity.get("baseUpdatedAt")
    if not (
        isinstance(base_hash, str)
        and len(base_hash) == 64
        and all(char in "0123456789abcdef" for char in base_hash)
        and isinstance(selected_hash, str)
        and len(selected_hash) == 64
        and all(char in "0123456789abcdef" for char in selected_hash)
        and isinstance(base_updated_raw, str)
    ):
        raise _selection_artifact_conflict(resource_type, resource_id)
    try:
        base_updated = datetime.fromisoformat(base_updated_raw.replace("Z", "+00:00"))
    except ValueError:
        raise _selection_artifact_conflict(resource_type, resource_id) from None
    if base_updated.tzinfo is None:
        base_updated = base_updated.replace(tzinfo=UTC)

    if mode == "replace_selection":
        source_entity = await session.scalar(
            select(Chapter)
            .where(Chapter.id == resource_id, Chapter.novelId == novel_id)
            .with_for_update()
        )
        source = source_entity.content if source_entity is not None else None
        updated_at = source_entity.updatedAt if source_entity is not None else None
    elif mode == "outline_content_selection":
        source_entity = await session.scalar(
            select(Outline)
            .where(Outline.id == resource_id, Outline.novelId == novel_id)
            .with_for_update()
        )
        source = source_entity.content if source_entity is not None else None
        updated_at = source_entity.updatedAt if source_entity is not None else None
    else:
        source_entity = await session.scalar(
            select(OutlineNode)
            .where(OutlineNode.id == resource_id, OutlineNode.novelId == novel_id)
            .with_for_update()
        )
        source = source_entity.content if source_entity is not None else None
        updated_at = source_entity.updatedAt if source_entity is not None else None
    if source is None or updated_at is None:
        raise _selection_artifact_conflict(resource_type, resource_id)
    normalized_updated = (
        updated_at.replace(tzinfo=UTC)
        if updated_at.tzinfo is None
        else updated_at.astimezone(UTC)
    )
    if (
        normalized_updated != base_updated.astimezone(UTC)
        or hashlib.sha256(source.encode("utf-8")).hexdigest() != base_hash
        or end > len(source)
    ):
        raise _selection_artifact_conflict(resource_type, resource_id)
    selected = source[start:end]
    if hashlib.sha256(selected.encode("utf-8")).hexdigest() != selected_hash:
        raise _selection_artifact_conflict(resource_type, resource_id)
    provided_selected = payload.get("selectedText")
    if provided_selected is not None and provided_selected != selected:
        raise _selection_artifact_conflict(resource_type, resource_id)
    replacement = payload.get("replacement")
    if not isinstance(replacement, str) or not replacement.strip():
        raise ApiError(
            status_code=409,
            code="ARTIFACT_SELECTION_REPLACEMENT_INVALID",
            message="閫夊尯鑽夋缂哄皯闈炵┖ replacement",
        )
    prefix = source[:start]
    suffix = source[end:]
    candidate = prefix + replacement + suffix
    payload.update(
        {
            "resourceType": resource_type,
            "resourceId": resource_id,
            "baseUpdatedAt": base_updated_raw,
            "baseContentHash": base_hash,
            "selectionStart": start,
            "selectionEnd": end,
            "selectedTextHash": selected_hash,
            "selectedText": selected,
            "contextBefore": source[max(0, start - 1000) : start],
            "contextAfter": source[end : min(len(source), end + 1000)],
            "target": {
                "mode": mode,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "baseUpdatedAt": base_updated_raw,
                "baseContentHash": base_hash,
                "selectionStart": start,
                "selectionEnd": end,
                "selectedTextHash": selected_hash,
            },
            "selection": {
                "start": start,
                "end": end,
                "selectedText": selected,
                "selectedTextHash": selected_hash,
            },
            "candidate": candidate,
            "candidatePrefix": prefix,
            "candidateSuffix": suffix,
        }
    )


def _selection_artifact_conflict(resource_type: object, resource_id: object) -> ApiError:
    return ApiError(
        status_code=409,
        code="ARTIFACT_SOURCE_VERSION_CONFLICT",
        message="閫夊尯鑽夋鐨勬潵婧愮増鏈凡鍙樻洿",
        details={
            "resourceType": resource_type if isinstance(resource_type, str) else None,
            "resourceId": resource_id if isinstance(resource_id, str) else None,
        },
    )


def _selection_diff(payload: dict[str, Any]) -> dict[str, Any] | None:
    target = payload.get("target")
    if not isinstance(target, dict) or target.get("mode") not in {
        "replace_selection",
        "outline_content_selection",
        "outline_node_content_selection",
    }:
        return None
    selected = payload.get("selectedText")
    replacement = payload.get("replacement")
    candidate = payload.get("candidate")
    prefix = payload.get("candidatePrefix")
    suffix = payload.get("candidateSuffix")
    values = (selected, replacement, candidate, prefix, suffix)
    if not all(isinstance(value, str) for value in values):
        raise ApiError(
            status_code=409,
            code="ARTIFACT_SELECTION_DIFF_INVALID",
            message="閫夊尯鑽夋 Diff 鏁版嵁涓嶅畬鏁?",
        )
    selected_text, replacement_text, candidate_text, prefix_text, suffix_text = cast(
        tuple[str, str, str, str, str], values
    )
    before = prefix_text + selected_text + suffix_text
    return {
        "type": "selection",
        "mode": target["mode"],
        "resourceType": payload.get("resourceType"),
        "resourceId": payload.get("resourceId"),
        "selectionStart": payload.get("selectionStart"),
        "selectionEnd": payload.get("selectionEnd"),
        "selectedText": selected_text,
        "replacement": replacement_text,
        "before": before,
        "after": candidate_text,
        "candidate": candidate_text,
        "prefix": prefix_text,
        "suffix": suffix_text,
    }


async def _require_current_writing_job(
    session: AsyncSession, task_id: str, job_id: str
) -> None:
    command = await session.scalar(
        select(WritingRunCommand.id)
        .where(
            WritingRunCommand.id == job_id,
            WritingRunCommand.taskId == task_id,
            WritingRunCommand.status.in_(("pending", "submitted", "processing")),
        )
        .with_for_update()
    )
    if command is None:
        raise ApiError(
            status_code=409,
            code="WRITING_JOB_MISMATCH",
            message="待审核草案写入作业不是当前活动命令",
        )


async def _latest_command_id(
    session: AsyncSession,
    task_id: str,
    *,
    lock: bool = False,
) -> str | None:
    statement = (
        select(WritingRunCommand.id)
        .where(WritingRunCommand.taskId == task_id)
        .order_by(WritingRunCommand.createdAt.desc(), WritingRunCommand.id.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return cast(str | None, await session.scalar(statement))


async def _lock_artifact_source_commands(
    session: AsyncSession,
    artifact: ReviewArtifact,
) -> None:
    payload = _parse_json(artifact.payloadJson, {})
    control = payload.get("_inkforgeControl") if isinstance(payload, dict) else None
    source_command_id = control.get("sourceCommandId") if isinstance(control, dict) else None
    if not isinstance(source_command_id, str) or not source_command_id:
        return
    await session.scalar(
        select(WritingRunCommand)
        .where(WritingRunCommand.id == source_command_id)
        .with_for_update()
    )


async def _source_bindings_for_task(
    session: AsyncSession, task_id: str
) -> tuple[str, list[dict[str, Any]]]:
    command = await session.scalar(
        select(WritingRunCommand)
        .where(
            WritingRunCommand.taskId == task_id,
            WritingRunCommand.kind == "start",
        )
        .order_by(WritingRunCommand.createdAt.asc(), WritingRunCommand.id.asc())
        .limit(1)
    )
    if command is None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_SOURCE_BINDINGS_MISSING",
            message="待审核草案缺少权威来源命令",
        )
    bindings = _source_bindings_from_command(command)
    if bindings is None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_SOURCE_BINDINGS_MISSING",
            message="待审核草案缺少权威来源绑定",
        )
    return command.id, bindings


async def _decision_source_bindings(
    session: AsyncSession, artifact: ReviewArtifact
) -> list[dict[str, Any]]:
    payload = _parse_json(artifact.payloadJson, {})
    control = payload.get("_inkforgeControl") if isinstance(payload, dict) else None
    source_command_id = control.get("sourceCommandId") if isinstance(control, dict) else None
    if not isinstance(source_command_id, str) or not source_command_id or artifact.taskId is None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_SOURCE_BINDINGS_MISSING",
            message="待审核草案缺少权威来源绑定",
        )
    command = await session.scalar(
        select(WritingRunCommand)
        .where(
            WritingRunCommand.id == source_command_id,
            WritingRunCommand.taskId == artifact.taskId,
            WritingRunCommand.kind == "start",
        )
        .with_for_update()
    )
    bindings = _source_bindings_from_command(command) if command is not None else None
    if bindings is None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_SOURCE_BINDINGS_MISSING",
            message="待审核草案缺少权威来源绑定",
        )
    return bindings


async def _artifact_requires_source_bindings(
    session: AsyncSession, artifact: ReviewArtifact
) -> bool:
    return await _artifact_kind_requires_source_bindings(session, artifact.kind, artifact.taskId)


async def _artifact_kind_requires_source_bindings(
    session: AsyncSession, kind: str, task_id: str | None
) -> bool:
    if kind in _SOURCE_BOUND_KINDS:
        return True
    if kind != "outline_draft" or task_id is None:
        return False
    payload_json = await session.scalar(
        select(WritingRunCommand.payloadJson)
        .where(
            WritingRunCommand.taskId == task_id,
            WritingRunCommand.kind == "start",
        )
        .order_by(WritingRunCommand.createdAt.asc(), WritingRunCommand.id.asc())
        .limit(1)
    )
    if not isinstance(payload_json, str):
        return False
    payload = _parse_json(payload_json, {})
    job = payload.get("job") if isinstance(payload, dict) else None
    source = job if isinstance(job, dict) else payload
    return (
        isinstance(source, dict)
        and source.get("workflow") == "long_serial"
        and source.get("operation") == "rewrite_outline_selection"
    )


def _source_bindings_from_command(
    command: WritingRunCommand,
) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(command.payloadJson)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    job = payload.get("job")
    source = job if isinstance(job, dict) else payload
    raw_bindings = source.get("sourceBindings")
    if not isinstance(raw_bindings, list) or not raw_bindings:
        return None
    try:
        return [
            SourceBinding.model_validate(binding).model_dump(mode="json")
            for binding in raw_bindings
        ]
    except (TypeError, ValueError):
        return None


async def _source_binding_view(
    session: AsyncSession, artifact: ReviewArtifact
) -> tuple[list[dict[str, Any]] | None, SourceBindingStatus]:
    if not await _artifact_requires_source_bindings(session, artifact):
        return None, "not_yet_supported"
    payload = _parse_json(artifact.payloadJson, {})
    control = payload.get("_inkforgeControl") if isinstance(payload, dict) else None
    source_command_id = control.get("sourceCommandId") if isinstance(control, dict) else None
    if not isinstance(source_command_id, str) or not source_command_id or artifact.taskId is None:
        return None, "legacy_missing"
    command = await session.scalar(
        select(WritingRunCommand).where(
            WritingRunCommand.id == source_command_id,
            WritingRunCommand.taskId == artifact.taskId,
            WritingRunCommand.kind == "start",
        )
    )
    if command is None:
        return None, "legacy_missing"
    bindings = _source_bindings_from_command(command)
    return (bindings, "verified") if bindings is not None else (None, "legacy_missing")


async def _source_binding_views(
    session: AsyncSession, artifacts: list[ReviewArtifact]
) -> dict[str, tuple[list[dict[str, Any]] | None, SourceBindingStatus]]:
    source_ids: dict[str, str] = {}
    views: dict[str, tuple[list[dict[str, Any]] | None, SourceBindingStatus]] = {}
    for artifact in artifacts:
        if not await _artifact_requires_source_bindings(session, artifact):
            views[artifact.id] = (None, "not_yet_supported")
            continue
        payload = _parse_json(artifact.payloadJson, {})
        control = payload.get("_inkforgeControl") if isinstance(payload, dict) else None
        source_command_id = (
            control.get("sourceCommandId") if isinstance(control, dict) else None
        )
        if (
            not isinstance(source_command_id, str)
            or not source_command_id
            or artifact.taskId is None
        ):
            views[artifact.id] = (None, "legacy_missing")
            continue
        source_ids[artifact.id] = source_command_id
    if not source_ids:
        return views
    commands = list(
        (
            await session.scalars(
                select(WritingRunCommand).where(WritingRunCommand.id.in_(set(source_ids.values())))
            )
        ).all()
    )
    commands_by_id = {command.id: command for command in commands}
    for artifact in artifacts:
        source_command_id = source_ids.get(artifact.id)
        if source_command_id is None:
            continue
        command = commands_by_id.get(source_command_id)
        if command is None or command.taskId != artifact.taskId or command.kind != "start":
            views[artifact.id] = (None, "legacy_missing")
            continue
        bindings = _source_bindings_from_command(command)
        views[artifact.id] = (
            (bindings, "verified") if bindings is not None else (None, "legacy_missing")
        )
    return views


def _encode_cursor(artifact: ReviewArtifact) -> str:
    payload = json.dumps(
        {"createdAt": artifact.createdAt.isoformat(), "id": artifact.id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded))
        created_at = datetime.fromisoformat(value["createdAt"])
        artifact_id = value["id"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ApiError(
            status_code=422,
            code="REVIEW_ARTIFACT_CURSOR_INVALID",
            message="待审核草案分页游标无效",
        ) from exc
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ApiError(
            status_code=422,
            code="REVIEW_ARTIFACT_CURSOR_INVALID",
            message="待审核草案分页游标无效",
        )
    return created_at, artifact_id


def _parse_json(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_PAYLOAD_INVALID",
            message="待审核草案持久化内容格式错误",
        ) from None


def _record(artifact: ReviewArtifact) -> ArtifactRecord:
    payload = _parse_json(artifact.payloadJson, {})
    if not isinstance(payload, dict) or payload.get("kind") != artifact.kind:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_PAYLOAD_INVALID",
            message="待审核草案类型与持久化内容不一致",
        )
    return ArtifactRecord(
        id=artifact.id,
        novel_id=artifact.novelId,
        chapter_id=artifact.chapterId,
        task_id=artifact.taskId,
        workflow_run_id=artifact.workflowRunId,
        artifact_key=artifact.artifactKey,
        kind=artifact.kind,
        status=artifact.status,
        title=artifact.title,
        summary=artifact.summary,
        payload=payload,
        diff=_parse_json(artifact.diffJson, None),
        created_by_agent=artifact.createdByAgent,
        updated_by_agent=artifact.updatedByAgent,
        reviewer_agent=artifact.reviewerAgent,
        revision=artifact.revision,
        created_at=artifact.createdAt,
        updated_at=artifact.updatedAt,
    )


def _response(
    artifact: ReviewArtifact,
    evaluations: list[ReviewArtifactEvaluation],
    *,
    source_bindings: list[dict[str, Any]] | None = None,
    source_binding_status: SourceBindingStatus | None = None,
) -> ReviewArtifactResponse:
    record = _record(artifact)
    payload = dict(record.payload)
    payload.pop("_inkforgeControl", None)
    if source_binding_status is None:
        source_binding_status = (
            "legacy_missing"
            if record.kind in _SOURCE_BOUND_KINDS
            else "not_yet_supported"
        )
    return ReviewArtifactResponse(
        id=record.id,
        novelId=record.novel_id,
        chapterId=record.chapter_id,
        taskId=record.task_id,
        workflowRunId=record.workflow_run_id,
        artifactKey=record.artifact_key,
        kind=cast(ArtifactKind, record.kind),
        status=cast(ArtifactStatus, record.status),
        title=record.title,
        summary=record.summary,
        payload=payload,
        diff=record.diff,
        createdByAgent=record.created_by_agent,
        updatedByAgent=record.updated_by_agent,
        reviewerAgent=record.reviewer_agent,
        revision=record.revision,
        evaluations=[
            ArtifactEvaluationResponse(
                id=item.id,
                artifactId=item.artifactId,
                revision=item.revision,
                evaluatorAgent=item.evaluatorAgent,
                verdict=cast(EvaluationVerdict, item.verdict),
                summary=item.summary,
                requiredChanges=item.requiredChanges,
                createdAt=item.createdAt,
            )
            for item in evaluations
        ],
        sourceBindings=(
            [SourceBinding.model_validate(item) for item in source_bindings]
            if source_bindings is not None
            else None
        ),
        sourceBindingStatus=source_binding_status,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )

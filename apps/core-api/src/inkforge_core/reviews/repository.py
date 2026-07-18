from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from inkforge_contracts import ShortStoryOutlineDraft
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Novel,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    ReviewArtifactRevision,
    WritingBible,
    WritingTask,
)
from ..errors import ApiError
from .schemas import (
    ArtifactEvaluationResponse,
    ArtifactKind,
    ArtifactStatus,
    CreateArtifactRequest,
    EvaluationVerdict,
    ReviewArtifactResponse,
    ReviewArtifactRevisionDetail,
    ReviewArtifactRevisionSummary,
    SaveShortStoryOutlineRequest,
    SubmitArtifactEvaluationRequest,
    assert_status_transition,
)


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

    async def require_artifact_revision(
        self,
        user_id: str,
        artifact_id: str,
        expected_revision: int,
    ) -> ArtifactRecord:
        async with self._session_factory() as session:
            async with session.begin():
                artifact = await _lock_owned_artifact(session, user_id, artifact_id)
                _assert_expected_revision(artifact, expected_revision)
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
            return _response(artifact, list(evaluations))

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
            return _response(artifact, list(evaluations))

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
                await session.execute(
                    delete(ReviewArtifact).where(ReviewArtifact.id == artifact_id)
                )

    async def create_or_revise(
        self, user_id: str, request: CreateArtifactRequest
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
                if task is None or (
                    request.chapterId is not None and task.chapterId != request.chapterId
                ):
                    raise ApiError(
                        status_code=403,
                        code="ARTIFACT_TASK_MISMATCH",
                        message="待审核草案与写作任务资源不匹配",
                    )
                profile = await session.scalar(
                    select(WritingBible.storyLengthProfile).where(
                        WritingBible.novelId == request.novelId
                    )
                )
                payload = _validate_payload_for_profile(
                    profile,
                    request.kind,
                    _payload_dict(request.payload),
                )
                existing: ReviewArtifact | None = None
                if request.artifactKey is not None:
                    existing = await session.scalar(
                        select(ReviewArtifact)
                        .where(
                            ReviewArtifact.novelId == request.novelId,
                            ReviewArtifact.taskId == request.taskId,
                            ReviewArtifact.artifactKey == request.artifactKey,
                        )
                        .order_by(ReviewArtifact.createdAt.desc(), ReviewArtifact.id.desc())
                        .limit(1)
                        .with_for_update()
                    )
                payload_json = _dump_json(payload)
                diff_json = _dump_json(request.diff) if request.diff is not None else None
                content_changed = False
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
                    existing_payload = _parse_json(existing.payloadJson, {})
                    if profile == "short_medium" and request.kind == "outline_draft":
                        existing_outline = _parse_short_outline(existing.payloadJson)
                        target_outline = ShortStoryOutlineDraft.model_validate(payload)
                        content_changed = (
                            existing_outline.semantic_content_signature()
                            != target_outline.semantic_content_signature()
                        )
                    else:
                        content_changed = (
                            existing.title != request.title
                            or existing.summary != request.summary
                            or existing_payload != payload
                        )
                    if content_changed:
                        if request.expectedRevision is None:
                            raise ApiError(
                                status_code=409,
                                code="ARTIFACT_EXPECTED_REVISION_REQUIRED",
                                message="修改草案内容时必须提供当前修订号",
                            )
                        _assert_expected_revision(existing, request.expectedRevision)
                        _assert_transition(existing.status, request.status)
                        existing.status = request.status
                        existing.title = request.title
                        existing.summary = request.summary
                        existing.payloadJson = payload_json
                        existing.diffJson = diff_json
                        existing.revision += 1
                    else:
                        existing.status = _non_regressive_callback_status(
                            existing.status, request.status
                        )
                    existing.updatedByAgent = request.createdByAgent
                    existing.reviewerAgent = request.reviewerAgent
                    artifact = existing
                if existing is None or content_changed:
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

    async def list_revisions(
        self, user_id: str, artifact_id: str
    ) -> list[ReviewArtifactRevisionSummary]:
        async with self._session_factory() as session:
            await _require_short_outline(session, user_id, artifact_id)
            revisions = list(
                (
                    await session.scalars(
                        select(ReviewArtifactRevision)
                        .where(ReviewArtifactRevision.artifactId == artifact_id)
                        .order_by(ReviewArtifactRevision.revision.desc())
                    )
                ).all()
            )
        return [_revision_summary(item) for item in revisions]

    async def get_revision(
        self, user_id: str, artifact_id: str, revision: int
    ) -> ReviewArtifactRevisionDetail:
        async with self._session_factory() as session:
            await _require_short_outline(session, user_id, artifact_id)
            record = await session.scalar(
                select(ReviewArtifactRevision).where(
                    ReviewArtifactRevision.artifactId == artifact_id,
                    ReviewArtifactRevision.revision == revision,
                )
            )
            if record is None:
                raise ApiError(
                    status_code=404,
                    code="ARTIFACT_REVISION_NOT_FOUND",
                    message="待审核草案版本不存在",
                )
            return _revision_detail(record)

    async def save_short_story_outline(
        self,
        user_id: str,
        artifact_id: str,
        request: SaveShortStoryOutlineRequest,
    ) -> ReviewArtifactResponse:
        async with self._session_factory() as session:
            async with session.begin():
                artifact = await _lock_short_outline(session, user_id, artifact_id)
                _assert_short_outline_editable(artifact)
                current = _parse_short_outline(artifact.payloadJson)
                current_section_ids = {item.id for item in current.sections}
                unknown_section_ids = {
                    item.id
                    for item in request.sections
                    if item.id is not None and item.id not in current_section_ids
                }
                if unknown_section_ids:
                    raise ApiError(
                        status_code=422,
                        code="SHORT_OUTLINE_SECTION_ID_UNKNOWN",
                        message="中短篇大纲包含不属于当前版本的分节 ID",
                    )
                sections = [
                    {
                        "id": item.id
                        or _deterministic_section_id(
                            artifact_id,
                            request.expectedRevision,
                            index,
                            item.title,
                            item.events,
                        ),
                        "title": item.title,
                        "events": item.events,
                    }
                    for index, item in enumerate(request.sections)
                ]
                try:
                    target = ShortStoryOutlineDraft.model_validate(
                        {
                            "kind": "outline_draft",
                            "storyLengthProfile": "short_medium",
                            "originalInspiration": current.originalInspiration,
                            "corePremise": request.corePremise,
                            "anchors": request.anchors,
                            "sections": sections,
                            "content": "",
                            "changeSummary": request.changeSummary,
                            "anchorChanges": request.anchorChanges,
                        }
                    )
                except ValidationError as exc:
                    raise ApiError(
                        status_code=422,
                        code="SHORT_OUTLINE_INVALID",
                        message="中短篇大纲结构无效",
                    ) from exc
                target_payload = target.model_dump(mode="json")
                if (
                    current.semantic_content_signature()
                    == target.semantic_content_signature()
                ):
                    return _response(artifact, [])
                _assert_expected_revision(artifact, request.expectedRevision)
                artifact.payloadJson = _dump_json(target_payload)
                artifact.summary = request.changeSummary or artifact.summary
                artifact.diffJson = _dump_json(
                    {
                        "type": "user_edit",
                        "sourceRevision": request.expectedRevision,
                    }
                )
                artifact.updatedByAgent = None
                artifact.revision += 1
                session.add(
                    ReviewArtifactRevision(
                        artifactId=artifact.id,
                        revision=artifact.revision,
                        summary=artifact.summary,
                        payloadJson=artifact.payloadJson,
                        diffJson=artifact.diffJson,
                        createdByAgent=None,
                    )
                )
        return await self.get_response(user_id, artifact_id)

    async def restore_revision(
        self,
        user_id: str,
        artifact_id: str,
        revision: int,
        *,
        expected_revision: int,
    ) -> ReviewArtifactResponse:
        async with self._session_factory() as session:
            async with session.begin():
                artifact = await _lock_short_outline(session, user_id, artifact_id)
                _assert_short_outline_editable(artifact)
                source = await session.scalar(
                    select(ReviewArtifactRevision).where(
                        ReviewArtifactRevision.artifactId == artifact_id,
                        ReviewArtifactRevision.revision == revision,
                    )
                )
                if source is None:
                    raise ApiError(
                        status_code=404,
                        code="ARTIFACT_REVISION_NOT_FOUND",
                        message="待审核草案版本不存在",
                    )
                source_outline = _parse_short_outline(source.payloadJson)
                source_payload = source_outline.model_dump(mode="json")
                current = _parse_short_outline(artifact.payloadJson)
                if (
                    current.semantic_content_signature()
                    == source_outline.semantic_content_signature()
                ):
                    return _response(artifact, [])
                _assert_expected_revision(artifact, expected_revision)
                artifact.payloadJson = _dump_json(source_payload)
                artifact.summary = source.summary
                artifact.diffJson = _dump_json(
                    {
                        "type": "restore",
                        "sourceRevision": revision,
                        "sourceDiff": _parse_json(source.diffJson, None),
                    }
                )
                artifact.updatedByAgent = None
                artifact.revision += 1
                session.add(
                    ReviewArtifactRevision(
                        artifactId=artifact.id,
                        revision=artifact.revision,
                        summary=artifact.summary,
                        payloadJson=artifact.payloadJson,
                        diffJson=artifact.diffJson,
                        createdByAgent=None,
                    )
                )
        return await self.get_response(user_id, artifact_id)

    async def submit_evaluation(
        self,
        user_id: str,
        artifact_id: str,
        request: SubmitArtifactEvaluationRequest,
    ) -> ReviewArtifactResponse:
        async with self._session_factory() as session:
            async with session.begin():
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


def _payload_dict(payload: object) -> dict[str, Any]:
    if isinstance(payload, ShortStoryOutlineDraft):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return payload
    raise TypeError("草案载荷必须是对象")


def _validate_payload_for_profile(
    profile: str | None,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if kind != "outline_draft":
        return payload
    if profile == "short_medium":
        try:
            return ShortStoryOutlineDraft.model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            raise ApiError(
                status_code=422,
                code="SHORT_OUTLINE_PAYLOAD_INVALID",
                message="中短篇作品只能保存强类型完整大纲",
            ) from exc
    if payload.get("storyLengthProfile") == "short_medium":
        raise ApiError(
            status_code=409,
            code="ARTIFACT_PROFILE_MISMATCH",
            message="中短篇大纲不能写入长篇作品",
        )
    return payload


def _dump_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _assert_expected_revision(artifact: ReviewArtifact, expected_revision: int) -> None:
    if artifact.revision != expected_revision:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_REVISION_CONFLICT",
            message="待审核草案修订号已过期",
        )


def _assert_transition(current: str, target: str) -> None:
    try:
        assert_status_transition(current, target)
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_STATUS_CONFLICT",
            message=str(exc),
        ) from exc


def _non_regressive_callback_status(current: str, requested: str) -> str:
    order = {
        "draft": 0,
        "under_review": 1,
        "awaiting_user": 2,
        "applying": 3,
        "applied": 4,
    }
    if order.get(requested, -1) < order.get(current, -1):
        return current
    _assert_transition(current, requested)
    return requested


def _deterministic_section_id(
    artifact_id: str,
    expected_revision: int,
    index: int,
    title: str,
    events: str,
) -> str:
    source = f"{artifact_id}\0{expected_revision}\0{index}\0{title.strip()}\0{events.strip()}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]
    return f"short-section-{digest}"


def _assert_short_outline_editable(artifact: ReviewArtifact) -> None:
    if artifact.status != "awaiting_user":
        raise ApiError(
            status_code=409,
            code="SHORT_OUTLINE_NOT_AWAITING_USER",
            message="只有等待用户确认的中短篇大纲可以直接编辑或恢复",
        )


def _parse_short_outline(payload_json: str) -> ShortStoryOutlineDraft:
    try:
        return ShortStoryOutlineDraft.model_validate(_parse_json(payload_json, {}))
    except ValidationError as exc:
        raise ApiError(
            status_code=409,
            code="SHORT_OUTLINE_PAYLOAD_INVALID",
            message="中短篇大纲持久化内容不符合强类型契约",
        ) from exc


async def _require_short_outline(
    session: AsyncSession,
    user_id: str,
    artifact_id: str,
) -> ReviewArtifact:
    owned = await _owned_artifact(session, user_id, artifact_id)
    if owned is None:
        raise ApiError(
            status_code=403,
            code="REVIEW_ARTIFACT_FORBIDDEN",
            message="无权访问该待审核草案",
        )
    profile = await session.scalar(
        select(WritingBible.storyLengthProfile).where(WritingBible.novelId == owned.novelId)
    )
    if (
        profile != "short_medium"
        or owned.kind != "outline_draft"
        or _parse_json(owned.payloadJson, {}).get("storyLengthProfile") != "short_medium"
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_OUTLINE_REQUIRED",
            message="该接口只支持中短篇大纲草案",
        )
    _parse_short_outline(owned.payloadJson)
    return owned


async def _lock_short_outline(
    session: AsyncSession,
    user_id: str,
    artifact_id: str,
) -> ReviewArtifact:
    owned = await _owned_artifact(session, user_id, artifact_id)
    if owned is None:
        raise ApiError(
            status_code=403,
            code="REVIEW_ARTIFACT_FORBIDDEN",
            message="无权访问该待审核草案",
        )
    if owned.taskId is None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_TASK_MISSING",
            message="中短篇大纲没有关联写作任务",
        )
    task_id = await session.scalar(
        select(WritingTask.id).where(WritingTask.id == owned.taskId).with_for_update()
    )
    if task_id is None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_TASK_MISSING",
            message="中短篇大纲关联写作任务不存在",
        )
    artifact = await session.scalar(
        select(ReviewArtifact)
        .join(WritingBible, WritingBible.novelId == ReviewArtifact.novelId)
        .where(
            ReviewArtifact.id == artifact_id,
            ReviewArtifact.kind == "outline_draft",
            WritingBible.storyLengthProfile == "short_medium",
        )
        .with_for_update()
    )
    if artifact is None:
        raise ApiError(
            status_code=409,
            code="SHORT_OUTLINE_REQUIRED",
            message="该接口只支持中短篇大纲草案",
        )
    _parse_short_outline(artifact.payloadJson)
    return artifact


async def _lock_owned_artifact(
    session: AsyncSession,
    user_id: str,
    artifact_id: str,
) -> ReviewArtifact:
    owned = await _owned_artifact(session, user_id, artifact_id)
    if owned is None:
        raise ApiError(
            status_code=403,
            code="REVIEW_ARTIFACT_FORBIDDEN",
            message="无权访问该待审核草案",
        )
    if owned.taskId is not None:
        task_id = await session.scalar(
            select(WritingTask.id).where(WritingTask.id == owned.taskId).with_for_update()
        )
        if task_id is None:
            raise ApiError(
                status_code=409,
                code="ARTIFACT_TASK_MISSING",
                message="待审核草案关联写作任务不存在",
            )
    artifact = await session.scalar(
        select(ReviewArtifact)
        .join(Novel, Novel.id == ReviewArtifact.novelId)
        .where(
            ReviewArtifact.id == artifact_id,
            Novel.userId == user_id,
        )
        .with_for_update()
    )
    if artifact is None:
        raise ApiError(
            status_code=409,
            code="ARTIFACT_CHANGED_DURING_DECISION",
            message="待审核草案在决定受理前已发生变化",
        )
    return artifact


def _revision_summary(record: ReviewArtifactRevision) -> ReviewArtifactRevisionSummary:
    return ReviewArtifactRevisionSummary(
        artifactId=record.artifactId,
        revision=record.revision,
        summary=record.summary,
        createdByAgent=record.createdByAgent,
        createdAt=record.createdAt,
    )


def _revision_detail(record: ReviewArtifactRevision) -> ReviewArtifactRevisionDetail:
    summary = _revision_summary(record)
    return ReviewArtifactRevisionDetail(
        **summary.model_dump(),
        payload=_typed_payload(_parse_json(record.payloadJson, {})),
        diff=_parse_json(record.diffJson, None),
    )


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
    artifact: ReviewArtifact, evaluations: list[ReviewArtifactEvaluation]
) -> ReviewArtifactResponse:
    record = _record(artifact)
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
        payload=_typed_payload(record.payload),
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
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def _typed_payload(payload: dict[str, Any]) -> ShortStoryOutlineDraft | dict[str, Any]:
    if (
        payload.get("kind") == "outline_draft"
        and payload.get("storyLengthProfile") == "short_medium"
    ):
        try:
            return ShortStoryOutlineDraft.model_validate(payload)
        except ValidationError as exc:
            raise ApiError(
                status_code=409,
                code="SHORT_OUTLINE_PAYLOAD_INVALID",
                message="中短篇大纲持久化内容不符合强类型契约",
            ) from exc
    return payload

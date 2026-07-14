from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.base import utc_now
from ..db.models import (
    Novel,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    ReviewArtifactRevision,
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
                )
                if task is None or (
                    request.chapterId is not None and task.chapterId != request.chapterId
                ):
                    raise ApiError(
                        status_code=403,
                        code="ARTIFACT_TASK_MISMATCH",
                        message="待审核草案与写作任务资源不匹配",
                    )
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
                payload_json = json.dumps(request.payload, ensure_ascii=False)
                diff_json = (
                    json.dumps(request.diff, ensure_ascii=False)
                    if request.diff is not None
                    else None
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
        payload=record.payload,
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

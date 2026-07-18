from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from inkforge_contracts import (
    ShortStoryChapterDraft,
    ShortStoryOutlineDraft,
    canonical_short_outline_hash,
    count_short_story_text_length,
)
from inkforge_contracts.jobs import ApprovedShortOutlineSource, WritingJobPayload
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..chapters.content_state import content_sha256
from ..db.base import utc_now
from ..db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    ReviewArtifactEvaluation,
    ReviewArtifactRevision,
    WritingBible,
    WritingRunCommand,
    WritingSession,
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
    ShortStoryArtifactResponse,
    ShortStoryArtifactsResponse,
    ShortStoryTaskStatus,
    ShortStoryWorkflowSession,
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

    async def get_short_story_artifacts(
        self,
        user_id: str,
        novel_id: str,
    ) -> ShortStoryArtifactsResponse:
        """返回中短篇工作区刷新所需的单一权威读模型。"""

        async with self._session_factory() as session:
            bible = await session.scalar(
                select(WritingBible)
                .join(Novel, Novel.id == WritingBible.novelId)
                .where(
                    WritingBible.novelId == novel_id,
                    Novel.userId == user_id,
                )
            )
            if bible is None:
                raise ApiError(
                    status_code=403,
                    code="NOVEL_FORBIDDEN",
                    message="无权访问该小说",
                )
            if bible.storyLengthProfile != "short_medium":
                raise ApiError(
                    status_code=409,
                    code="SHORT_STORY_PROFILE_REQUIRED",
                    message="该接口只支持中短篇作品",
                )
            outline = await _latest_short_story_artifact_by_kind(
                session, novel_id, "outline_draft"
            )
            chapter_draft = await _latest_short_story_artifact_by_kind(
                session, novel_id, "chapter_draft"
            )
            outline_response = (
                await _short_story_artifact_response(session, outline)
                if outline is not None
                else None
            )
            draft_response = (
                await _short_story_artifact_response(session, chapter_draft)
                if chapter_draft is not None
                else None
            )
            tasks = list(
                (
                    await session.scalars(
                        select(WritingTask)
                        .where(WritingTask.novelId == novel_id)
                        .order_by(WritingTask.updatedAt.desc(), WritingTask.id.desc())
                    )
                ).all()
            )
            summaries: list[tuple[WritingTask, ShortStoryTaskStatus]] = []
            for task in tasks:
                command = await session.scalar(
                    select(WritingRunCommand)
                    .where(WritingRunCommand.taskId == task.id)
                    .order_by(
                        WritingRunCommand.createdAt.desc(),
                        WritingRunCommand.id.desc(),
                    )
                    .limit(1)
                )
                if command is None:
                    continue
                try:
                    payload = _parse_writing_job_payload(command.payloadJson)
                except ApiError:
                    continue
                if (
                    payload.workflowKind != "short_medium"
                    or payload.operation not in {
                        "develop_short_outline",
                        "write_short_story",
                    }
                ):
                    continue
                active_artifact_id = _task_active_artifact_id(task)
                if active_artifact_id is None and command.artifactId is not None:
                    active_artifact_id = command.artifactId
                if active_artifact_id is None:
                    for candidate in (chapter_draft, outline):
                        if (
                            candidate is not None
                            and candidate.taskId == task.id
                            and candidate.status
                            in {"draft", "under_review", "awaiting_user", "applying"}
                        ):
                            active_artifact_id = candidate.id
                            break
                summaries.append(
                    (
                        task,
                        ShortStoryTaskStatus(
                            id=task.id,
                            phase=task.phase,
                            operation=cast(Any, payload.operation),
                            activeArtifactId=active_artifact_id,
                            latestCommandId=command.id,
                            latestCommandStatus=cast(Any, command.status),
                            updatedAt=task.updatedAt,
                        ),
                    )
                )

            recoverable_phases = {"active", "waiting_call", "awaiting_user_review"}
            preferred = next(
                (
                    item
                    for item in summaries
                    if item[0].phase in recoverable_phases
                    or item[1].latestCommandStatus
                    in {"pending", "submitted", "processing"}
                ),
                summaries[0] if summaries else None,
            )
            latest_task = preferred[1] if preferred is not None else None
            workflow_session = None
            if preferred is not None and preferred[0].writingSessionId is not None:
                session_record = await session.scalar(
                    select(WritingSession).where(
                        WritingSession.id == preferred[0].writingSessionId,
                        WritingSession.novelId == novel_id,
                    )
                )
                if session_record is not None:
                    session_summaries = [
                        summary
                        for task, summary in summaries
                        if task.writingSessionId == session_record.id
                    ]
                    current = next(
                        (
                            item
                            for item in session_summaries
                            if item.phase in recoverable_phases
                            or item.latestCommandStatus
                            in {"pending", "submitted", "processing"}
                        ),
                        None,
                    )
                    last = next(
                        (
                            item
                            for item in session_summaries
                            if item.phase in {"completed", "error"}
                            and item is not current
                        ),
                        None,
                    )
                    workflow_session = ShortStoryWorkflowSession(
                        id=session_record.id,
                        phase=session_record.phase,
                        currentTask=current,
                        lastTask=last,
                    )
            return ShortStoryArtifactsResponse(
                outline=outline_response,
                chapterDraft=draft_response,
                latestTask=latest_task,
                workflowSession=workflow_session,
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
                if profile == "short_medium" and request.kind == "chapter_draft":
                    await _validate_short_story_draft_submission(
                        session,
                        task=task,
                        request=request,
                        payload=ShortStoryChapterDraft.model_validate(payload),
                        existing=existing,
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
                if (
                    profile == "short_medium"
                    and request.kind == "chapter_draft"
                    and request.status == "awaiting_user"
                ):
                    await _require_short_story_dual_review(
                        session,
                        artifact_id=artifact.id,
                        revision=artifact.revision,
                        error_code="SHORT_STORY_REVIEWS_INCOMPLETE",
                        message="中短篇正文必须完成编辑和校验两份全稿审核后才能交给用户",
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
                profile = await session.scalar(
                    select(WritingBible.storyLengthProfile).where(
                        WritingBible.novelId == artifact.novelId
                    )
                )
                is_short_story_draft = (
                    profile == "short_medium"
                    and artifact.kind == "chapter_draft"
                    and _parse_json(artifact.payloadJson, {}).get("storyLengthProfile")
                    == "short_medium"
                )
                if is_short_story_draft:
                    _parse_short_story_draft(artifact.payloadJson)
                    if request.evaluatorAgent not in {"编辑", "校验"}:
                        raise ApiError(
                            status_code=409,
                            code="SHORT_STORY_REVIEWER_INVALID",
                            message="中短篇全稿只接受编辑和校验审核",
                        )
                    if request.evaluatorAgent == "校验":
                        editor = await session.scalar(
                            select(ReviewArtifactEvaluation.id).where(
                                ReviewArtifactEvaluation.artifactId == artifact_id,
                                ReviewArtifactEvaluation.revision == request.revision,
                                ReviewArtifactEvaluation.evaluatorAgent == "编辑",
                            )
                        )
                        if editor is None:
                            raise ApiError(
                                status_code=409,
                                code="SHORT_STORY_EDITOR_REVIEW_REQUIRED",
                                message="中短篇全稿必须先完成编辑审核，再提交校验结论",
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
    if isinstance(payload, (ShortStoryOutlineDraft, ShortStoryChapterDraft)):
        return payload.model_dump(mode="json")
    if isinstance(payload, dict):
        return payload
    raise TypeError("草案载荷必须是对象")


def _validate_payload_for_profile(
    profile: str | None,
    kind: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if kind == "chapter_draft":
        if profile == "short_medium":
            try:
                return ShortStoryChapterDraft.model_validate(payload).model_dump(mode="json")
            except ValidationError as exc:
                raise ApiError(
                    status_code=422,
                    code="SHORT_STORY_DRAFT_PAYLOAD_INVALID",
                    message="中短篇作品只能保存强类型完整正文",
                ) from exc
        if payload.get("storyLengthProfile") == "short_medium":
            raise ApiError(
                status_code=409,
                code="ARTIFACT_PROFILE_MISMATCH",
                message="中短篇正文不能写入长篇作品",
            )
        return payload
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


async def _validate_short_story_draft_submission(
    session: AsyncSession,
    *,
    task: WritingTask,
    request: CreateArtifactRequest,
    payload: ShortStoryChapterDraft,
    existing: ReviewArtifact | None,
) -> None:
    """在持久化前重新核对中短篇整稿的全部权威来源。"""

    bible = await session.scalar(
        select(WritingBible)
        .where(WritingBible.novelId == request.novelId)
        .with_for_update()
    )
    if (
        bible is None
        or bible.storyLengthProfile != "short_medium"
        or bible.targetTotalWordCount is None
        or not 6_000 <= bible.targetTotalWordCount <= 80_000
        or task.targetWordCount != bible.targetTotalWordCount
        or payload.metadata.targetWordCount != bible.targetTotalWordCount
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_TARGET_MISMATCH",
            message="中短篇正文目标字数与作品圣经不一致",
        )
    chapters = list(
        (
            await session.scalars(
                select(Chapter)
                .where(Chapter.novelId == request.novelId)
                .order_by(Chapter.order, Chapter.id)
                .with_for_update()
            )
        ).all()
    )
    if len(chapters) != 1:
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_CHAPTER_INVALID",
            message="中短篇必须使用小说创建时的唯一正文承载章节",
        )
    chapter = chapters[0]
    if (
        request.chapterId != chapter.id
        or task.chapterId != chapter.id
        or payload.metadata.targetChapterId != chapter.id
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_TARGET_CHAPTER_MISMATCH",
            message="中短篇正文目标章节与唯一正文承载章节不一致",
        )
    if payload.metadata.baseChapterHash != content_sha256(chapter.content):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_CHAPTER_BASE_CHANGED",
            message="中短篇正式正文基线已经变化，请重新生成整稿",
        )
    actual_count = count_short_story_text_length(payload.content)
    if (
        payload.metadata.actualWordCount != actual_count
        or not 6_000 <= actual_count <= 80_000
    ):
        raise ApiError(
            status_code=422,
            code="SHORT_STORY_ACTUAL_WORD_COUNT_INVALID",
            message="中短篇正文实际字数必须为 6000～80000，且与元数据一致",
        )

    command = await session.scalar(
        select(WritingRunCommand)
        .where(
            WritingRunCommand.taskId == task.id,
            WritingRunCommand.status.in_(("pending", "submitted", "processing")),
        )
        .order_by(WritingRunCommand.createdAt.desc(), WritingRunCommand.id.desc())
        .limit(1)
        .with_for_update()
    )
    if command is None or command.id != payload.metadata.generationCommandId:
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_COMMAND_MISMATCH",
            message="中短篇正文生成命令与当前活动命令不一致",
        )
    command_payload = _parse_writing_job_payload(command.payloadJson)
    source = command_payload.source
    if (
        command_payload.workflowKind != "short_medium"
        or command_payload.operation != "write_short_story"
        or command_payload.targetTotalWordCount != bible.targetTotalWordCount
        or not isinstance(source, ApprovedShortOutlineSource)
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_COMMAND_MISMATCH",
            message="当前活动命令不是同一中短篇整稿流程",
        )

    latest_outline = await session.scalar(
        select(ReviewArtifact)
        .where(
            ReviewArtifact.novelId == request.novelId,
            ReviewArtifact.kind == "outline_draft",
        )
        .order_by(ReviewArtifact.updatedAt.desc(), ReviewArtifact.id.desc())
        .limit(1)
        .with_for_update()
    )
    if (
        latest_outline is None
        or latest_outline.status != "applied"
        or latest_outline.id != source.outlineArtifactId
        or latest_outline.revision != source.outlineRevision
        or payload.metadata.sourceOutlineArtifactId != source.outlineArtifactId
        or payload.metadata.sourceOutlineRevision != source.outlineRevision
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_OUTLINE_SOURCE_CHANGED",
            message="中短篇正文来源大纲已经变化，请重新生成整稿",
        )
    outline = _parse_short_outline(latest_outline.payloadJson)
    authoritative_hash = canonical_short_outline_hash(outline)
    if (
        source.outlineHash != authoritative_hash
        or payload.metadata.sourceOutlineHash != authoritative_hash
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_OUTLINE_SOURCE_CHANGED",
            message="中短篇正文来源大纲哈希已经变化，请重新生成整稿",
        )

    metadata = payload.metadata
    if existing is None:
        if metadata.automaticRewriteCount != 0 or metadata.generationReason != "user_request":
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_INITIAL_GENERATION_INVALID",
                message="中短篇首版正文必须由当前用户请求生成",
            )
        return

    current = _parse_short_story_draft(existing.payloadJson)
    if metadata.generationCommandId == current.metadata.generationCommandId:
        if payload == current:
            return
        if not (
            current.metadata.automaticRewriteCount == 0
            and metadata.automaticRewriteCount == 1
            and metadata.generationReason == "automatic_rewrite"
        ):
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_AUTOMATIC_REWRITE_LIMIT",
                message="同一用户请求最多自动完整返工一次",
            )
        await _require_short_story_dual_review(
            session,
            artifact_id=existing.id,
            revision=existing.revision,
            error_code="SHORT_STORY_AUTOMATIC_REWRITE_REVIEW_REQUIRED",
            message="首版正文必须完成编辑和校验审核后才能自动完整返工",
        )
        rewrite_requested = await session.scalar(
            select(ReviewArtifactEvaluation.id)
            .where(
                ReviewArtifactEvaluation.artifactId == existing.id,
                ReviewArtifactEvaluation.revision == existing.revision,
                ReviewArtifactEvaluation.evaluatorAgent.in_(("编辑", "校验")),
                ReviewArtifactEvaluation.verdict.in_(("revise", "block")),
            )
            .limit(1)
        )
        if rewrite_requested is None:
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_AUTOMATIC_REWRITE_NOT_REQUIRED",
                message="首轮双审核均已通过，不能触发自动完整返工",
            )
        return

    if not (
        metadata.automaticRewriteCount == 0
        and metadata.generationReason == "user_request"
        and command.kind == "artifact_decision"
        and command.decision == "revise"
        and command.artifactId == existing.id
    ):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_USER_REVISION_COMMAND_REQUIRED",
            message="新的中短篇整稿版本必须来自用户明确的 revise 决定",
        )


def _parse_writing_job_payload(serialized: str) -> WritingJobPayload:
    try:
        value = json.loads(serialized)
        return WritingJobPayload.model_validate(value)
    except (json.JSONDecodeError, ValidationError, TypeError):
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_COMMAND_MISMATCH",
            message="中短篇正文活动命令身份无效",
        ) from None


async def _require_short_story_dual_review(
    session: AsyncSession,
    *,
    artifact_id: str,
    revision: int,
    error_code: str,
    message: str,
) -> None:
    evaluators = set(
        (
            await session.scalars(
                select(ReviewArtifactEvaluation.evaluatorAgent).where(
                    ReviewArtifactEvaluation.artifactId == artifact_id,
                    ReviewArtifactEvaluation.revision == revision,
                    ReviewArtifactEvaluation.evaluatorAgent.in_(("编辑", "校验")),
                )
            )
        ).all()
    )
    if evaluators != {"编辑", "校验"}:
        raise ApiError(status_code=409, code=error_code, message=message)


def _parse_short_story_draft(payload_json: str) -> ShortStoryChapterDraft:
    try:
        return ShortStoryChapterDraft.model_validate(_parse_json(payload_json, {}))
    except ValidationError as exc:
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_DRAFT_PAYLOAD_INVALID",
            message="中短篇正文持久化内容不符合强类型契约",
        ) from exc


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


def _typed_payload(
    payload: dict[str, Any],
) -> ShortStoryOutlineDraft | ShortStoryChapterDraft | dict[str, Any]:
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
    if (
        payload.get("kind") == "chapter_draft"
        and payload.get("storyLengthProfile") == "short_medium"
    ):
        try:
            return ShortStoryChapterDraft.model_validate(payload)
        except ValidationError as exc:
            raise ApiError(
                status_code=409,
                code="SHORT_STORY_DRAFT_PAYLOAD_INVALID",
                message="中短篇正文持久化内容不符合强类型契约",
            ) from exc
    return payload


async def _latest_short_story_artifact_by_kind(
    session: AsyncSession,
    novel_id: str,
    kind: str,
) -> ReviewArtifact | None:
    candidates = list(
        (
            await session.scalars(
                select(ReviewArtifact)
                .where(
                    ReviewArtifact.novelId == novel_id,
                    ReviewArtifact.kind == kind,
                )
                .order_by(ReviewArtifact.updatedAt.desc(), ReviewArtifact.id.desc())
            )
        ).all()
    )
    for artifact in candidates:
        payload = _parse_json(artifact.payloadJson, {})
        if (
            isinstance(payload, dict)
            and payload.get("storyLengthProfile") == "short_medium"
        ):
            return artifact
    return None


async def _short_story_artifact_response(
    session: AsyncSession,
    artifact: ReviewArtifact,
) -> ShortStoryArtifactResponse:
    evaluations = list(
        (
            await session.scalars(
                select(ReviewArtifactEvaluation)
                .where(
                    ReviewArtifactEvaluation.artifactId == artifact.id,
                    ReviewArtifactEvaluation.revision == artifact.revision,
                )
                .order_by(
                    ReviewArtifactEvaluation.createdAt.desc(),
                    ReviewArtifactEvaluation.id.desc(),
                )
            )
        ).all()
    )
    response = _response(artifact, evaluations)
    try:
        return ShortStoryArtifactResponse.model_validate(response.model_dump())
    except ValidationError as exc:
        raise ApiError(
            status_code=409,
            code="SHORT_STORY_ARTIFACT_INVALID",
            message="中短篇工作区草案载荷无效",
        ) from exc


def _task_active_artifact_id(task: WritingTask) -> str | None:
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

"""章节影视化改编域的 PostgreSQL 事务与耐久任务实现。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, cast

from inkforge_contracts.jobs import AgentJobStatus
from inkforge_contracts.video import AspectRatio
from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterAdaptationPlanJobPayload,
    ChapterAdaptationPromptJobPayload,
    CinematicSceneCandidate,
    CinematicShotCandidate,
    DramaticBeatCandidate,
    DramaticStructureCheckpoint,
    ShotPromptSpecBatch,
    VideoAdaptationCheckpointCallback,
    VideoAdaptationFailureCallback,
    VideoAdaptationJobPayload,
    VideoAdaptationPlanCompletionCallback,
    VideoAdaptationPromptCompletionCallback,
    VideoAdaptationWorkflowProgressQuery,
    VideoAdaptationWorkflowProgressResponse,
    compile_seedance_shot_prompt,
    parse_video_adaptation_job_payload,
)
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db.base import generate_id, utc_now
from ...db.models import (
    Chapter,
    Novel,
    ReviewArtifact,
    VideoAdaptationDecisionCommand,
    VideoAdaptationTask,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoCinematicScene,
    VideoDramaticBeat,
    VideoDramaticBeatSourceAnchor,
    VideoEpisodeBoundary,
    VideoEpisodePlanVersion,
    VideoProject,
    VideoShot,
    VideoShotPlanVersion,
    VideoShotPromptHead,
    VideoShotPromptVersion,
    VideoShotSourceAnchor,
    WritingBible,
)
from ...errors import ApiError
from ..setting_snapshot import build_long_serial_setting_snapshot
from .read_model import (
    candidate_from_formal_plan,
    list_adaptation_responses,
    load_adaptation_response,
)
from .schemas import (
    ChapterAdaptationListResponse,
    ChapterAdaptationResponse,
    ChapterAdaptationTaskResponse,
    ConfirmAdaptationPlanRequest,
    CreateChapterAdaptationRequest,
    DiscardAdaptationCandidateRequest,
    SaveEpisodePlanRequest,
    SaveShotPromptRequest,
    StartPromptRunRequest,
    StartShotPlanRunRequest,
)
from .validation import (
    candidate_json,
    canonical_json_hash,
    validate_episode_boundaries,
    validate_plan_against_source,
)

_ACTIVE_TASK_STATUSES = {"pending", "submitted", "processing"}


@dataclass(frozen=True, slots=True)
class AdaptationTaskAcceptance:
    adaptation_id: str
    task_id: str


@dataclass(frozen=True, slots=True)
class AdaptationTaskDispatch:
    user_id: str
    novel_id: str
    task_id: str
    job_id: str
    payload: VideoAdaptationJobPayload


class VideoAdaptationRepository:
    """只操作章节改编新表；旧 VideoScene 域不进入本仓储。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        dispatch_namespace: str = "default",
    ) -> None:
        self._session_factory = session_factory
        self._job_prefix = f"video-adaptation-{dispatch_namespace}-"

    async def create_adaptation(
        self,
        user_id: str,
        project_id: str,
        request: CreateChapterAdaptationRequest,
    ) -> ChapterAdaptationResponse:
        """冻结完整章节；相同项目、章节和来源哈希幂等复用同一活动根。"""

        # 来源唯一约束承担创建幂等；clientRequestId 仍由公共请求日志记录。
        async with self._session_factory() as session:
            async with session.begin():
                project = await _require_owned_project(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    lock=True,
                )
                await _require_long_serial(session, project.novelId, lock=True)
                chapter = await session.scalar(
                    select(Chapter)
                    .where(
                        Chapter.id == request.chapterId,
                        Chapter.novelId == project.novelId,
                    )
                    .with_for_update()
                )
                if chapter is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_ADAPTATION_CHAPTER_NOT_FOUND",
                        message="章节不存在或不属于当前小说",
                    )
                expected_updated_at = _database_timestamp(request.expectedChapterUpdatedAt)
                if chapter.updatedAt != expected_updated_at:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_SOURCE_CHANGED",
                        message="章节已经变化，请刷新后重新创建改编",
                    )
                source_text = chapter.content
                if not source_text.strip():
                    raise ApiError(
                        status_code=422,
                        code="VIDEO_ADAPTATION_SOURCE_EMPTY",
                        message="章节正文为空，不能创建影视化改编",
                    )
                if len(source_text) > 120_000:
                    raise ApiError(
                        status_code=422,
                        code="VIDEO_ADAPTATION_SOURCE_TOO_LONG",
                        message="单章正文超过 120000 字，当前工作台不能安全处理",
                    )
                source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
                existing = await session.scalar(
                    select(VideoChapterAdaptation).where(
                        VideoChapterAdaptation.projectId == project.id,
                        VideoChapterAdaptation.chapterId == chapter.id,
                        VideoChapterAdaptation.sourceHash == source_hash,
                        VideoChapterAdaptation.lifecycleStatus == "active",
                    )
                )
                if existing is not None:
                    adaptation_id = existing.id
                else:
                    adaptation_id = generate_id()
                    session.add(
                        VideoChapterAdaptation(
                            id=adaptation_id,
                            projectId=project.id,
                            novelId=project.novelId,
                            chapterId=chapter.id,
                            chapterTitle=chapter.title or "未命名章节",
                            chapterUpdatedAt=chapter.updatedAt,
                            sourceText=source_text,
                            sourceHash=source_hash,
                            lifecycleStatus="active",
                        )
                    )
                    session.add(
                        VideoChapterAdaptationHead(
                            adaptationId=adaptation_id,
                            revision=1,
                            updatedAt=utc_now(),
                        )
                    )
        return await self.get_adaptation(user_id, adaptation_id)

    async def get_adaptation(
        self,
        user_id: str,
        adaptation_id: str,
    ) -> ChapterAdaptationResponse:
        async with self._session_factory() as session:
            return await load_adaptation_response(
                session,
                user_id=user_id,
                adaptation_id=adaptation_id,
            )

    async def list_adaptations(
        self,
        user_id: str,
        project_id: str,
    ) -> ChapterAdaptationListResponse:
        async with self._session_factory() as session:
            await _require_owned_project(
                session,
                user_id=user_id,
                project_id=project_id,
            )
            return ChapterAdaptationListResponse(
                adaptations=await list_adaptation_responses(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                )
            )

    async def create_plan_task(
        self,
        user_id: str,
        adaptation_id: str,
        request: StartShotPlanRunRequest,
    ) -> AdaptationTaskAcceptance:
        async with self._session_factory() as session:
            async with session.begin():
                adaptation, project, head = await _require_owned_adaptation(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                idempotency_key = (
                    f"video-adaptation-plan:{user_id}:{adaptation.id}:"
                    f"{request.clientRequestId}"
                )
                existing = await session.scalar(
                    select(VideoAdaptationTask).where(
                        VideoAdaptationTask.idempotencyKey == idempotency_key
                    )
                )
                if existing is not None:
                    payload = parse_video_adaptation_job_payload(existing.requestJson)
                    if (
                        not isinstance(payload, ChapterAdaptationPlanJobPayload)
                        or payload.pacingPreset != request.pacingPreset
                        or payload.targetEpisodeSeconds != request.targetEpisodeSeconds
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_ADAPTATION_IDEMPOTENCY_CONFLICT",
                            message="同一拆镜请求标识不能提交不同参数",
                        )
                    return AdaptationTaskAcceptance(adaptation.id, existing.id)
                # 网络重放必须先命中自身任务，之后才能把其他活动任务视为互斥冲突。
                await _require_no_active_task(session, adaptation.id)
                awaiting = await session.scalar(
                    select(ReviewArtifact.id).where(
                        ReviewArtifact.videoAdaptationId == adaptation.id,
                        ReviewArtifact.status == "awaiting_user",
                    )
                )
                if awaiting is not None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_REVIEW_PENDING",
                        message="当前已有待确认镜头方案，请先确认或放弃",
                    )
                task_id = generate_id()
                payload = ChapterAdaptationPlanJobPayload(
                    workflow="chapter_cinematic_adaptation_v2",
                    adaptationId=adaptation.id,
                    projectId=project.id,
                    chapterId=adaptation.chapterId or "deleted-chapter",
                    chapterTitle=adaptation.chapterTitle,
                    sourceText=adaptation.sourceText,
                    sourceHash=adaptation.sourceHash,
                    ratio=cast(AspectRatio, project.targetAspectRatio),
                    targetLanguage=project.targetLanguage,
                    pacingPreset=request.pacingPreset,
                    targetEpisodeSeconds=request.targetEpisodeSeconds,
                )
                inherited_checkpoint: str | None = None
                prior_failed = await session.scalar(
                    select(VideoAdaptationTask)
                    .where(
                        VideoAdaptationTask.adaptationId == adaptation.id,
                        VideoAdaptationTask.kind == "shot_plan",
                        VideoAdaptationTask.status == "failed",
                        VideoAdaptationTask.checkpointStage == "dramatic_structure",
                        VideoAdaptationTask.checkpointJson.is_not(None),
                    )
                    .order_by(
                        VideoAdaptationTask.createdAt.desc(),
                        VideoAdaptationTask.id.desc(),
                    )
                    .limit(1)
                    .with_for_update()
                )
                if prior_failed is not None:
                    try:
                        prior_payload = parse_video_adaptation_job_payload(
                            prior_failed.requestJson
                        )
                        if (
                            isinstance(prior_payload, ChapterAdaptationPlanJobPayload)
                            and prior_payload.sourceHash == payload.sourceHash
                            and prior_payload.pacingPreset == payload.pacingPreset
                            and prior_payload.targetEpisodeSeconds
                            == payload.targetEpisodeSeconds
                        ):
                            inherited_checkpoint = (
                                DramaticStructureCheckpoint.model_validate_json(
                                    prior_failed.checkpointJson or ""
                                ).model_dump_json()
                            )
                    except (ValidationError, ValueError):
                        inherited_checkpoint = None
                task = VideoAdaptationTask(
                    id=task_id,
                    adaptationId=adaptation.id,
                    projectId=project.id,
                    novelId=project.novelId,
                    baseShotPlanVersionId=None,
                    jobId=f"{self._job_prefix}{task_id}",
                    kind="shot_plan",
                    workflow=payload.workflow,
                    provider="deepseek",
                    status="pending",
                    idempotencyKey=idempotency_key,
                    requestJson=payload.model_dump_json(),
                    checkpointStage=(
                        "dramatic_structure" if inherited_checkpoint is not None else "none"
                    ),
                    checkpointJson=inherited_checkpoint,
                    attemptCount=0,
                    updatedAt=utc_now(),
                )
                session.add(task)
                head.updatedAt = utc_now()
        return AdaptationTaskAcceptance(adaptation_id, task_id)

    async def create_prompt_task(
        self,
        user_id: str,
        adaptation_id: str,
        request: StartPromptRunRequest,
    ) -> AdaptationTaskAcceptance:
        async with self._session_factory() as session:
            async with session.begin():
                adaptation, project, head = await _require_owned_adaptation(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                idempotency_key = (
                    f"video-adaptation-prompt:{user_id}:{adaptation.id}:"
                    f"{request.clientRequestId}"
                )
                existing = await session.scalar(
                    select(VideoAdaptationTask).where(
                        VideoAdaptationTask.idempotencyKey == idempotency_key
                    )
                )
                if existing is not None:
                    payload = parse_video_adaptation_job_payload(existing.requestJson)
                    if (
                        not isinstance(payload, ChapterAdaptationPromptJobPayload)
                        or payload.shotPlanVersionId != request.shotPlanVersionId
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_ADAPTATION_IDEMPOTENCY_CONFLICT",
                            message="同一提示词请求标识不能提交不同镜头方案",
                        )
                    if request.shotIds:
                        requested_keys = list(
                            (
                                await session.scalars(
                                    select(VideoShot.shotKey)
                                    .where(
                                        VideoShot.planVersionId
                                        == request.shotPlanVersionId,
                                        VideoShot.id.in_(request.shotIds),
                                    )
                                    .order_by(VideoShot.ordinal)
                                )
                            ).all()
                        )
                        if (
                            len(requested_keys) != len(set(request.shotIds))
                            or payload.targetShotKeys != requested_keys
                        ):
                            raise ApiError(
                                status_code=409,
                                code="VIDEO_ADAPTATION_IDEMPOTENCY_CONFLICT",
                                message="同一提示词请求标识不能提交不同镜头",
                            )
                    return AdaptationTaskAcceptance(adaptation.id, existing.id)
                if head.revision != request.expectedAdaptationRevision:
                    raise _adaptation_revision_conflict(head.revision)
                if head.currentShotPlanVersionId != request.shotPlanVersionId:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_PLAN_CHANGED",
                        message="当前正式镜头方案已经变化",
                    )
                detail = await load_adaptation_response(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation.id,
                )
                if detail.currentPlan is None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_PLAN_REQUIRED",
                        message="请先确认电影化镜头方案",
                    )
                shots = [
                    shot
                    for scene in detail.currentPlan.scenes
                    for beat in scene.beats
                    for shot in beat.shots
                ]
                requested_ids = set(request.shotIds)
                if requested_ids:
                    targets = [shot for shot in shots if shot.id in requested_ids]
                    if len(targets) != len(requested_ids):
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_ADAPTATION_SHOT_NOT_FOUND",
                            message="提示词任务包含当前方案之外的镜头",
                        )
                else:
                    saved_ids = {item.shotId for item in detail.promptVersions}
                    targets = [shot for shot in shots if shot.id not in saved_ids]
                if not targets:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_PROMPTS_COMPLETE",
                        message="所选镜头均已有正式提示词",
                    )
                target_keys = [shot.shotKey for shot in targets]
                await _require_no_active_task(session, adaptation.id)
                setting_snapshot = await build_long_serial_setting_snapshot(
                    session,
                    adaptation.novelId,
                )
                task_id = generate_id()
                payload = ChapterAdaptationPromptJobPayload(
                    workflow="chapter_shot_prompt_v2",
                    adaptationId=adaptation.id,
                    projectId=project.id,
                    shotPlanVersionId=request.shotPlanVersionId,
                    sourceText=adaptation.sourceText,
                    sourceHash=adaptation.sourceHash,
                    shotPlan=candidate_from_formal_plan(detail.currentPlan),
                    episodeBreakAfterShotKeys=detail.currentPlan.episodeBreakAfterShotKeys,
                    targetShotKeys=target_keys,
                    ratio=cast(AspectRatio, project.targetAspectRatio),
                    targetLanguage=project.targetLanguage,
                    settingSnapshot=setting_snapshot,
                )
                task = VideoAdaptationTask(
                    id=task_id,
                    adaptationId=adaptation.id,
                    projectId=project.id,
                    novelId=project.novelId,
                    baseShotPlanVersionId=request.shotPlanVersionId,
                    jobId=f"{self._job_prefix}{task_id}",
                    kind="shot_prompt",
                    workflow=payload.workflow,
                    provider="deepseek",
                    status="pending",
                    idempotencyKey=idempotency_key,
                    requestJson=payload.model_dump_json(),
                    checkpointStage="none",
                    checkpointJson=None,
                    attemptCount=0,
                    updatedAt=utc_now(),
                )
                session.add(task)
        return AdaptationTaskAcceptance(adaptation_id, task_id)

    async def get_task_response(
        self,
        user_id: str,
        task_id: str,
    ) -> ChapterAdaptationTaskResponse:
        async with self._session_factory() as session:
            row = await session.execute(
                select(VideoAdaptationTask, Novel.userId)
                .join(
                    VideoChapterAdaptation,
                    VideoChapterAdaptation.id == VideoAdaptationTask.adaptationId,
                )
                .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
                .join(Novel, Novel.id == VideoProject.novelId)
                .where(VideoAdaptationTask.id == task_id)
            )
            record = row.one_or_none()
            if record is None or str(record[1]) != user_id:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_ADAPTATION_TASK_NOT_FOUND",
                    message="章节影视化任务不存在",
                )
            return _task_response(record[0])

    async def claim_due_tasks(self, limit: int) -> list[AdaptationTaskDispatch]:
        """领取到期任务，并用短租约避免多个 Core worker 重复投递。"""

        if limit < 1:
            raise ValueError("章节影视化任务领取数量必须为正整数")
        now = utc_now()
        lease_until = now + timedelta(seconds=30)
        async with self._session_factory() as session:
            async with session.begin():
                rows = (
                    await session.execute(
                        select(VideoAdaptationTask, Novel.userId)
                        .join(
                            VideoChapterAdaptation,
                            VideoChapterAdaptation.id == VideoAdaptationTask.adaptationId,
                        )
                        .join(VideoProject, VideoProject.id == VideoAdaptationTask.projectId)
                        .join(Novel, Novel.id == VideoProject.novelId)
                        .where(
                            VideoAdaptationTask.provider == "deepseek",
                            VideoAdaptationTask.jobId.like(f"{self._job_prefix}%"),
                            VideoAdaptationTask.status.in_(_ACTIVE_TASK_STATUSES),
                            VideoAdaptationTask.nextAttemptAt <= now,
                            VideoProject.deletedAt.is_(None),
                        )
                        .order_by(
                            VideoAdaptationTask.nextAttemptAt,
                            VideoAdaptationTask.createdAt,
                            VideoAdaptationTask.id,
                        )
                        .limit(limit)
                        .with_for_update(of=VideoAdaptationTask, skip_locked=True)
                    )
                ).all()
                records: list[AdaptationTaskDispatch] = []
                for task, owner_id in rows:
                    try:
                        payload = parse_video_adaptation_job_payload(task.requestJson)
                        _validate_task_payload(task, payload)
                    except ValueError as exc:
                        _fail_task(
                            task,
                            code="VIDEO_ADAPTATION_DISPATCH_INPUT_INVALID",
                            message=str(exc),
                        )
                        continue
                    task.nextAttemptAt = lease_until
                    task.updatedAt = utc_now()
                    records.append(
                        AdaptationTaskDispatch(
                            user_id=str(owner_id),
                            novel_id=task.novelId,
                            task_id=task.id,
                            job_id=task.jobId,
                            payload=payload,
                        )
                    )
        return records

    async def mark_submitted(self, task_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoAdaptationTask, task_id, with_for_update=True)
                if task is not None and task.status in _ACTIVE_TASK_STATUSES:
                    now = utc_now()
                    if task.status == "pending":
                        task.status = "submitted"
                    if task.submittedAt is None:
                        task.submittedAt = now
                    task.nextAttemptAt = now + timedelta(minutes=10)
                    task.lastErrorCode = None
                    task.lastErrorMessage = None
                    task.updatedAt = now

    async def record_dispatch_failure(
        self,
        task_id: str,
        error_code: str,
        *,
        transient: bool,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoAdaptationTask, task_id, with_for_update=True)
                if task is None or task.status in {"completed", "failed", "cancelled"}:
                    return
                if transient:
                    now = utc_now()
                    task.attemptCount += 1
                    task.status = "pending"
                    task.nextAttemptAt = now + _dispatch_backoff(task.attemptCount)
                    task.lastErrorCode = "VIDEO_ADAPTATION_AGENT_SUBMIT_RETRY"
                    task.lastErrorMessage = f"章节影视化任务投递暂时失败：{error_code}"
                    task.completedAt = None
                    task.updatedAt = now
                    return
                _fail_task(
                    task,
                    code="VIDEO_ADAPTATION_AGENT_SUBMIT_FAILED",
                    message=f"章节影视化任务投递失败：{error_code}",
                )

    async def settle_dispatch_terminal(
        self,
        task_id: str,
        agent_status: AgentJobStatus,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoAdaptationTask, task_id, with_for_update=True)
                if task is None or task.status in {"completed", "failed", "cancelled"}:
                    return
                _fail_task(
                    task,
                    code="VIDEO_ADAPTATION_AGENT_TERMINAL_WITHOUT_CALLBACK",
                    message=f"Agent 队列已进入 {agent_status}，但 Core 未收到章节影视化终态回调",
                    status="cancelled" if agent_status == "cancelled" else "failed",
                )

    async def get_workflow_progress(
        self,
        query: VideoAdaptationWorkflowProgressQuery,
    ) -> VideoAdaptationWorkflowProgressResponse:
        async with self._session_factory() as session:
            async with session.begin():
                task, _, _ = await _require_callback_context(session, query, lock=True)
                if task.status in _ACTIVE_TASK_STATUSES:
                    task.status = "processing"
                    task.nextAttemptAt = utc_now() + timedelta(minutes=10)
                    task.updatedAt = utc_now()
                    status = "active"
                elif task.status == "completed":
                    status = "completed"
                else:
                    status = "failed"
                checkpoint = (
                    DramaticStructureCheckpoint.model_validate_json(task.checkpointJson)
                    if task.checkpointJson is not None
                    else None
                )
        return VideoAdaptationWorkflowProgressResponse(
            **query.model_dump(mode="python"),
            status=cast(Literal["active", "completed", "failed"], status),
            checkpoint=checkpoint,
        )

    async def save_checkpoint(
        self,
        callback: VideoAdaptationCheckpointCallback,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task, _, _ = await _require_callback_context(session, callback, lock=True)
                if task.kind != "shot_plan" or task.status not in _ACTIVE_TASK_STATUSES:
                    raise _callback_state_conflict()
                checkpoint_json = callback.checkpoint.model_dump_json()
                if task.checkpointStage == "dramatic_structure":
                    if task.checkpointJson == checkpoint_json:
                        return
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_CHECKPOINT_CONFLICT",
                        message="同一戏剧结构阶段不能覆盖不同内容",
                    )
                if task.checkpointStage != "none" or task.checkpointJson is not None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_CHECKPOINT_CONFLICT",
                        message="章节影视化检查点阶段非法",
                    )
                task.status = "processing"
                task.checkpointStage = "dramatic_structure"
                task.checkpointJson = checkpoint_json
                task.nextAttemptAt = utc_now() + timedelta(minutes=10)
                task.updatedAt = utc_now()

    async def complete_plan(
        self,
        callback: VideoAdaptationPlanCompletionCallback,
    ) -> None:
        result = {
            "eventId": callback.eventId,
            "workflow": "chapter_cinematic_adaptation_v2",
            "candidate": candidate_json(callback.candidate),
        }
        result_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
        async with self._session_factory() as session:
            async with session.begin():
                task, adaptation, _ = await _require_callback_context(
                    session,
                    callback,
                    lock=True,
                )
                if task.kind != "shot_plan":
                    raise _callback_state_conflict()
                if task.status == "completed":
                    if task.resultJson == result_json:
                        return
                    raise _terminal_callback_conflict()
                if task.status not in _ACTIVE_TASK_STATUSES:
                    raise _callback_state_conflict()
                validate_plan_against_source(
                    callback.candidate,
                    adaptation_id=adaptation.id,
                    source_text=adaptation.sourceText,
                    source_hash=adaptation.sourceHash,
                )
                awaiting = await session.scalar(
                    select(ReviewArtifact.id).where(
                        ReviewArtifact.videoAdaptationId == adaptation.id,
                        ReviewArtifact.status == "awaiting_user",
                    )
                )
                if awaiting is not None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_REVIEW_PENDING",
                        message="当前已有待确认章节镜头方案",
                    )
                payload = {
                    "applyTarget": {
                        "type": "video_adaptation_plan",
                        "adaptationId": adaptation.id,
                    },
                    "candidate": candidate_json(callback.candidate),
                }
                now = utc_now()
                session.add(
                    ReviewArtifact(
                        novelId=adaptation.novelId,
                        chapterId=adaptation.chapterId,
                        taskId=None,
                        videoSceneId=None,
                        videoAdaptationId=adaptation.id,
                        videoAdaptationTaskId=task.id,
                        kind="video_adaptation_plan",
                        status="awaiting_user",
                        title=f"{adaptation.chapterTitle} · 电影化镜头方案",
                        summary=_candidate_summary(callback.candidate),
                        payloadJson=json.dumps(payload, ensure_ascii=False),
                        artifactKey=f"video-adaptation-plan:{adaptation.id}:{task.id}",
                        revision=1,
                        createdByAgent="剧情",
                        updatedAt=now,
                    )
                )
                task.status = "completed"
                task.resultJson = result_json
                task.completedAt = now
                task.updatedAt = now

    async def complete_prompts(
        self,
        callback: VideoAdaptationPromptCompletionCallback,
    ) -> None:
        result = {
            "eventId": callback.eventId,
            "workflow": "chapter_shot_prompt_v2",
            "promptBatch": callback.promptBatch.model_dump(mode="json"),
        }
        result_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
        async with self._session_factory() as session:
            async with session.begin():
                task, _, _ = await _require_callback_context(session, callback, lock=True)
                if task.kind != "shot_prompt":
                    raise _callback_state_conflict()
                if task.status == "completed":
                    if task.resultJson == result_json:
                        return
                    raise _terminal_callback_conflict()
                if task.status not in _ACTIVE_TASK_STATUSES:
                    raise _callback_state_conflict()
                payload = parse_video_adaptation_job_payload(task.requestJson)
                if not isinstance(payload, ChapterAdaptationPromptJobPayload):
                    raise _callback_state_conflict()
                actual_keys = [item.shotKey for item in callback.promptBatch.prompts]
                if actual_keys != payload.targetShotKeys:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_PROMPT_TARGET_MISMATCH",
                        message="逐镜提示词结果没有按请求顺序完整覆盖目标镜头",
                    )
                now = utc_now()
                task.status = "completed"
                task.resultJson = result_json
                task.completedAt = now
                task.updatedAt = now

    async def fail_task(self, callback: VideoAdaptationFailureCallback) -> None:
        result = {
            "eventId": callback.eventId,
            "code": callback.code,
            "message": callback.message,
            "recoverable": callback.recoverable,
        }
        result_json = json.dumps(result, ensure_ascii=False, sort_keys=True)
        async with self._session_factory() as session:
            async with session.begin():
                task, _, _ = await _require_callback_context(session, callback, lock=True)
                if task.status == "failed":
                    if task.resultJson == result_json:
                        return
                    raise _terminal_callback_conflict()
                if task.status not in _ACTIVE_TASK_STATUSES:
                    raise _callback_state_conflict()
                _fail_task(
                    task,
                    code=callback.code,
                    message=callback.message,
                    result_json=result_json,
                )

    async def confirm_plan(
        self,
        user_id: str,
        adaptation_id: str,
        request: ConfirmAdaptationPlanRequest,
    ) -> ChapterAdaptationResponse:
        request_hash = canonical_json_hash(
            {
                "adaptationId": adaptation_id,
                "expectedArtifactRevision": request.expectedArtifactRevision,
                "expectedAdaptationRevision": request.expectedAdaptationRevision,
                "plan": candidate_json(request.plan),
            }
        )
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": _decision_lock_key(user_id, request.clientRequestId)},
                )
                existing = await session.scalar(
                    select(VideoAdaptationDecisionCommand).where(
                        VideoAdaptationDecisionCommand.requestedByUserId == user_id,
                        VideoAdaptationDecisionCommand.clientRequestId
                        == request.clientRequestId,
                    )
                )
                if existing is not None:
                    if existing.requestHash != request_hash:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_ADAPTATION_DECISION_IDEMPOTENCY_CONFLICT",
                            message="同一批准请求标识不能绑定不同镜头方案",
                        )
                    return_id = existing.adaptationId
                else:
                    adaptation, project, head = await _require_owned_adaptation(
                        session,
                        user_id=user_id,
                        adaptation_id=adaptation_id,
                        lock=True,
                    )
                    if head.revision != request.expectedAdaptationRevision:
                        raise _adaptation_revision_conflict(head.revision)
                    artifact = await session.scalar(
                        select(ReviewArtifact)
                        .where(
                            ReviewArtifact.videoAdaptationId == adaptation.id,
                            ReviewArtifact.revision == request.expectedArtifactRevision,
                        )
                        .order_by(ReviewArtifact.createdAt.desc())
                        .limit(1)
                        .with_for_update()
                    )
                    if artifact is None or artifact.status != "awaiting_user":
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_ADAPTATION_REVIEW_NOT_PENDING",
                            message="当前没有匹配版本的待确认镜头方案",
                        )
                    task = await session.get(
                        VideoAdaptationTask,
                        artifact.videoAdaptationTaskId,
                        with_for_update=True,
                    )
                    if (
                        task is None
                        or task.adaptationId != adaptation.id
                        or task.status != "completed"
                        or task.kind != "shot_plan"
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_ADAPTATION_SOURCE_TASK_INVALID",
                            message="待确认方案缺少可核验的完成任务",
                        )
                    validate_plan_against_source(
                        request.plan,
                        adaptation_id=adaptation.id,
                        source_text=adaptation.sourceText,
                        source_hash=adaptation.sourceHash,
                    )
                    plan_version = await _materialize_plan(
                        session,
                        adaptation=adaptation,
                        head=head,
                        artifact=artifact,
                        task=task,
                        user_id=user_id,
                        plan=request.plan,
                    )
                    now = utc_now()
                    artifact.status = "applied"
                    artifact.appliedAt = now
                    artifact.updatedAt = now
                    head.currentShotPlanVersionId = plan_version.id
                    head.currentEpisodePlanVersionId = None
                    head.revision += 1
                    head.updatedAt = now
                    result = {
                        "adaptationId": adaptation.id,
                        "planVersionId": plan_version.id,
                        "headRevision": head.revision,
                    }
                    session.add(
                        VideoAdaptationDecisionCommand(
                            id=generate_id(),
                            requestedByUserId=user_id,
                            novelId=adaptation.novelId,
                            projectId=project.id,
                            adaptationId=adaptation.id,
                            artifactId=artifact.id,
                            sourceTaskId=task.id,
                            clientRequestId=request.clientRequestId,
                            expectedArtifactRevision=request.expectedArtifactRevision,
                            expectedAdaptationRevision=request.expectedAdaptationRevision,
                            requestHash=request_hash,
                            decision="approve",
                            status="succeeded",
                            resultJson=json.dumps(result, ensure_ascii=False),
                            completedAt=now,
                            updatedAt=now,
                        )
                    )
                    return_id = adaptation.id
        return await self.get_adaptation(user_id, return_id)

    async def save_episode_plan(
        self,
        user_id: str,
        adaptation_id: str,
        request: SaveEpisodePlanRequest,
    ) -> ChapterAdaptationResponse:
        # 同内容网络重放由当前 EpisodePlan contentHash 幂等收敛。
        async with self._session_factory() as session:
            async with session.begin():
                adaptation, _, head = await _require_owned_adaptation(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                if head.currentShotPlanVersionId != request.shotPlanVersionId:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_PLAN_CHANGED",
                        message="保存分集时正式镜头方案已经变化",
                    )
                shots = list(
                    (
                        await session.scalars(
                            select(VideoShot)
                            .where(VideoShot.planVersionId == request.shotPlanVersionId)
                            .order_by(VideoShot.ordinal)
                            .with_for_update()
                        )
                    ).all()
                )
                validate_episode_boundaries(
                    request.breakAfterShotIds,
                    ordered_shot_ids=[shot.id for shot in shots],
                )
                content_hash = canonical_json_hash(
                    {
                        "shotPlanVersionId": request.shotPlanVersionId,
                        "breakAfterShotIds": request.breakAfterShotIds,
                    }
                )
                current = (
                    await session.get(
                        VideoEpisodePlanVersion,
                        head.currentEpisodePlanVersionId,
                    )
                    if head.currentEpisodePlanVersionId
                    else None
                )
                if current is not None and current.contentHash == content_hash:
                    return_id = adaptation.id
                else:
                    if head.revision != request.expectedAdaptationRevision:
                        raise _adaptation_revision_conflict(head.revision)
                    version_no = int(
                        await session.scalar(
                            select(func.coalesce(func.max(VideoEpisodePlanVersion.versionNo), 0))
                            .where(VideoEpisodePlanVersion.adaptationId == adaptation.id)
                        )
                        or 0
                    ) + 1
                    version = VideoEpisodePlanVersion(
                        id=generate_id(),
                        adaptationId=adaptation.id,
                        shotPlanVersionId=request.shotPlanVersionId,
                        versionNo=version_no,
                        basedOnVersionId=current.id if current else None,
                        createdByUserId=user_id,
                        contentHash=content_hash,
                    )
                    session.add(version)
                    await session.flush()
                    for ordinal, shot_id in enumerate(request.breakAfterShotIds, start=1):
                        session.add(
                            VideoEpisodeBoundary(
                                episodePlanVersionId=version.id,
                                shotPlanVersionId=request.shotPlanVersionId,
                                afterShotId=shot_id,
                                ordinal=ordinal,
                            )
                        )
                    await session.flush()
                    head.currentEpisodePlanVersionId = version.id
                    head.revision += 1
                    head.updatedAt = utc_now()
                    return_id = adaptation.id
        return await self.get_adaptation(user_id, return_id)

    async def discard_candidate(
        self,
        user_id: str,
        adaptation_id: str,
        request: DiscardAdaptationCandidateRequest,
    ) -> ChapterAdaptationResponse:
        """显式删除待审候选；正式方案和来源任务历史保持不变。"""

        # candidate 删除由 Artifact/head revision 绑定；请求标识进入公共请求日志。
        async with self._session_factory() as session:
            async with session.begin():
                adaptation, _, head = await _require_owned_adaptation(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                if head.revision != request.expectedAdaptationRevision:
                    raise _adaptation_revision_conflict(head.revision)
                artifact = await session.scalar(
                    select(ReviewArtifact)
                    .where(
                        ReviewArtifact.videoAdaptationId == adaptation.id,
                        ReviewArtifact.status == "awaiting_user",
                        ReviewArtifact.revision == request.expectedArtifactRevision,
                    )
                    .order_by(ReviewArtifact.createdAt.desc())
                    .limit(1)
                    .with_for_update()
                )
                if artifact is None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_REVIEW_NOT_PENDING",
                        message="当前没有匹配版本的待审镜头方案",
                    )
                await session.delete(artifact)
                head.revision += 1
                head.updatedAt = utc_now()
        return await self.get_adaptation(user_id, adaptation_id)

    async def save_prompt(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        request: SaveShotPromptRequest,
    ) -> ChapterAdaptationResponse:
        async with self._session_factory() as session:
            async with session.begin():
                adaptation, project, head = await _require_owned_adaptation(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                if head.currentShotPlanVersionId is None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ADAPTATION_PLAN_REQUIRED",
                        message="请先确认电影化镜头方案",
                    )
                shot = await session.scalar(
                    select(VideoShot)
                    .where(
                        VideoShot.id == shot_id,
                        VideoShot.planVersionId == head.currentShotPlanVersionId,
                    )
                    .with_for_update()
                )
                prompt_head = await session.get(
                    VideoShotPromptHead,
                    shot_id,
                    with_for_update=True,
                )
                if shot is None or prompt_head is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_ADAPTATION_SHOT_NOT_FOUND",
                        message="正式镜头不存在",
                    )
                current_version = (
                    await session.get(VideoShotPromptVersion, prompt_head.currentVersionId)
                    if prompt_head.currentVersionId
                    else None
                )
                generated_text = current_version.generatedText if current_version else None
                source_task_id = current_version.sourceTaskId if current_version else None
                if request.candidateTaskId is not None:
                    task = await session.get(
                        VideoAdaptationTask,
                        request.candidateTaskId,
                        with_for_update=True,
                    )
                    generated_text = _prompt_candidate_text(
                        task,
                        adaptation=adaptation,
                        plan_version_id=head.currentShotPlanVersionId,
                        shot=shot,
                        ratio=cast(AspectRatio, project.targetAspectRatio),
                    )
                    source_task_id = task.id if task is not None else None
                content_hash = canonical_json_hash(
                    {
                        "shotId": shot.id,
                        "generatedText": generated_text,
                        "currentText": request.currentPrompt,
                    }
                )
                if current_version is not None and current_version.contentHash == content_hash:
                    return_id = adaptation.id
                else:
                    if prompt_head.revision != request.expectedPromptRevision:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_SHOT_PROMPT_REVISION_CONFLICT",
                            message="镜头提示词版本已经变化",
                            details={"currentRevision": prompt_head.revision},
                        )
                    version_no = int(
                        await session.scalar(
                            select(func.coalesce(func.max(VideoShotPromptVersion.versionNo), 0))
                            .where(VideoShotPromptVersion.shotId == shot.id)
                        )
                        or 0
                    ) + 1
                    version = VideoShotPromptVersion(
                        id=generate_id(),
                        shotId=shot.id,
                        shotPlanVersionId=shot.planVersionId,
                        versionNo=version_no,
                        basedOnVersionId=current_version.id if current_version else None,
                        generatedText=generated_text,
                        currentText=request.currentPrompt,
                        sourceTaskId=source_task_id,
                        createdByUserId=user_id,
                        contentHash=content_hash,
                    )
                    session.add(version)
                    await session.flush()
                    prompt_head.currentVersionId = version.id
                    prompt_head.revision += 1
                    prompt_head.updatedAt = utc_now()
                    return_id = adaptation.id
        return await self.get_adaptation(user_id, return_id)


async def _materialize_plan(
    session: AsyncSession,
    *,
    adaptation: VideoChapterAdaptation,
    head: VideoChapterAdaptationHead,
    artifact: ReviewArtifact,
    task: VideoAdaptationTask,
    user_id: str,
    plan: ChapterAdaptationPlanCandidate,
) -> VideoShotPlanVersion:
    version_no = int(
        await session.scalar(
            select(func.coalesce(func.max(VideoShotPlanVersion.versionNo), 0)).where(
                VideoShotPlanVersion.adaptationId == adaptation.id
            )
        )
        or 0
    ) + 1
    version = VideoShotPlanVersion(
        id=generate_id(),
        adaptationId=adaptation.id,
        versionNo=version_no,
        basedOnVersionId=head.currentShotPlanVersionId,
        sourceTaskId=task.id,
        reviewArtifactId=artifact.id,
        createdByUserId=user_id,
        contentHash=canonical_json_hash(candidate_json(plan)),
    )
    session.add(version)
    # 这些不可变行只通过显式 ID 关联、没有 ORM relationship；按表层级批量 flush，
    # 既固定外键写入顺序，也避免按每个镜头往返开发库。
    await session.flush()

    scene_rows: list[tuple[VideoCinematicScene, CinematicSceneCandidate]] = []
    for scene_ordinal, scene_candidate in enumerate(plan.scenes, start=1):
        scene = VideoCinematicScene(
            id=generate_id(),
            planVersionId=version.id,
            adaptationId=adaptation.id,
            sceneKey=scene_candidate.sceneKey,
            ordinal=scene_ordinal,
            title=scene_candidate.title,
            locationLabel=scene_candidate.locationLabel,
            timeLabel=scene_candidate.timeLabel,
            objective=scene_candidate.objective,
            changeSummary=scene_candidate.changeSummary,
        )
        session.add(scene)
        scene_rows.append((scene, scene_candidate))
    await session.flush()

    beat_ordinal = 0
    beat_rows: list[tuple[VideoDramaticBeat, DramaticBeatCandidate, str]] = []
    for scene, scene_candidate in scene_rows:
        for beat_candidate in scene_candidate.beats:
            beat_ordinal += 1
            beat = VideoDramaticBeat(
                id=generate_id(),
                planVersionId=version.id,
                sceneId=scene.id,
                beatKey=beat_candidate.beatKey,
                ordinal=beat_ordinal,
                title=beat_candidate.title,
                dramaticTurn=beat_candidate.dramaticTurn,
                visualStrategy=beat_candidate.visualStrategy,
            )
            session.add(beat)
            beat_rows.append((beat, beat_candidate, scene.id))
    await session.flush()

    shot_ordinal = 0
    shot_rows: list[tuple[VideoShot, CinematicShotCandidate]] = []
    for beat, beat_candidate, scene_id in beat_rows:
        for anchor_ordinal, source_range in enumerate(
            beat_candidate.sourceRanges,
            start=1,
        ):
            session.add(
                VideoDramaticBeatSourceAnchor(
                    beatId=beat.id,
                    planVersionId=version.id,
                    ordinal=anchor_ordinal,
                    startCodePoint=source_range.start,
                    endCodePoint=source_range.end,
                )
            )
        for shot_candidate in beat_candidate.shots:
            shot_ordinal += 1
            shot = VideoShot(
                id=generate_id(),
                planVersionId=version.id,
                sceneId=scene_id,
                beatId=beat.id,
                shotKey=shot_candidate.shotKey,
                ordinal=shot_ordinal,
                title=shot_candidate.title,
                narrativePurpose=shot_candidate.narrativePurpose,
                adaptationType=shot_candidate.adaptationType,
                shotScale=shot_candidate.shotScale,
                cameraAngle=shot_candidate.cameraAngle,
                cameraMovement=shot_candidate.cameraMovement,
                visualIntent=shot_candidate.visualIntent,
                audioMode=shot_candidate.audioMode,
                audioIntent=shot_candidate.audioIntent,
                cutReason=shot_candidate.cutReason,
                timelineDurationMs=shot_candidate.timelineDurationMs,
            )
            session.add(shot)
            shot_rows.append((shot, shot_candidate))
    await session.flush()

    for shot, shot_candidate in shot_rows:
        session.add(
            VideoShotPromptHead(
                shotId=shot.id,
                shotPlanVersionId=version.id,
                currentVersionId=None,
                revision=1,
                updatedAt=utc_now(),
            )
        )
        for anchor_ordinal, source_range in enumerate(
            shot_candidate.sourceRanges,
            start=1,
        ):
            session.add(
                VideoShotSourceAnchor(
                    shotId=shot.id,
                    planVersionId=version.id,
                    ordinal=anchor_ordinal,
                    startCodePoint=source_range.start,
                    endCodePoint=source_range.end,
                )
            )
    return version


async def _require_owned_project(
    session: AsyncSession,
    *,
    user_id: str,
    project_id: str,
    lock: bool = False,
) -> VideoProject:
    statement = (
        select(VideoProject)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(
            VideoProject.id == project_id,
            VideoProject.deletedAt.is_(None),
            Novel.userId == user_id,
        )
    )
    if lock:
        statement = statement.with_for_update(of=VideoProject)
    project = await session.scalar(statement)
    if project is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_PROJECT_NOT_FOUND",
            message="视频项目不存在",
        )
    return project


async def _require_owned_adaptation(
    session: AsyncSession,
    *,
    user_id: str,
    adaptation_id: str,
    lock: bool,
) -> tuple[VideoChapterAdaptation, VideoProject, VideoChapterAdaptationHead]:
    statement = (
        select(VideoChapterAdaptation, VideoProject)
        .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(
            VideoChapterAdaptation.id == adaptation_id,
            VideoChapterAdaptation.lifecycleStatus == "active",
            VideoProject.deletedAt.is_(None),
            Novel.userId == user_id,
        )
    )
    if lock:
        statement = statement.with_for_update(of=(VideoChapterAdaptation, VideoProject))
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_ADAPTATION_NOT_FOUND",
            message="章节影视化改编不存在",
        )
    adaptation, project = row
    head = await session.get(
        VideoChapterAdaptationHead,
        adaptation.id,
        with_for_update=lock,
    )
    if head is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_HEAD_MISSING",
            message="章节影视化改编缺少正式版本指针",
        )
    return adaptation, project, head


async def _require_long_serial(
    session: AsyncSession,
    novel_id: str,
    *,
    lock: bool,
) -> None:
    statement = select(WritingBible).where(WritingBible.novelId == novel_id)
    if lock:
        statement = statement.with_for_update()
    bible = await session.scalar(statement)
    if bible is None or bible.storyLengthProfile != "long_serial":
        raise ApiError(
            status_code=409,
            code="VIDEO_LONG_SERIAL_REQUIRED",
            message="视频制作只支持长篇小说",
        )


async def _require_no_active_task(session: AsyncSession, adaptation_id: str) -> None:
    active = await session.scalar(
        select(VideoAdaptationTask.id).where(
            VideoAdaptationTask.adaptationId == adaptation_id,
            VideoAdaptationTask.status.in_(_ACTIVE_TASK_STATUSES),
        )
    )
    if active is not None:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_TASK_ACTIVE",
            message="当前章节改编已有活动任务",
        )


async def _require_callback_context(
    session: AsyncSession,
    value: _CallbackIdentity,
    *,
    lock: bool,
) -> tuple[VideoAdaptationTask, VideoChapterAdaptation, VideoProject]:
    task_id = str(value.taskId)
    task = await session.get(VideoAdaptationTask, task_id, with_for_update=lock)
    if task is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_ADAPTATION_TASK_NOT_FOUND",
            message="章节影视化任务不存在",
        )
    adaptation = await session.get(
        VideoChapterAdaptation,
        task.adaptationId,
        with_for_update=lock,
    )
    project = await session.get(VideoProject, task.projectId, with_for_update=lock)
    if adaptation is None or project is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_CALLBACK_TARGET_INVALID",
            message="章节影视化回调目标已经不存在",
        )
    expected = {
        "jobId": task.jobId,
        "runId": task.id,
        "taskId": task.id,
        "novelId": task.novelId,
        "projectId": task.projectId,
        "adaptationId": task.adaptationId,
        "workflow": task.workflow,
    }
    for field, expected_value in expected.items():
        actual = getattr(value, field, expected_value)
        if str(actual) != expected_value:
            raise ApiError(
                status_code=403,
                code="VIDEO_ADAPTATION_CALLBACK_RESOURCE_MISMATCH",
                message="章节影视化回调资源绑定不匹配",
            )
    latest_id = await session.scalar(
        select(VideoAdaptationTask.id)
        .where(
            VideoAdaptationTask.adaptationId == task.adaptationId,
            VideoAdaptationTask.kind == task.kind,
        )
        .order_by(VideoAdaptationTask.createdAt.desc(), VideoAdaptationTask.id.desc())
        .limit(1)
    )
    if latest_id != task.id:
        raise ApiError(
            status_code=409,
            code="VIDEO_ADAPTATION_CALLBACK_STALE",
            message="旧章节影视化任务不能覆盖更新任务",
        )
    return task, adaptation, project


def _validate_task_payload(
    task: VideoAdaptationTask,
    payload: VideoAdaptationJobPayload,
) -> None:
    if (
        payload.adaptationId != task.adaptationId
        or payload.projectId != task.projectId
        or payload.workflow != task.workflow
    ):
        raise ValueError("章节影视化任务冻结输入与任务归属不一致")
    if isinstance(payload, ChapterAdaptationPlanJobPayload):
        if task.kind != "shot_plan" or task.baseShotPlanVersionId is not None:
            raise ValueError("章节拆镜任务类型或基础版本不一致")
    elif (
        task.kind != "shot_prompt"
        or task.baseShotPlanVersionId != payload.shotPlanVersionId
    ):
        raise ValueError("逐镜提示词任务类型或基础版本不一致")


def _prompt_candidate_text(
    task: VideoAdaptationTask | None,
    *,
    adaptation: VideoChapterAdaptation,
    plan_version_id: str,
    shot: VideoShot,
    ratio: AspectRatio,
) -> str:
    if (
        task is None
        or task.adaptationId != adaptation.id
        or task.baseShotPlanVersionId != plan_version_id
        or task.kind != "shot_prompt"
        or task.status != "completed"
        or task.resultJson is None
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_SHOT_PROMPT_CANDIDATE_INVALID",
            message="提示词候选不存在或不属于当前镜头方案",
        )
    try:
        result = json.loads(task.resultJson)
        batch = ShotPromptSpecBatch.model_validate(result["promptBatch"])
        item = next(prompt for prompt in batch.prompts if prompt.shotKey == shot.shotKey)
        return compile_seedance_shot_prompt(
            item.spec,
            ratio=ratio,
            timeline_duration_ms=shot.timelineDurationMs,
        )
    except (KeyError, StopIteration, TypeError, ValueError) as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_SHOT_PROMPT_CANDIDATE_INVALID",
            message="提示词候选内容损坏或不包含当前镜头",
        ) from exc


def _task_response(task: VideoAdaptationTask) -> ChapterAdaptationTaskResponse:
    return ChapterAdaptationTaskResponse(
        id=task.id,
        jobId=task.jobId,
        kind=cast(Literal["shot_plan", "shot_prompt"], task.kind),
        workflow=task.workflow,
        status=task.status,
        checkpointStage=task.checkpointStage,
        lastErrorCode=task.lastErrorCode,
        lastErrorMessage=task.lastErrorMessage,
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
    )


def _fail_task(
    task: VideoAdaptationTask,
    *,
    code: str,
    message: str,
    status: str = "failed",
    result_json: str | None = None,
) -> None:
    now = utc_now()
    task.status = status
    task.lastErrorCode = code
    task.lastErrorMessage = message
    task.resultJson = result_json
    task.completedAt = now
    task.updatedAt = now


def _candidate_summary(candidate: ChapterAdaptationPlanCandidate) -> str:
    beats = sum(len(scene.beats) for scene in candidate.scenes)
    shots = sum(len(beat.shots) for scene in candidate.scenes for beat in scene.beats)
    duration_seconds = sum(
        shot.timelineDurationMs
        for scene in candidate.scenes
        for beat in scene.beats
        for shot in beat.shots
    ) / 1000
    return (
        f"{len(candidate.scenes)} 个场景 · {beats} 个戏剧节拍 · "
        f"{shots} 个镜头 · 约 {duration_seconds:g} 秒"
    )


def _adaptation_revision_conflict(current_revision: int) -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_ADAPTATION_REVISION_CONFLICT",
        message="章节影视化版本已经变化，请刷新后重试",
        details={"currentRevision": current_revision},
    )


def _callback_state_conflict() -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_ADAPTATION_CALLBACK_STATE_CONFLICT",
        message="章节影视化任务当前状态不接受该回调",
    )


def _terminal_callback_conflict() -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_ADAPTATION_TERMINAL_CALLBACK_CONFLICT",
        message="章节影视化终态回调与已保存结果不一致",
    )


def _decision_lock_key(user_id: str, client_request_id: str) -> int:
    digest = hashlib.sha256(
        f"video-adaptation-decision:{user_id}:{client_request_id}".encode()
    ).digest()
    raw = int.from_bytes(digest[:8], "big")
    return raw if raw < 2**63 else raw - 2**64


def _dispatch_backoff(attempt_count: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** min(max(attempt_count, 1), 8)))


def _database_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class _CallbackIdentity(Protocol):
    jobId: str
    runId: str
    taskId: str
    novelId: str
    projectId: str
    adaptationId: str

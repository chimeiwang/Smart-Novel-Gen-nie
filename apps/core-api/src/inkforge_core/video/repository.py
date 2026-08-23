"""视频项目、场景、任务与 ReviewArtifact 的 PostgreSQL 事务实现。"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from inkforge_contracts.jobs import AgentJobStatus
from inkforge_contracts.video import (
    VIDEO_PLAN_MAX_EFFECTIVE_CALLS,
    AspectRatio,
    AssetDuty,
    AssetModality,
    SceneAssetsStageArguments,
    ScenePromptSpec,
    SeedancePromptPackage,
    StoryPlanStageArguments,
    VideoPlanAttemptState,
    VideoPlanCallReservationRequest,
    VideoPlanCallReservationResponse,
    VideoPlanCompletionCallback,
    VideoPlanFailureCallback,
    VideoPlanJobPayload,
    VideoPlanProgressQuery,
    VideoPlanProgressResponse,
    VideoStoryPlanCheckpointCallback,
    calculate_video_plan_business_input_fingerprint,
    calculate_video_plan_input_fingerprint,
)
from pydantic import JsonValue
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..billing.request_ids import video_task_billing_request_prefix
from ..db.base import generate_id, utc_now
from ..db.models import (
    Chapter,
    CreditLedger,
    Novel,
    ReviewArtifact,
    ReviewArtifactRevision,
    User,
    VideoAsset,
    VideoAssetBinding,
    VideoGenerationTask,
    VideoProject,
    VideoReviewDecisionCommand,
    VideoScene,
    WritingBible,
)
from ..errors import ApiError
from .plan_result import (
    VideoPlanTerminalResult,
    VideoPlanTerminalResultFormatError,
    decode_video_plan_terminal_result,
    encode_video_plan_terminal_result,
    video_plan_results_equal,
    video_plan_terminal_progress_json,
)
from .schemas import (
    ApproveVideoSceneRequest,
    ApproveVideoSceneResponse,
    CreateVideoProjectRequest,
    CreateVideoSceneRequest,
    PromptPreviewRequest,
    ReviseVideoSceneRequest,
    VideoAssetBindingResponse,
    VideoAssetResponse,
    VideoGenerationTaskResponse,
    VideoProjectDetailResponse,
    VideoProjectResponse,
    VideoReviewArtifactSummary,
    VideoSceneResponse,
)
from .setting_snapshot import build_long_serial_setting_snapshot
from .storage import StoredVideoAsset

_PREVIEW_PROJECT_MODES = {"concept", "trailer", "highlight"}
_ACTIVE_VIDEO_PLAN_TASK_STATUSES = {"pending", "submitted", "processing"}
_PLAN_PROGRESS_CHECKPOINT_KIND = "video_plan_progress_checkpoint"
_PLAN_PROGRESS_CHECKPOINT_VERSION = "2.0"
_LEGACY_PLAN_PROGRESS_CHECKPOINT_VERSION = "1.0"

_ActiveCheckpointStage = Literal["empty", "scene_assets", "story"]
_ModelPlanStage = Literal["scene_assets", "story_beats", "cinematography"]


@dataclass(frozen=True, slots=True)
class VideoTaskAcceptance:
    """公开请求事务已经受理的任务身份，不承担队列投递职责。"""

    scene_id: str
    task_id: str
    replay_task: VideoGenerationTaskResponse | None = None


@dataclass(frozen=True, slots=True)
class VideoTaskDispatch:
    """后台 dispatcher 领取后交给 Agent 的不可变任务快照。"""

    user_id: str
    novel_id: str
    task_id: str
    job_id: str
    payload: VideoPlanJobPayload


@dataclass(frozen=True, slots=True)
class VideoAssetFile:
    """授权下载所需的最小文件定位信息。"""

    storage_key: str
    mime_type: str
    name: str


@dataclass(frozen=True, slots=True)
class VideoPromptPreviewContext:
    """共享编译器所需的正式场景和已校验素材选择。"""

    scene_plan: ScenePromptSpec
    selections: dict[str, str]
    resolved_slot_ids: tuple[str, ...]
    missing_slot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _VideoPlanReservationRecord:
    """保存在任务结果中的单次模型调用预留回执。"""

    event_id: str
    checkpoint_stage: _ActiveCheckpointStage
    stage: _ModelPlanStage
    reserved_calls_before: int


@dataclass(frozen=True, slots=True)
class _VideoPlanDurableProgress:
    """无需新增数据表即可随任务行原子更新的规划进度与调用账本。"""

    checkpoint_stage: _ActiveCheckpointStage
    scene_assets_plan: SceneAssetsStageArguments | None
    story_plan: StoryPlanStageArguments | None
    attempt_state: VideoPlanAttemptState
    reservations: tuple[_VideoPlanReservationRecord, ...]
    inherited_from_task_id: str | None
    inherited_input_fingerprint: str | None


class VideoRepository:
    """所有视频正式状态都在 Core 的数据库事务中读写。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        dispatch_namespace: str = "test",
    ) -> None:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?", dispatch_namespace):
            raise ValueError("视频调度命名空间无效")
        self._session_factory = session_factory
        self._dispatch_namespace = dispatch_namespace
        self._job_id_prefix = f"video-plan-{dispatch_namespace}-"

    def _plan_job_id(self, task_id: str) -> str:
        """为当前开发实例生成不可跨命名空间领取的稳定作业标识。"""

        return f"{self._job_id_prefix}{task_id}"

    async def create_project(
        self,
        user_id: str,
        novel_id: str,
        request: CreateVideoProjectRequest,
    ) -> VideoProjectResponse:
        """校验小说归属后创建视频项目。"""

        async with self._session_factory() as session:
            async with session.begin():
                owned = await session.scalar(
                    select(Novel.id).where(Novel.id == novel_id, Novel.userId == user_id)
                )
                if owned is None:
                    raise ApiError(status_code=404, code="NOVEL_NOT_FOUND", message="小说不存在")
                await _require_long_serial_novel(session, novel_id, lock=True)
                project = VideoProject(
                    novelId=novel_id,
                    title=request.title.strip(),
                    mode=request.mode,
                    targetAspectRatio=request.targetAspectRatio,
                    targetLanguage=request.targetLanguage,
                    updatedAt=utc_now(),
                )
                session.add(project)
                await session.flush()
                response = _project_response(project, scene_count=0)
        return response

    async def list_projects(self, user_id: str, novel_id: str) -> list[VideoProjectResponse]:
        """只返回当前用户小说下未软删除的项目。"""

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(VideoProject, func.count(VideoScene.id))
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .outerjoin(VideoScene, VideoScene.projectId == VideoProject.id)
                    .where(
                        Novel.userId == user_id,
                        VideoProject.novelId == novel_id,
                        VideoProject.deletedAt.is_(None),
                    )
                    .group_by(VideoProject.id)
                    .order_by(VideoProject.updatedAt.desc(), VideoProject.id)
                )
            ).all()
        return [_project_response(project, int(scene_count)) for project, scene_count in rows]

    async def get_project(
        self,
        user_id: str,
        project_id: str,
        *,
        preview_enabled: bool,
        seedance_configured: bool,
        seedance_enabled: bool,
    ) -> VideoProjectDetailResponse:
        """加载项目、场景、最新任务和当前审核草案。"""

        async with self._session_factory() as session:
            project = await _require_owned_project(session, user_id, project_id)
            scenes = (
                await session.scalars(
                    select(VideoScene)
                    .where(VideoScene.projectId == project_id)
                    .order_by(VideoScene.ordinal, VideoScene.id)
                )
            ).all()
            scene_responses = [await _scene_response(session, scene) for scene in scenes]
            assets = (
                await session.scalars(
                    select(VideoAsset)
                    .where(VideoAsset.projectId == project_id)
                    .order_by(VideoAsset.createdAt, VideoAsset.id)
                )
            ).all()
        return VideoProjectDetailResponse(
            project=_project_response(project, len(scenes)),
            scenes=scene_responses,
            assets=[_asset_response(asset) for asset in assets],
            previewEnabled=preview_enabled,
            seedanceConfigured=seedance_configured,
            seedanceEnabled=seedance_enabled,
        )

    async def require_project(self, user_id: str, project_id: str) -> None:
        """在文件写入前执行项目归属与长篇来源检查。"""

        async with self._session_factory() as session:
            await _require_owned_project(
                session,
                user_id,
                project_id,
                require_long_serial=True,
            )

    async def create_asset(
        self,
        user_id: str,
        project_id: str,
        asset_id: str,
        *,
        name: str,
        modality: str,
        duty: str,
        source_kind: str,
        stored: StoredVideoAsset,
    ) -> VideoAssetResponse:
        """把已安全落盘的媒体事实写入数据库。"""

        async with self._session_factory() as session:
            async with session.begin():
                await _require_owned_project(
                    session,
                    user_id,
                    project_id,
                    lock=True,
                    require_long_serial=True,
                )
                asset = VideoAsset(
                    id=asset_id,
                    projectId=project_id,
                    name=name.strip(),
                    modality=modality,
                    duty=duty,
                    storageKey=stored.storage_key,
                    mimeType=stored.mime_type,
                    byteSize=stored.byte_size,
                    durationMs=None,
                    sha256=stored.sha256,
                    sourceKind=source_kind,
                    rightsStatus="unconfirmed",
                    updatedAt=utc_now(),
                )
                session.add(asset)
                await session.flush()
                response = _asset_response(asset)
        return response

    async def confirm_asset(
        self,
        user_id: str,
        asset_id: str,
        rights_status: str,
    ) -> VideoAssetResponse:
        """只有 confirmed 会设置锁定时间；其他状态会解除锁定。"""

        async with self._session_factory() as session:
            async with session.begin():
                asset = await session.scalar(
                    select(VideoAsset)
                    .join(VideoProject, VideoProject.id == VideoAsset.projectId)
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .where(VideoAsset.id == asset_id, Novel.userId == user_id)
                    .with_for_update()
                )
                if asset is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_ASSET_NOT_FOUND",
                        message="视频素材不存在",
                    )
                await _require_long_serial_project_by_id(
                    session,
                    asset.projectId,
                    lock=True,
                )
                asset.rightsStatus = rights_status
                asset.lockedAt = utc_now() if rights_status == "confirmed" else None
                asset.updatedAt = utc_now()
                response = _asset_response(asset)
        return response

    async def get_asset_file(self, user_id: str, asset_id: str) -> VideoAssetFile:
        """下载前校验素材所属小说仍属于当前用户。"""

        async with self._session_factory() as session:
            asset = await session.scalar(
                select(VideoAsset)
                .join(VideoProject, VideoProject.id == VideoAsset.projectId)
                .join(Novel, Novel.id == VideoProject.novelId)
                .where(VideoAsset.id == asset_id, Novel.userId == user_id)
            )
            if asset is None:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_ASSET_NOT_FOUND",
                    message="视频素材不存在",
                )
            return VideoAssetFile(
                storage_key=asset.storageKey,
                mime_type=asset.mimeType,
                name=asset.name,
            )

    async def create_scene_task(
        self,
        user_id: str,
        project_id: str,
        request: CreateVideoSceneRequest,
    ) -> VideoTaskAcceptance:
        """在单个事务中冻结原文、创建场景并登记耐久规划任务。"""

        async with self._session_factory() as session:
            async with session.begin():
                project = await _require_owned_project(
                    session,
                    user_id,
                    project_id,
                    lock=True,
                    require_long_serial=True,
                )
                idempotency_key = _video_scene_create_idempotency_key(
                    user_id,
                    project_id,
                    request.clientRequestId,
                )
                existing_task = await session.scalar(
                    select(VideoGenerationTask)
                    .where(VideoGenerationTask.idempotencyKey == idempotency_key)
                    .with_for_update()
                )
                if existing_task is not None:
                    _validate_create_replay_payload(
                        existing_task,
                        project,
                        request,
                    )
                    return VideoTaskAcceptance(
                        scene_id=existing_task.sceneId,
                        task_id=existing_task.id,
                        replay_task=_task_response(existing_task),
                    )
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
                        code="CHAPTER_NOT_FOUND",
                        message="章节不存在或不属于当前小说",
                    )
                source_text = _validated_chapter_selection(chapter, request)
                if not source_text.strip():
                    raise ApiError(
                        status_code=400,
                        code="VIDEO_SOURCE_EMPTY",
                        message="视频场景来源不能为空",
                    )
                ordinal = (
                    int(
                        await session.scalar(
                            select(func.coalesce(func.max(VideoScene.ordinal), 0)).where(
                                VideoScene.projectId == project_id
                            )
                        )
                        or 0
                    )
                    + 1
                )
                scene = VideoScene(
                    projectId=project_id,
                    novelId=project.novelId,
                    chapterId=chapter.id,
                    ordinal=ordinal,
                    title=request.title.strip(),
                    sourceText=source_text,
                    sourceHash=hashlib.sha256(source_text.encode()).hexdigest(),
                    durationSeconds=request.durationSeconds,
                    status="generating",
                    updatedAt=utc_now(),
                )
                session.add(scene)
                await session.flush()
                task_id = generate_id()
                job_id = self._plan_job_id(task_id)
                try:
                    setting_snapshot = await build_long_serial_setting_snapshot(
                        session,
                        project.novelId,
                    )
                except ValueError as exc:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_SOURCE_SETTING_INVALID",
                        message="长篇资料库中存在无法冻结的设定，请先修复设定资料",
                    ) from exc
                payload = VideoPlanJobPayload(
                    projectId=project.id,
                    sceneId=scene.id,
                    chapterId=chapter.id,
                    title=scene.title,
                    sourceText=source_text,
                    durationSeconds=scene.durationSeconds,
                    ratio=cast(AspectRatio, project.targetAspectRatio),
                    settingSnapshot=setting_snapshot,
                    # 新任务显式冻结 Responses 主链；不能依赖历史兼容默认值。
                    planningRoute="responses_json_schema_v1",
                    # 1.4 由服务器固定原文事件动作槽，旧草案任务只能显式重试。
                    directorDraftVersion="1.4",
                )
                task = VideoGenerationTask(
                    id=task_id,
                    projectId=project.id,
                    sceneId=scene.id,
                    jobId=job_id,
                    kind="plan",
                    provider="deepseek",
                    status="pending",
                    idempotencyKey=idempotency_key,
                    requestJson=payload.model_dump_json(),
                    attemptCount=0,
                    updatedAt=utc_now(),
                )
                session.add(task)
                project.updatedAt = utc_now()
        return VideoTaskAcceptance(
            scene_id=scene.id,
            task_id=task_id,
        )

    async def retry_scene_task(self, user_id: str, scene_id: str) -> VideoTaskAcceptance:
        """复用最近失败任务的冻结输入，为同一场景登记一次新尝试。"""

        async with self._session_factory() as session:
            async with session.begin():
                scene = await session.scalar(
                    select(VideoScene)
                    .join(VideoProject, VideoProject.id == VideoScene.projectId)
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .where(VideoScene.id == scene_id, Novel.userId == user_id)
                    .with_for_update()
                )
                if scene is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_SCENE_NOT_FOUND",
                        message="视频场景不存在",
                    )
                project = await _require_owned_project(
                    session,
                    user_id,
                    scene.projectId,
                    lock=True,
                    require_long_serial=True,
                )
                if scene.status != "failed" or scene.planJson is not None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_SCENE_NOT_RETRYABLE",
                        message="只有尚无正式方案的失败场景可以重新生成",
                    )
                latest_task = await session.scalar(
                    select(VideoGenerationTask)
                    .where(VideoGenerationTask.sceneId == scene.id)
                    .order_by(
                        VideoGenerationTask.createdAt.desc(),
                        VideoGenerationTask.id.desc(),
                    )
                    .with_for_update()
                )
                if (
                    latest_task is None
                    or latest_task.kind != "plan"
                    or latest_task.status != "failed"
                ):
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_SCENE_NOT_RETRYABLE",
                        message="当前场景没有可重试的失败规划任务",
                    )
                source_payload = _validate_retry_payload(latest_task, scene, project)
                payload = _upgrade_video_planning_route(source_payload)
                inherited_progress_json = _retry_plan_progress_json(
                    latest_task,
                    source_payload=source_payload,
                    target_payload=payload,
                )
                task_count = int(
                    await session.scalar(
                        select(func.count(VideoGenerationTask.id)).where(
                            VideoGenerationTask.sceneId == scene.id
                        )
                    )
                    or 0
                )
                attempt_number = task_count + 1
                task_id = generate_id()
                job_id = self._plan_job_id(task_id)
                task = VideoGenerationTask(
                    id=task_id,
                    projectId=project.id,
                    sceneId=scene.id,
                    jobId=job_id,
                    kind="plan",
                    provider="deepseek",
                    status="pending",
                    idempotencyKey=f"video-plan:{scene.id}:{attempt_number}",
                    # 来源与设定快照逐字复用；新 task 显式升级传输协议，不在旧 task 内切换。
                    requestJson=payload.model_dump_json(),
                    resultJson=inherited_progress_json,
                    attemptCount=0,
                    updatedAt=utc_now(),
                )
                session.add(task)
                scene.status = "generating"
                scene.lastErrorCode = None
                scene.lastErrorMessage = None
                scene.updatedAt = utc_now()
                project.updatedAt = utc_now()
        return VideoTaskAcceptance(
            scene_id=scene.id,
            task_id=task_id,
        )

    async def revise_scene_task(
        self,
        user_id: str,
        scene_id: str,
        request: ReviseVideoSceneRequest,
    ) -> VideoTaskAcceptance:
        """快照待审候选，并用相同冻结输入登记一次幂等返工任务。"""

        async with self._session_factory() as session:
            async with session.begin():
                scene = await session.scalar(
                    select(VideoScene)
                    .join(VideoProject, VideoProject.id == VideoScene.projectId)
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .where(VideoScene.id == scene_id, Novel.userId == user_id)
                    .with_for_update()
                )
                if scene is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_SCENE_NOT_FOUND",
                        message="视频场景不存在",
                    )
                project = await _require_owned_project(
                    session,
                    user_id,
                    scene.projectId,
                    lock=True,
                    require_long_serial=True,
                )
                idempotency_key = f"video-revise:{scene.id}:{request.clientRequestId}"
                existing_task = await session.scalar(
                    select(VideoGenerationTask)
                    .where(VideoGenerationTask.idempotencyKey == idempotency_key)
                    .with_for_update()
                )
                if existing_task is not None:
                    _validate_revise_replay_payload(
                        existing_task,
                        scene,
                        project,
                        request.userMessage,
                    )
                    return VideoTaskAcceptance(
                        scene_id=existing_task.sceneId,
                        task_id=existing_task.id,
                        replay_task=_task_response(existing_task),
                    )
                if scene.status != "awaiting_review" or scene.planJson is not None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_SCENE_NOT_REVISABLE",
                        message="只有尚无正式方案的待审场景可以返工",
                    )
                artifact = await session.scalar(
                    select(ReviewArtifact)
                    .where(ReviewArtifact.videoSceneId == scene.id)
                    .order_by(
                        ReviewArtifact.revision.desc(),
                        ReviewArtifact.createdAt.desc(),
                    )
                    .with_for_update()
                )
                if artifact is None or artifact.status != "awaiting_user":
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_SCENE_NOT_AWAITING_REVIEW",
                        message="当前场景没有等待返工的候选方案",
                    )
                if artifact.revision != request.expectedArtifactRevision:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ARTIFACT_REVISION_CONFLICT",
                        message="视频候选版本已经变化，请刷新后再返工",
                        details={"currentRevision": artifact.revision},
                    )
                latest_task = await session.scalar(
                    select(VideoGenerationTask)
                    .where(VideoGenerationTask.sceneId == scene.id)
                    .order_by(
                        VideoGenerationTask.createdAt.desc(),
                        VideoGenerationTask.id.desc(),
                    )
                    .with_for_update()
                )
                if (
                    latest_task is None
                    or latest_task.kind != "plan"
                    or latest_task.status != "completed"
                ):
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_SCENE_NOT_REVISABLE",
                        message="当前候选没有可用于返工的已完成规划任务",
                    )
                _validate_artifact_matches_task(latest_task, artifact)
                revision_baseline = _revision_baseline_from_artifact(artifact, scene)
                base_payload = _validate_retry_payload(latest_task, scene, project)
                # 重新走共享契约校验，不能利用 model_copy 绕过返工意见长度与空白约束。
                payload = _upgrade_video_planning_route(
                    VideoPlanJobPayload.model_validate(
                        {
                            **base_payload.model_dump(mode="python"),
                            "revisionInstruction": request.userMessage,
                            "revisionBaseline": revision_baseline,
                        }
                    )
                )
                session.add(_artifact_revision_snapshot(artifact))
                artifact.status = "draft"
                artifact.updatedAt = utc_now()
                task_id = generate_id()
                job_id = self._plan_job_id(task_id)
                task = VideoGenerationTask(
                    id=task_id,
                    projectId=project.id,
                    sceneId=scene.id,
                    jobId=job_id,
                    kind="plan",
                    provider="deepseek",
                    status="pending",
                    idempotencyKey=idempotency_key,
                    requestJson=payload.model_dump_json(),
                    attemptCount=0,
                    updatedAt=utc_now(),
                )
                session.add(task)
                scene.status = "generating"
                scene.lastErrorCode = None
                scene.lastErrorMessage = None
                scene.updatedAt = utc_now()
                project.updatedAt = utc_now()
        return VideoTaskAcceptance(
            scene_id=scene.id,
            task_id=task_id,
        )

    async def mark_submitted(self, task_id: str) -> None:
        """记录 Redis 队列已接受任务，并延后下一次耐久对账。"""

        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoGenerationTask, task_id, with_for_update=True)
                if task is not None and task.status in _ACTIVE_VIDEO_PLAN_TASK_STATUSES:
                    now = utc_now()
                    if task.status == "pending":
                        task.status = "submitted"
                    if task.submittedAt is None:
                        task.submittedAt = now
                    task.nextAttemptAt = now + timedelta(minutes=10)
                    task.lastErrorCode = None
                    task.lastErrorMessage = None
                    task.updatedAt = now

    async def claim_due_plan_tasks(self, limit: int) -> list[VideoTaskDispatch]:
        """领取到期活动任务，并用短租约避免多个 Core worker 重复投递。"""

        if limit < 1:
            raise ValueError("视频任务领取数量必须为正整数")
        now = utc_now()
        lease_until = now + timedelta(seconds=30)
        async with self._session_factory() as session:
            async with session.begin():
                rows = (
                    await session.execute(
                        select(VideoGenerationTask, VideoProject, Novel.userId)
                        .join(
                            VideoProject,
                            VideoProject.id == VideoGenerationTask.projectId,
                        )
                        .join(Novel, Novel.id == VideoProject.novelId)
                        .where(
                            VideoGenerationTask.kind == "plan",
                            VideoGenerationTask.provider == "deepseek",
                            VideoGenerationTask.jobId.like(f"{self._job_id_prefix}%"),
                            VideoGenerationTask.status.in_(_ACTIVE_VIDEO_PLAN_TASK_STATUSES),
                            VideoGenerationTask.nextAttemptAt <= now,
                            VideoProject.deletedAt.is_(None),
                        )
                        .order_by(
                            VideoGenerationTask.nextAttemptAt,
                            VideoGenerationTask.createdAt,
                            VideoGenerationTask.id,
                        )
                        .limit(limit)
                        .with_for_update(of=VideoGenerationTask, skip_locked=True)
                    )
                ).all()
                records: list[VideoTaskDispatch] = []
                for task, project, user_id in rows:
                    scene = await session.get(VideoScene, task.sceneId, with_for_update=True)
                    try:
                        if scene is None:
                            raise ValueError("视频场景不存在")
                        payload = _validate_retry_payload(task, scene, project)
                    except (ApiError, ValueError) as exc:
                        _fail_dispatch_task(
                            task,
                            scene,
                            code="VIDEO_DISPATCH_INPUT_INVALID",
                            message=str(exc),
                        )
                        continue
                    task.nextAttemptAt = lease_until
                    task.updatedAt = utc_now()
                    records.append(
                        VideoTaskDispatch(
                            user_id=str(user_id),
                            novel_id=project.novelId,
                            task_id=task.id,
                            job_id=task.jobId,
                            payload=payload,
                        )
                    )
        return records

    async def record_dispatch_failure(
        self,
        task_id: str,
        error_code: str,
        *,
        transient: bool,
    ) -> None:
        """瞬时错误退避重试；确定性错误才终结任务和场景。"""

        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoGenerationTask, task_id, with_for_update=True)
                if task is None or task.status in {"completed", "failed", "cancelled"}:
                    return
                scene = await session.get(VideoScene, task.sceneId, with_for_update=True)
                if transient:
                    now = utc_now()
                    task.attemptCount += 1
                    task.status = "pending"
                    task.nextAttemptAt = now + _video_dispatch_backoff(task.attemptCount)
                    task.lastErrorCode = "VIDEO_AGENT_SUBMIT_RETRY"
                    task.lastErrorMessage = f"视频任务投递暂时失败：{error_code}"
                    task.completedAt = None
                    task.updatedAt = now
                    return
                _fail_dispatch_task(
                    task,
                    scene,
                    code="VIDEO_AGENT_SUBMIT_FAILED",
                    message=f"视频任务投递失败：{error_code}",
                )

    async def settle_dispatch_terminal(
        self,
        task_id: str,
        agent_status: AgentJobStatus,
    ) -> None:
        """Agent 队列已终态但 Core 未收到回调时形成稳定失败事实。"""

        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoGenerationTask, task_id, with_for_update=True)
                if task is None or task.status in {"completed", "failed", "cancelled"}:
                    return
                scene = await session.get(VideoScene, task.sceneId, with_for_update=True)
                _fail_dispatch_task(
                    task,
                    scene,
                    code="VIDEO_AGENT_TERMINAL_WITHOUT_CALLBACK",
                    message=f"Agent 队列已进入 {agent_status}，但 Core 尚未收到视频终态回调",
                    status="cancelled" if agent_status == "cancelled" else "failed",
                )

    async def get_plan_progress(
        self,
        query: VideoPlanProgressQuery,
    ) -> VideoPlanProgressResponse:
        """返回当前规划任务的耐久阶段；终态永不回显可续跑计划。"""

        async with self._session_factory() as session:
            async with session.begin():
                task, scene, project = await _require_callback_resources(
                    session,
                    query.taskId,
                )
                _validate_callback_binding(task, scene, project, query)
                _require_video_plan_task(task)
                await _require_current_scene_task(session, task, scene)
                await _require_long_serial_novel(
                    session,
                    project.novelId,
                    lock=True,
                )
                try:
                    frozen_payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
                except ValueError as exc:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_INPUT_INVALID",
                        message="视频规划任务的冻结输入已损坏，不能安全恢复",
                    ) from exc
                input_fingerprint = calculate_video_plan_input_fingerprint(frozen_payload)
                progress_status = _video_plan_progress_status(task)
                if progress_status == "active":
                    now = utc_now()
                    task.status = "processing"
                    task.nextAttemptAt = now + timedelta(minutes=10)
                    task.updatedAt = now
                    durable = _load_active_plan_progress(task.resultJson)
                    checkpoint_stage: Literal["empty", "scene_assets", "story", "terminal"] = (
                        durable.checkpoint_stage
                    )
                    scene_assets_plan = durable.scene_assets_plan
                    story_plan = durable.story_plan
                    attempt_state = durable.attempt_state
                else:
                    checkpoint_stage = "terminal"
                    scene_assets_plan = None
                    story_plan = None
                    attempt_state = _terminal_attempt_state(task.resultJson)

        return VideoPlanProgressResponse(
            protocolVersion="1.0",
            jobId=query.jobId,
            runId=query.runId,
            taskId=query.taskId,
            novelId=query.novelId,
            projectId=query.projectId,
            sceneId=query.sceneId,
            inputFingerprint=input_fingerprint,
            status=progress_status,
            checkpointStage=checkpoint_stage,
            sceneAssetsPlan=scene_assets_plan,
            storyPlan=story_plan,
            attemptState=attempt_state,
        )

    async def reserve_plan_call(
        self,
        request: VideoPlanCallReservationRequest,
    ) -> VideoPlanCallReservationResponse:
        """在任务行锁内幂等预留一次供应商调用并持久化 pending。"""

        async with self._session_factory() as session:
            async with session.begin():
                task, scene, project = await _require_callback_resources(
                    session,
                    request.taskId,
                )
                _validate_callback_binding(task, scene, project, request)
                _require_video_plan_task(task)
                await _require_current_scene_task(session, task, scene)
                await _require_long_serial_novel(
                    session,
                    project.novelId,
                    lock=True,
                )
                _require_active_video_plan_task(task)
                durable = _load_active_plan_progress(task.resultJson)

                replay = next(
                    (
                        record
                        for record in durable.reservations
                        if record.event_id == request.eventId
                    ),
                    None,
                )
                if replay is not None:
                    if (
                        replay.checkpoint_stage != request.checkpointStage
                        or replay.stage != request.stage
                        or replay.reserved_calls_before != request.expectedReservedCalls
                        or request.inheritedCalls != durable.attempt_state.inheritedCalls
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_PLAN_RESERVATION_EVENT_CONFLICT",
                            message="同一模型调用预留事件不能绑定不同请求",
                        )
                    return _reservation_response(request, replay)

                if durable.checkpoint_stage != request.checkpointStage:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_RESERVATION_STAGE_CONFLICT",
                        message="视频规划检查点阶段已经变化，请重新读取进度",
                    )
                if durable.attempt_state.reservedCalls != request.expectedReservedCalls:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_RESERVATION_COUNT_CONFLICT",
                        message="视频规划模型调用计数已经变化，请重新读取进度",
                    )
                if durable.attempt_state.inheritedCalls != request.inheritedCalls:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_RESERVATION_INHERITANCE_CONFLICT",
                        message="视频规划继承调用基线已经变化，请重新读取进度",
                    )
                if (
                    durable.attempt_state.reservedCalls
                    + durable.attempt_state.inheritedCalls
                    >= VIDEO_PLAN_MAX_EFFECTIVE_CALLS
                ):
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_CALL_BUDGET_EXHAUSTED",
                        message="视频规划模型调用预算已经耗尽",
                    )

                record = _VideoPlanReservationRecord(
                    event_id=request.eventId,
                    checkpoint_stage=request.checkpointStage,
                    stage=request.stage,
                    reserved_calls_before=request.expectedReservedCalls,
                )
                response = _reservation_response(request, record)
                updated = _VideoPlanDurableProgress(
                    checkpoint_stage=durable.checkpoint_stage,
                    scene_assets_plan=durable.scene_assets_plan,
                    story_plan=durable.story_plan,
                    attempt_state=response.attemptState,
                    reservations=(*durable.reservations, record),
                    inherited_from_task_id=durable.inherited_from_task_id,
                    inherited_input_fingerprint=durable.inherited_input_fingerprint,
                )
                task.status = "processing"
                task.resultJson = _plan_progress_json(updated)
                task.nextAttemptAt = utc_now() + timedelta(minutes=10)
                task.updatedAt = utc_now()
                return response

    async def save_story_plan_checkpoint(
        self,
        callback: VideoStoryPlanCheckpointCallback,
    ) -> None:
        """幂等推进 canonical 阶段，并在同一更新中清除当前 pending。"""

        async with self._session_factory() as session:
            async with session.begin():
                task, scene, project = await _require_callback_resources(
                    session,
                    callback.taskId,
                )
                _validate_callback_binding(task, scene, project, callback)
                _require_video_plan_task(task)
                await _require_current_scene_task(session, task, scene)
                await _require_long_serial_novel(
                    session,
                    project.novelId,
                    lock=True,
                )
                _require_active_video_plan_task(task)
                durable = _load_active_plan_progress(task.resultJson)
                callback_progress = _progress_from_checkpoint_callback(
                    callback,
                    reservations=durable.reservations,
                    inherited_from_task_id=durable.inherited_from_task_id,
                    inherited_input_fingerprint=durable.inherited_input_fingerprint,
                )

                if callback.checkpointStage == durable.checkpoint_stage:
                    if callback_progress == durable:
                        return
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_CHECKPOINT_CONFLICT",
                        message="同一视频规划阶段不能覆盖不同的检查点内容",
                    )

                _validate_checkpoint_advance(durable, callback_progress)
                task.status = "processing"
                task.resultJson = _plan_progress_json(callback_progress)
                task.nextAttemptAt = utc_now() + timedelta(minutes=10)
                task.updatedAt = utc_now()

    async def complete_plan(self, callback: VideoPlanCompletionCallback) -> None:
        """幂等创建或更新视频 ReviewArtifact，正式方案仍等待用户批准。"""

        async with self._session_factory() as session:
            async with session.begin():
                task, scene, project = await _require_callback_resources(
                    session,
                    callback.taskId,
                )
                _validate_callback_binding(task, scene, project, callback)
                _require_video_plan_task(task)
                await _require_current_scene_task(session, task, scene)
                payload = _completion_result(callback, scene.id)
                if task.status == "completed":
                    _require_matching_terminal_callback(
                        task,
                        status="completed",
                        event_id=callback.eventId,
                        result=payload,
                    )
                    return
                if task.status == "failed":
                    raise _terminal_callback_conflict()
                if task.status not in _ACTIVE_VIDEO_PLAN_TASK_STATUSES:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_TASK_NOT_ACTIVE",
                        message="视频规划任务已经进入终态，不能再保存成功候选",
                    )
                await _require_long_serial_novel(
                    session,
                    project.novelId,
                    lock=True,
                )
                _validate_plan_against_frozen_snapshot(task, callback.scenePlan)
                if not callback.promptPackage.previewOnly or callback.promptPackage.submissionReady:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PREVIEW_PACKAGE_REQUIRED",
                        message="结构冻结期只接受禁止供应商提交的开发预览包",
                    )
                payload_json = json.dumps(payload, ensure_ascii=False)
                terminal_result_json = _encode_terminal_callback_result(
                    task.resultJson,
                    status="completed",
                    event_id=callback.eventId,
                    result=payload,
                )
                job_payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
                artifact = await session.scalar(
                    select(ReviewArtifact)
                    .where(ReviewArtifact.videoSceneId == scene.id)
                    .order_by(
                        ReviewArtifact.revision.desc(),
                        ReviewArtifact.createdAt.desc(),
                    )
                    .with_for_update()
                )
                if job_payload.revisionInstruction is None:
                    if artifact is not None:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_ARTIFACT_ALREADY_EXISTS",
                            message="视频场景已经存在候选方案",
                        )
                    artifact = ReviewArtifact(
                        novelId=callback.novelId,
                        chapterId=scene.chapterId,
                        taskId=None,
                        workflowRunId=None,
                        videoSceneId=scene.id,
                        artifactKey=f"video-scene:{scene.id}",
                        kind="video_scene_plan",
                        status="awaiting_user",
                        title=f"视频场景方案：{scene.title}",
                        summary=callback.scenePlan.summary,
                        payloadJson=payload_json,
                        createdByAgent="剧情",
                        updatedByAgent="剧情",
                        revision=1,
                        updatedAt=utc_now(),
                    )
                    session.add(artifact)
                else:
                    if artifact is None or artifact.status != "draft":
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_REVISE_ARTIFACT_NOT_DRAFT",
                            message="返工任务没有可更新的草稿候选",
                        )
                    history_revision_id = await session.scalar(
                        select(ReviewArtifactRevision.id).where(
                            ReviewArtifactRevision.artifactId == artifact.id,
                            ReviewArtifactRevision.revision == artifact.revision,
                        )
                    )
                    if history_revision_id is None:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_REVISE_HISTORY_MISSING",
                            message="返工前候选缺少历史快照，不能覆盖",
                        )
                    _apply_revised_artifact(
                        artifact,
                        scene_title=scene.title,
                        summary=callback.scenePlan.summary,
                        payload_json=payload_json,
                    )
                task.status = "completed"
                task.resultJson = terminal_result_json
                task.completedAt = utc_now()
                task.updatedAt = utc_now()
                scene.status = "awaiting_review"
                scene.lastErrorCode = None
                scene.lastErrorMessage = None
                scene.updatedAt = utc_now()

    async def fail_plan(self, callback: VideoPlanFailureCallback) -> None:
        """幂等保存 Agent 失败，完整错误信息不做静默截断。"""

        async with self._session_factory() as session:
            async with session.begin():
                task, scene, project = await _require_callback_resources(
                    session,
                    callback.taskId,
                )
                _validate_callback_binding(task, scene, project, callback)
                _require_video_plan_task(task)
                await _require_current_scene_task(session, task, scene)
                result = _failure_result(callback)
                if task.status == "failed":
                    _require_matching_terminal_callback(
                        task,
                        status="failed",
                        event_id=callback.eventId,
                        result=result,
                    )
                    return
                if task.status == "completed":
                    raise _terminal_callback_conflict()
                if task.status not in _ACTIVE_VIDEO_PLAN_TASK_STATUSES:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PLAN_TASK_NOT_ACTIVE",
                        message="视频规划任务已经进入终态，不能再保存失败结果",
                    )
                await _require_long_serial_novel(
                    session,
                    project.novelId,
                    lock=True,
                )
                if _is_refundable_video_plan_failure(callback):
                    await _refund_failed_video_plan(
                        session,
                        task=task,
                        novel_id=project.novelId,
                    )
                task.resultJson = _encode_terminal_callback_result(
                    task.resultJson,
                    status="failed",
                    event_id=callback.eventId,
                    result=result,
                )
                task.status = "failed"
                task.lastErrorCode = callback.code
                task.lastErrorMessage = callback.message
                task.completedAt = utc_now()
                task.updatedAt = utc_now()
                scene.status = "failed"
                scene.lastErrorCode = callback.code
                scene.lastErrorMessage = callback.message
                scene.updatedAt = utc_now()

    async def approve_scene(
        self,
        user_id: str,
        scene_id: str,
        request: ApproveVideoSceneRequest,
    ) -> ApproveVideoSceneResponse:
        """按请求键和候选 revision 原子批准，并耐久保存首次完整结果。"""

        async with self._session_factory() as session:
            async with session.begin():
                request_hash = _video_review_decision_request_hash(
                    scene_id,
                    request.expectedArtifactRevision,
                )
                await _lock_video_review_decision_request(
                    session,
                    user_id,
                    request.clientRequestId,
                )
                existing_command = await session.scalar(
                    select(VideoReviewDecisionCommand)
                    .where(
                        VideoReviewDecisionCommand.requestedByUserId == user_id,
                        VideoReviewDecisionCommand.clientRequestId == request.clientRequestId,
                    )
                    .with_for_update()
                )
                if existing_command is not None:
                    return _approval_response_from_command(
                        existing_command,
                        user_id=user_id,
                        scene_id=scene_id,
                        expected_artifact_revision=request.expectedArtifactRevision,
                        request_hash=request_hash,
                    )

                scene, artifact, source_task = await _require_video_approval_context(
                    session,
                    user_id=user_id,
                    scene_id=scene_id,
                    expected_artifact_revision=request.expectedArtifactRevision,
                )
                approved_at = utc_now()

                if artifact.status == "applied":
                    response, result_json = await _replay_applied_video_approval(
                        session,
                        user_id=user_id,
                        scene=scene,
                        artifact=artifact,
                        source_task=source_task,
                        request_hash=request_hash,
                    )
                else:
                    _apply_video_approval_candidate(
                        scene,
                        artifact,
                        approved_at=approved_at,
                    )
                    await session.flush()
                    response = ApproveVideoSceneResponse(
                        scene=await _scene_response(session, scene)
                    )
                    result_json = response.model_dump_json()

                session.add(
                    _video_review_decision_command(
                        user_id=user_id,
                        scene=scene,
                        artifact=artifact,
                        source_task=source_task,
                        request=request,
                        request_hash=request_hash,
                        result_json=result_json,
                        completed_at=approved_at,
                    )
                )
                await session.flush()
                return response

    async def get_scene(self, user_id: str, scene_id: str) -> VideoSceneResponse:
        """供前端轮询单个场景状态。"""

        async with self._session_factory() as session:
            scene = await session.scalar(
                select(VideoScene)
                .join(VideoProject, VideoProject.id == VideoScene.projectId)
                .join(Novel, Novel.id == VideoProject.novelId)
                .where(VideoScene.id == scene_id, Novel.userId == user_id)
            )
            if scene is None:
                raise ApiError(
                    status_code=404, code="VIDEO_SCENE_NOT_FOUND", message="视频场景不存在"
                )
            return await _scene_response(session, scene)

    async def prepare_prompt_preview(
        self,
        user_id: str,
        scene_id: str,
        request: PromptPreviewRequest,
    ) -> VideoPromptPreviewContext:
        """从正式 planJson 解析全部素材槽位，对已锁定素材做无持久化校验。"""

        async with self._session_factory() as session:
            scene = await session.scalar(
                select(VideoScene)
                .join(VideoProject, VideoProject.id == VideoScene.projectId)
                .join(Novel, Novel.id == VideoProject.novelId)
                .where(VideoScene.id == scene_id, Novel.userId == user_id)
            )
            if scene is None:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_SCENE_NOT_FOUND",
                    message="视频场景不存在",
                )
            await _require_long_serial_project_by_id(
                session,
                scene.projectId,
                lock=False,
            )
            if scene.status != "approved" or scene.planJson is None:
                raise ApiError(
                    status_code=409,
                    code="VIDEO_SCENE_NOT_APPROVED",
                    message="提示词预览只能使用已批准的正式场景方案",
                )
            try:
                scene_plan = ScenePromptSpec.model_validate_json(scene.planJson)
            except ValueError as exc:
                raise ApiError(
                    status_code=409,
                    code="VIDEO_APPROVED_PLAN_INVALID",
                    message="已批准场景方案无法安全编译",
                ) from exc

            prompt_slots = {asset.assetId: asset for asset in scene_plan.assets}
            requested = {binding.slotId: binding.assetId for binding in request.previewBindings}
            unknown_slot_ids = set(requested) - set(prompt_slots)
            if unknown_slot_ids:
                raise ApiError(
                    status_code=422,
                    code="VIDEO_PROMPT_SLOT_NOT_FOUND",
                    message="预览请求包含当前正式方案不存在的素材槽位",
                    details=cast(JsonValue, {"slotIds": sorted(unknown_slot_ids)}),
                )

            selected_asset_ids = set(requested.values())
            assets: list[VideoAsset] = []
            if selected_asset_ids:
                assets = list(
                    (
                        await session.scalars(
                            select(VideoAsset).where(
                                VideoAsset.projectId == scene.projectId,
                                VideoAsset.id.in_(selected_asset_ids),
                            )
                        )
                    ).all()
                )
            assets_by_id = {asset.id: asset for asset in assets}
            missing_asset_ids = selected_asset_ids - set(assets_by_id)
            if missing_asset_ids:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_PREVIEW_ASSET_NOT_FOUND",
                    message="预览素材不存在或不属于当前项目",
                )

            for slot_id, asset_id in requested.items():
                slot = prompt_slots[slot_id]
                asset = assets_by_id[asset_id]
                if asset.lockedAt is None or asset.rightsStatus != "confirmed":
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_ASSET_NOT_LOCKED",
                        message="预览素材必须先确认权利并锁定",
                        details={"slotId": slot_id, "assetId": asset_id},
                    )
                if asset.modality != slot.modality:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PROMPT_ASSET_MODALITY_MISMATCH",
                        message="素材模态与正式方案槽位不匹配",
                        details={"slotId": slot_id, "assetId": asset_id},
                    )
                if not _preview_duty_matches(slot.duty, asset.duty):
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_PROMPT_ASSET_DUTY_MISMATCH",
                        message="素材职责与正式方案槽位不匹配",
                        details={"slotId": slot_id, "assetId": asset_id},
                    )

            ordered_slot_ids = [asset.assetId for asset in scene_plan.assets]
            resolved_slot_ids = tuple(
                slot_id for slot_id in ordered_slot_ids if slot_id in requested
            )
            missing_slot_ids = tuple(
                slot_id for slot_id in ordered_slot_ids if slot_id not in requested
            )
            return VideoPromptPreviewContext(
                scene_plan=scene_plan,
                selections=requested,
                resolved_slot_ids=resolved_slot_ids,
                missing_slot_ids=missing_slot_ids,
            )


def _preview_duty_matches(planned_duty: str, stored_duty: str) -> bool:
    """关系交互是规划职责；旧表无此枚举，预览期用图片 keyframe 显式兼容。"""

    if planned_duty == "relation_interaction":
        return stored_duty == "keyframe"
    return stored_duty == planned_duty


async def _require_owned_project(
    session: AsyncSession,
    user_id: str,
    project_id: str,
    *,
    lock: bool = False,
    require_long_serial: bool = False,
) -> VideoProject:
    """统一执行项目归属和软删除校验。"""

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
        statement = statement.with_for_update()
    project = await session.scalar(statement)
    if project is None:
        raise ApiError(status_code=404, code="VIDEO_PROJECT_NOT_FOUND", message="视频项目不存在")
    if require_long_serial:
        await _require_long_serial_novel(session, project.novelId, lock=lock)
        _require_preview_project_mode(project)
    return project


async def _require_long_serial_project_by_id(
    session: AsyncSession,
    project_id: str,
    *,
    lock: bool,
) -> None:
    """对已经完成归属检查的写操作复核项目的长篇来源。"""

    project = await session.get(VideoProject, project_id)
    if project is None or project.deletedAt is not None:
        raise ApiError(
            status_code=404,
            code="VIDEO_PROJECT_NOT_FOUND",
            message="视频项目不存在",
        )
    await _require_long_serial_novel(session, project.novelId, lock=lock)
    _require_preview_project_mode(project)


def _require_preview_project_mode(project: VideoProject) -> None:
    """旧 Scene 预览只服务试制项目；series 必须进入独立章节改编域。"""

    if project.mode not in _PREVIEW_PROJECT_MODES:
        raise ApiError(
            status_code=409,
            code="VIDEO_PREVIEW_MODE_REQUIRED",
            message="旧场景预览仅支持概念片、预告片和高光片段项目",
        )


async def _require_long_serial_novel(
    session: AsyncSession,
    novel_id: str,
    *,
    lock: bool,
) -> None:
    """以 WritingBible 为唯一篇幅事实，稳定拒绝非长篇视频写入。"""

    statement = select(WritingBible).where(WritingBible.novelId == novel_id)
    if lock:
        statement = statement.with_for_update()
    writing_bible = await session.scalar(statement)
    if writing_bible is None or writing_bible.storyLengthProfile != "long_serial":
        raise ApiError(
            status_code=409,
            code="VIDEO_LONG_SERIAL_REQUIRED",
            message="视频制作仅支持长篇连载小说",
            details={"requiredProfile": "long_serial"},
        )


async def _require_callback_resources(
    session: AsyncSession,
    task_id: str,
) -> tuple[VideoGenerationTask, VideoScene, VideoProject]:
    """锁定回调关联的任务和场景，避免并发成功/失败互相覆盖。"""

    task = await session.get(VideoGenerationTask, task_id, with_for_update=True)
    if task is None:
        raise ApiError(status_code=404, code="VIDEO_TASK_NOT_FOUND", message="视频任务不存在")
    scene = await session.get(VideoScene, task.sceneId, with_for_update=True)
    if scene is None:
        raise ApiError(status_code=404, code="VIDEO_SCENE_NOT_FOUND", message="视频场景不存在")
    project = await session.get(VideoProject, task.projectId, with_for_update=True)
    if project is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_PROJECT_NOT_FOUND",
            message="视频项目不存在",
        )
    return task, scene, project


def _require_video_plan_task(task: VideoGenerationTask) -> None:
    """阶段进度只属于 DeepSeek 场景规划任务，不能复用到生成任务。"""

    if task.kind != "plan" or task.provider != "deepseek":
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_TASK_REQUIRED",
            message="当前任务不是 DeepSeek 视频场景规划任务",
        )


def _require_active_video_plan_task(task: VideoGenerationTask) -> None:
    """模型调用预留与阶段推进只能修改活动任务。"""

    if task.status not in _ACTIVE_VIDEO_PLAN_TASK_STATUSES:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_TASK_NOT_ACTIVE",
            message="只有活动中的视频规划任务可以继续执行",
        )


def _video_plan_progress_status(
    task: VideoGenerationTask,
) -> Literal["active", "completed", "failed"]:
    """把数据库任务状态投影为共享进度契约中的三个稳定状态。"""

    if task.status in _ACTIVE_VIDEO_PLAN_TASK_STATUSES:
        return "active"
    if task.status == "completed":
        return "completed"
    if task.status == "failed":
        return "failed"
    raise ApiError(
        status_code=409,
        code="VIDEO_PLAN_PROGRESS_STATUS_INVALID",
        message="当前视频规划任务状态不能恢复或继续执行",
    )


def _empty_plan_progress() -> _VideoPlanDurableProgress:
    """返回尚未预留任何供应商调用的初始耐久状态。"""

    return _VideoPlanDurableProgress(
        checkpoint_stage="empty",
        scene_assets_plan=None,
        story_plan=None,
        attempt_state=VideoPlanAttemptState(reservedCalls=0, pendingStage=None),
        reservations=(),
        inherited_from_task_id=None,
        inherited_input_fingerprint=None,
    )


def _plan_progress_json(progress: _VideoPlanDurableProgress) -> str:
    """把阶段、计划与最多四项预留账本编码成稳定判别式 JSON。"""

    _validate_durable_progress(progress)
    return json.dumps(
        {
            "kind": _PLAN_PROGRESS_CHECKPOINT_KIND,
            "schemaVersion": _PLAN_PROGRESS_CHECKPOINT_VERSION,
            "checkpointStage": progress.checkpoint_stage,
            "sceneAssetsPlan": (
                progress.scene_assets_plan.model_dump(mode="json")
                if progress.scene_assets_plan is not None
                else None
            ),
            "storyPlan": (
                progress.story_plan.model_dump(mode="json")
                if progress.story_plan is not None
                else None
            ),
            "attemptState": progress.attempt_state.model_dump(mode="json"),
            "inheritedFromTaskId": progress.inherited_from_task_id,
            "inheritedInputFingerprint": progress.inherited_input_fingerprint,
            "reservations": [
                {
                    "eventId": record.event_id,
                    "checkpointStage": record.checkpoint_stage,
                    "stage": record.stage,
                    "reservedCallsBefore": record.reserved_calls_before,
                }
                for record in progress.reservations
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _load_active_plan_progress(result_json: str | None) -> _VideoPlanDurableProgress:
    """严格读取活动任务进度；损坏账本不能被当成空状态重复计费。"""

    if result_json is None:
        return _empty_plan_progress()
    try:
        value = json.loads(result_json)
        if not isinstance(value, dict):
            raise ValueError("进度检查点顶层不是对象")
        schema_version = value.get("schemaVersion")
        legacy_keys = {
            "kind",
            "schemaVersion",
            "checkpointStage",
            "sceneAssetsPlan",
            "storyPlan",
            "attemptState",
            "reservations",
        }
        current_keys = legacy_keys | {
            "inheritedFromTaskId",
            "inheritedInputFingerprint",
        }
        expected_keys = (
            legacy_keys
            if schema_version == _LEGACY_PLAN_PROGRESS_CHECKPOINT_VERSION
            else current_keys
        )
        if set(value) != expected_keys:
            raise ValueError("进度检查点顶层字段不完整")
        if value["kind"] != _PLAN_PROGRESS_CHECKPOINT_KIND:
            raise ValueError("进度检查点判别类型不匹配")
        if schema_version not in {
            _LEGACY_PLAN_PROGRESS_CHECKPOINT_VERSION,
            _PLAN_PROGRESS_CHECKPOINT_VERSION,
        }:
            raise ValueError("进度检查点版本不受支持")
        checkpoint_stage_value = value["checkpointStage"]
        if checkpoint_stage_value not in {"empty", "scene_assets", "story"}:
            raise ValueError("进度检查点阶段无效")
        checkpoint_stage = cast(_ActiveCheckpointStage, checkpoint_stage_value)
        scene_assets_plan = (
            SceneAssetsStageArguments.model_validate(value["sceneAssetsPlan"])
            if value["sceneAssetsPlan"] is not None
            else None
        )
        story_plan = (
            StoryPlanStageArguments.model_validate(value["storyPlan"])
            if value["storyPlan"] is not None
            else None
        )
        attempt_state = VideoPlanAttemptState.model_validate(value["attemptState"])
        inherited_from_task_id = (
            None
            if schema_version == _LEGACY_PLAN_PROGRESS_CHECKPOINT_VERSION
            else value["inheritedFromTaskId"]
        )
        inherited_input_fingerprint = (
            None
            if schema_version == _LEGACY_PLAN_PROGRESS_CHECKPOINT_VERSION
            else value["inheritedInputFingerprint"]
        )
        if inherited_from_task_id is not None and (
            not isinstance(inherited_from_task_id, str) or not inherited_from_task_id
        ):
            raise ValueError("继承来源任务标识无效")
        if inherited_input_fingerprint is not None and (
            not isinstance(inherited_input_fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", inherited_input_fingerprint) is None
        ):
            raise ValueError("继承业务输入指纹无效")
        raw_reservations = value["reservations"]
        if not isinstance(raw_reservations, list):
            raise ValueError("模型调用预留账本不是数组")
        reservations: list[_VideoPlanReservationRecord] = []
        for index, raw_record in enumerate(raw_reservations):
            if not isinstance(raw_record, dict) or set(raw_record) != {
                "eventId",
                "checkpointStage",
                "stage",
                "reservedCallsBefore",
            }:
                raise ValueError("模型调用预留记录字段不完整")
            response = VideoPlanCallReservationResponse.model_validate(
                {
                    "protocolVersion": "1.0",
                    "eventId": raw_record["eventId"],
                    "jobId": "durable-job",
                    "runId": "durable-run",
                    "taskId": "durable-task",
                    "novelId": "durable-novel",
                    "projectId": "durable-project",
                    "sceneId": "durable-scene",
                    "checkpointStage": raw_record["checkpointStage"],
                    "stage": raw_record["stage"],
                    "reservedCallsBefore": raw_record["reservedCallsBefore"],
                    "attemptState": {
                        "reservedCalls": raw_record["reservedCallsBefore"] + 1,
                        "inheritedCalls": attempt_state.inheritedCalls,
                        "pendingStage": raw_record["stage"],
                    },
                }
            )
            if response.reservedCallsBefore != index:
                raise ValueError("模型调用预留账本计数不连续")
            reservations.append(
                _VideoPlanReservationRecord(
                    event_id=response.eventId,
                    checkpoint_stage=response.checkpointStage,
                    stage=response.stage,
                    reserved_calls_before=response.reservedCallsBefore,
                )
            )
        progress = _VideoPlanDurableProgress(
            checkpoint_stage=checkpoint_stage,
            scene_assets_plan=scene_assets_plan,
            story_plan=story_plan,
            attempt_state=attempt_state,
            reservations=tuple(reservations),
            inherited_from_task_id=inherited_from_task_id,
            inherited_input_fingerprint=inherited_input_fingerprint,
        )
        _validate_durable_progress(progress)
    except (TypeError, ValueError) as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_PROGRESS_CHECKPOINT_INVALID",
            message="视频规划进度或调用账本已损坏，不能安全恢复",
        ) from exc
    return progress


def _validate_durable_progress(progress: _VideoPlanDurableProgress) -> None:
    """用共享契约复核阶段载荷，并确保预留事件与计数一一对应。"""

    VideoPlanProgressResponse(
        protocolVersion="1.0",
        jobId="durable-job",
        runId="durable-run",
        taskId="durable-task",
        novelId="durable-novel",
        projectId="durable-project",
        sceneId="durable-scene",
        inputFingerprint="0" * 64,
        status="active",
        checkpointStage=progress.checkpoint_stage,
        sceneAssetsPlan=progress.scene_assets_plan,
        storyPlan=progress.story_plan,
        attemptState=progress.attempt_state,
    )
    if len(progress.reservations) != progress.attempt_state.reservedCalls:
        raise ValueError("模型调用预留事件数量与 reservedCalls 不一致")
    event_ids = [record.event_id for record in progress.reservations]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("模型调用预留 eventId 不能重复")
    if len(progress.reservations) > VIDEO_PLAN_MAX_EFFECTIVE_CALLS:
        raise ValueError("模型调用预留账本超过五次上限")
    provenance = (
        progress.inherited_from_task_id,
        progress.inherited_input_fingerprint,
    )
    if progress.attempt_state.inheritedCalls == 0:
        if provenance != (None, None):
            raise ValueError("没有继承调用基线时不能携带 checkpoint 来源")
    elif None in provenance:
        raise ValueError("继承 checkpoint 必须同时记录来源任务和业务输入指纹")


def _reservation_response(
    request: VideoPlanCallReservationRequest,
    record: _VideoPlanReservationRecord,
) -> VideoPlanCallReservationResponse:
    """从耐久记录重建首次和幂等重放完全一致的预留回执。"""

    return VideoPlanCallReservationResponse(
        protocolVersion="1.0",
        eventId=record.event_id,
        jobId=request.jobId,
        runId=request.runId,
        taskId=request.taskId,
        novelId=request.novelId,
        projectId=request.projectId,
        sceneId=request.sceneId,
        checkpointStage=record.checkpoint_stage,
        stage=record.stage,
        reservedCallsBefore=record.reserved_calls_before,
        attemptState=VideoPlanAttemptState(
            reservedCalls=record.reserved_calls_before + 1,
            inheritedCalls=request.inheritedCalls,
            pendingStage=record.stage,
        ),
    )


def _progress_from_checkpoint_callback(
    callback: VideoStoryPlanCheckpointCallback,
    *,
    reservations: tuple[_VideoPlanReservationRecord, ...],
    inherited_from_task_id: str | None,
    inherited_input_fingerprint: str | None,
) -> _VideoPlanDurableProgress:
    """把已由共享契约验证的回调投影为不含事件噪声的持久状态。"""

    progress = _VideoPlanDurableProgress(
        checkpoint_stage=callback.checkpointStage,
        scene_assets_plan=callback.sceneAssetsPlan,
        story_plan=callback.storyPlan,
        attempt_state=callback.attemptState,
        reservations=reservations,
        inherited_from_task_id=inherited_from_task_id,
        inherited_input_fingerprint=inherited_input_fingerprint,
    )
    try:
        _validate_durable_progress(progress)
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_CHECKPOINT_ATTEMPT_CONFLICT",
            message="阶段检查点与已预留模型调用账本不一致",
        ) from exc
    return progress


def _validate_checkpoint_advance(
    current: _VideoPlanDurableProgress,
    target: _VideoPlanDurableProgress,
) -> None:
    """只允许完成当前 pending 所指阶段，并向下一个 canonical 阶段推进。"""

    ranks = {"empty": 0, "scene_assets": 1, "story": 2}
    if ranks[target.checkpoint_stage] != ranks[current.checkpoint_stage] + 1:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_CHECKPOINT_TRANSITION_INVALID",
            message="视频规划检查点只能按阶段单向推进一次",
        )
    expected_pending: dict[_ActiveCheckpointStage, _ModelPlanStage | None] = {
        "empty": "scene_assets",
        "scene_assets": "story_beats",
        "story": None,
    }
    if current.attempt_state.pendingStage != expected_pending[current.checkpoint_stage]:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_CHECKPOINT_PENDING_MISMATCH",
            message="阶段检查点没有匹配的待确认模型调用",
        )
    if (
        target.attempt_state.reservedCalls != current.attempt_state.reservedCalls
        or target.attempt_state.inheritedCalls != current.attempt_state.inheritedCalls
        or target.attempt_state.pendingStage is not None
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_CHECKPOINT_ATTEMPT_CONFLICT",
            message="阶段成功只能清除 pending，不能改变模型调用计数",
        )
    if target.checkpoint_stage == "story":
        if current.scene_assets_plan is None or target.story_plan is None:
            raise ApiError(
                status_code=409,
                code="VIDEO_PLAN_CHECKPOINT_INPUT_MISSING",
                message="故事阶段缺少已冻结的场景素材规范",
            )
        _require_story_preserves_scene_assets(
            current.scene_assets_plan,
            target.story_plan,
        )


def _require_story_preserves_scene_assets(
    scene_assets: SceneAssetsStageArguments,
    story: StoryPlanStageArguments,
) -> None:
    """故事阶段只能增加 beats，不能覆盖第一阶段已经冻结的事实。"""

    frozen_fields = (
        "title",
        "summary",
        "dramaticArc",
        "visualStyle",
        "globalDirection",
        "assets",
        "negativeConstraints",
    )
    if any(
        getattr(scene_assets, field_name) != getattr(story, field_name)
        for field_name in frozen_fields
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_STORY_CHANGED_SCENE_ASSETS",
            message="故事阶段改写了已冻结的场景或素材事实",
        )


def _completion_result(
    callback: VideoPlanCompletionCallback,
    scene_id: str,
) -> dict[str, JsonValue]:
    """提取会进入 ReviewArtifact 的完整成功结果，供落库和幂等共用。"""

    return cast(
        dict[str, JsonValue],
        {
            "applyTarget": {"type": "video_scene_plan", "sceneId": scene_id},
            "scenePlan": callback.scenePlan.model_dump(mode="json"),
            "promptPackage": callback.promptPackage.model_dump(mode="json"),
        },
    )


def _failure_result(callback: VideoPlanFailureCallback) -> dict[str, JsonValue]:
    """只保存 Agent 失败契约中的原始业务结果，不混入 Core 展示字段。"""

    return {
        "code": callback.code,
        "message": callback.message,
        "recoverable": callback.recoverable,
    }


def _is_refundable_video_plan_failure(callback: VideoPlanFailureCallback) -> bool:
    """只补偿供应商输出耗尽纠正后仍不满足结构或导演门禁的业务失败。"""

    return (
        callback.code == "VIDEO_PLAN_FAILED"
        and callback.recoverable
        and callback.message.startswith("VIDEO_SCENE_PLAN_INVALID")
    )


async def _refund_failed_video_plan(
    session: AsyncSession,
    *,
    task: VideoGenerationTask,
    novel_id: str,
) -> None:
    """在失败终态事务内幂等退回本 task 的积分，真实 TokenUsage 保持不变。"""

    user_id = await session.scalar(select(Novel.userId).where(Novel.id == novel_id))
    if user_id is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_REFUND_OWNER_MISSING",
            message="视频规划失败补偿缺少小说归属，不能安全结算",
        )
    prefix = video_task_billing_request_prefix(task.id)
    refund_request_id = f"{prefix}refund"
    existing_refund = await session.scalar(
        select(CreditLedger)
        .where(
            CreditLedger.userId == user_id,
            CreditLedger.type == "video_plan_refund",
            CreditLedger.requestId == refund_request_id,
        )
        .with_for_update()
    )
    if existing_refund is not None:
        return
    charges = tuple(
        (
            await session.scalars(
                select(CreditLedger)
                .where(
                    CreditLedger.userId == user_id,
                    CreditLedger.novelId == novel_id,
                    CreditLedger.type == "ai_charge",
                    CreditLedger.requestId.like(f"{prefix}%"),
                )
                .with_for_update()
            )
        ).all()
    )
    refund_micros = sum(
        -int(charge.amountMicros)
        for charge in charges
        if charge.amountMicros < 0
    )
    if refund_micros == 0:
        return
    balance_after = await session.scalar(
        update(User)
        .where(User.id == user_id)
        .values(creditBalanceMicros=User.creditBalanceMicros + refund_micros)
        .returning(User.creditBalanceMicros)
    )
    if balance_after is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_REFUND_USER_MISSING",
            message="视频规划失败补偿缺少用户账户，不能安全结算",
        )
    session.add(
        CreditLedger(
            userId=str(user_id),
            type="video_plan_refund",
            amountMicros=refund_micros,
            balanceAfterMicros=int(balance_after),
            model="deepseek-v4-flash",
            promptTokens=0,
            cachedTokens=0,
            completionTokens=0,
            totalTokens=0,
            agentId="剧情",
            novelId=novel_id,
            requestId=refund_request_id,
            note="视频规划结构失败积分退回",
        )
    )


def _encode_terminal_callback_result(
    progress_json: str | None,
    *,
    status: Literal["completed", "failed"],
    event_id: str,
    result: dict[str, JsonValue],
) -> str:
    """把格式错误转换为稳定业务冲突，绝不覆盖无法读取的旧结果。"""

    try:
        return encode_video_plan_terminal_result(
            progress_json=progress_json,
            status=status,
            event_id=event_id,
            result=result,
        )
    except VideoPlanTerminalResultFormatError as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_TERMINAL_RESULT_INVALID",
            message="视频规划进度或终态结果已损坏，不能安全收敛任务",
        ) from exc


def _require_matching_terminal_callback(
    task: VideoGenerationTask,
    *,
    status: Literal["completed", "failed"],
    event_id: str,
    result: dict[str, JsonValue],
) -> None:
    """终态重放必须匹配原事件和原结果；旧成功记录只比较可证明的候选。"""

    terminal = _decode_terminal_callback_result(task.resultJson)
    if terminal is not None:
        if (
            terminal.status == status
            and terminal.event_id == event_id
            and video_plan_results_equal(terminal.result, result)
        ):
            return
        raise _terminal_callback_conflict()

    # 旧版成功任务直接把完整候选放在 resultJson，虽然没有 eventId，仍可严格证明
    # Agent 的业务结果一致。旧失败任务缺少 recoverable/eventId，不能安全视为重放。
    if status == "completed":
        try:
            legacy_result = json.loads(task.resultJson or "")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ApiError(
                status_code=409,
                code="VIDEO_PLAN_TERMINAL_RESULT_INVALID",
                message="历史视频规划终态结果已损坏，不能核验重复回调",
            ) from exc
        if isinstance(legacy_result, dict) and video_plan_results_equal(
            cast(dict[str, JsonValue], legacy_result),
            result,
        ):
            return
    raise _terminal_callback_conflict()


def _decode_terminal_callback_result(
    result_json: str | None,
) -> VideoPlanTerminalResult | None:
    """统一把终态信封解析错误映射为 Core 稳定错误。"""

    try:
        return decode_video_plan_terminal_result(result_json)
    except VideoPlanTerminalResultFormatError as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_TERMINAL_RESULT_INVALID",
            message="视频规划终态结果已损坏，不能核验重复回调",
        ) from exc


def _terminal_callback_conflict() -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_PLAN_TERMINAL_CALLBACK_CONFLICT",
        message="视频规划终态回调与首次保存的结果不一致",
    )


def _terminal_attempt_state(result_json: str | None) -> VideoPlanAttemptState:
    """终态只回显安全计数；正式候选或旧数据没有账本时返回零。"""

    if result_json is None:
        return VideoPlanAttemptState(reservedCalls=0, pendingStage=None)
    try:
        terminal = decode_video_plan_terminal_result(result_json)
        progress_json = (
            video_plan_terminal_progress_json(terminal) if terminal is not None else result_json
        )
        state = _load_active_plan_progress(progress_json).attempt_state
        return state.model_copy(update={"pendingStage": None})
    except (ApiError, VideoPlanTerminalResultFormatError):
        return VideoPlanAttemptState(reservedCalls=0, pendingStage=None)


def _retry_plan_progress_json(
    task: VideoGenerationTask,
    *,
    source_payload: VideoPlanJobPayload,
    target_payload: VideoPlanJobPayload,
) -> str | None:
    """只复制可证明的 canonical checkpoint，并为新任务重建空预留账本。"""

    source_fingerprint = calculate_video_plan_business_input_fingerprint(source_payload)
    target_fingerprint = calculate_video_plan_business_input_fingerprint(target_payload)
    if source_fingerprint != target_fingerprint:
        return None
    try:
        terminal = decode_video_plan_terminal_result(task.resultJson)
        if terminal is None or terminal.status != "failed":
            return None
        terminal_message = terminal.result.get("message")
        if isinstance(terminal_message, str) and (
            "编译后的 Provider 中文提示词超出产品安全上限：" in terminal_message
        ):
            # 超长可能来自素材、故事和摄影任一阶段；只重跑摄影没有权限修正上游预算。
            return None
        source = _load_active_plan_progress(video_plan_terminal_progress_json(terminal))
    except (ApiError, VideoPlanTerminalResultFormatError):
        # 历史结果缺少可证明的版本化进度时从 empty 安全重跑，不能猜测半结构草稿。
        return None
    checkpoint_stage = source.checkpoint_stage
    scene_assets_plan = source.scene_assets_plan
    story_plan = source.story_plan
    if (
        target_payload.directorDraftVersion in {"1.3", "1.4"}
        and story_plan is not None
        and story_plan.schemaVersion != "2.0"
    ):
        # v1 故事检查点没有逐动作 E 事件归属，不能在新协议下继续用关键词猜测顺序。
        scene_assets_plan = _scene_assets_checkpoint_from_story(story_plan)
        if scene_assets_plan is None:
            return None
        checkpoint_stage = "scene_assets"
        story_plan = None
    if isinstance(terminal_message, str) and (
        "VIDEO_PLAN_INITIAL_KEYFRAME_REQUIRED" in terminal_message
    ):
        if story_plan is None:
            return None
        scene_assets_plan = _scene_assets_checkpoint_from_story(story_plan)
        if scene_assets_plan is None:
            return None
        checkpoint_stage = "scene_assets"
        story_plan = None
    inherited_calls = {"empty": 0, "scene_assets": 1, "story": 2}[
        checkpoint_stage
    ]
    if inherited_calls == 0:
        return None
    inherited = _VideoPlanDurableProgress(
        checkpoint_stage=checkpoint_stage,
        scene_assets_plan=scene_assets_plan,
        story_plan=story_plan,
        attempt_state=VideoPlanAttemptState(
            reservedCalls=0,
            inheritedCalls=inherited_calls,
            pendingStage=None,
        ),
        reservations=(),
        inherited_from_task_id=task.id,
        inherited_input_fingerprint=target_fingerprint,
    )
    return _plan_progress_json(inherited)


def _scene_assets_checkpoint_from_story(
    story: StoryPlanStageArguments,
) -> SceneAssetsStageArguments | None:
    """从旧故事检查点恢复仍然可信的场景素材层，不继承错误节拍。"""

    has_initial_state = any(
        asset.duty == "keyframe"
        and asset.bindingScope == "scene_direct"
        and asset.modality == "image"
        and asset.keyframeRole == "initial_state"
        for asset in story.assets
    )
    if not has_initial_state:
        return None
    try:
        return SceneAssetsStageArguments(
            title=story.title,
            summary=story.summary,
            dramaticArc=story.dramaticArc,
            visualStyle=story.visualStyle,
            globalDirection=story.globalDirection,
            assets=story.assets,
            negativeConstraints=story.negativeConstraints,
        )
    except ValueError:
        return None


def _validate_retry_payload(
    task: VideoGenerationTask,
    scene: VideoScene,
    project: VideoProject,
) -> VideoPlanJobPayload:
    """确认重试载荷仍与场景冻结事实完全一致。"""

    try:
        payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_RETRY_INPUT_INVALID",
            message="原失败任务的冻结输入已无法安全读取",
        ) from exc
    source_hash = hashlib.sha256(payload.sourceText.encode()).hexdigest()
    if (
        task.projectId != project.id
        or task.sceneId != scene.id
        or payload.projectId != project.id
        or payload.sceneId != scene.id
        or payload.chapterId != scene.chapterId
        or payload.title != scene.title
        or payload.sourceText != scene.sourceText
        or source_hash != scene.sourceHash
        or payload.durationSeconds != scene.durationSeconds
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_RETRY_INPUT_MISMATCH",
            message="原失败任务与当前场景的冻结输入不一致，不能安全重试",
        )
    return payload


def _upgrade_video_planning_route(
    payload: VideoPlanJobPayload,
) -> VideoPlanJobPayload:
    """为显式创建的新任务冻结当前 Responses 协议，来源快照保持原样。"""

    return VideoPlanJobPayload.model_validate(
        {
            **payload.model_dump(mode="python"),
            "planningRoute": "responses_json_schema_v1",
            "planningModel": "deepseek-v4-flash",
            "directorDraftVersion": "1.4",
        }
    )


def _video_scene_create_idempotency_key(
    user_id: str,
    project_id: str,
    client_request_id: str,
) -> str:
    """把浏览器请求标识绑定到用户和项目，避免跨资源重放。"""

    return f"video-scene:{user_id}:{project_id}:{client_request_id}"


def _video_review_decision_request_hash(
    scene_id: str,
    expected_artifact_revision: int,
) -> str:
    """把会改变批准语义的字段编码为稳定请求哈希。"""

    canonical = json.dumps(
        {
            "decision": "approve",
            "expectedArtifactRevision": expected_artifact_revision,
            "sceneId": scene_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _video_review_decision_lock_key(user_id: str, client_request_id: str) -> int:
    """为用户级请求键生成 PostgreSQL bigint advisory lock 键。"""

    canonical = json.dumps(
        ["video-review-decision", user_id, client_request_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    raw = int.from_bytes(hashlib.sha256(canonical.encode("utf-8")).digest()[:8], "big")
    return raw if raw < 2**63 else raw - 2**64


async def _lock_video_review_decision_request(
    session: AsyncSession,
    user_id: str,
    client_request_id: str,
) -> None:
    """先串行化同一用户请求键，消除“查无记录后并发插入”的窗口。"""

    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _video_review_decision_lock_key(user_id, client_request_id)},
    )


def _approval_response_from_command(
    command: VideoReviewDecisionCommand,
    *,
    user_id: str,
    scene_id: str,
    expected_artifact_revision: int,
    request_hash: str,
    artifact_id: str | None = None,
    source_task_id: str | None = None,
) -> ApproveVideoSceneResponse:
    """严格核验耐久命令绑定，并读取首次保存的完整批准响应。"""

    if (
        command.requestedByUserId != user_id
        or command.sceneId != scene_id
        or command.decision != "approve"
        or command.expectedArtifactRevision != expected_artifact_revision
        or command.requestHash != request_hash
        or (artifact_id is not None and command.artifactId != artifact_id)
        or (source_task_id is not None and command.sourceTaskId != source_task_id)
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_REVIEW_DECISION_IDEMPOTENCY_CONFLICT",
            message="同一批准请求标识不能绑定不同的场景或候选版本",
        )
    if command.status != "succeeded":
        raise _video_approval_result_error()
    try:
        response = ApproveVideoSceneResponse.model_validate_json(command.resultJson)
    except ValueError as exc:
        raise _video_approval_result_error() from exc
    if response.scene.id != scene_id:
        raise _video_approval_result_error()
    return response


def _video_review_decision_command(
    *,
    user_id: str,
    scene: VideoScene,
    artifact: ReviewArtifact,
    source_task: VideoGenerationTask,
    request: ApproveVideoSceneRequest,
    request_hash: str,
    result_json: str,
    completed_at: datetime,
) -> VideoReviewDecisionCommand:
    """构造与正式应用位于同一事务的成功批准命令。"""

    return VideoReviewDecisionCommand(
        id=generate_id(),
        requestedByUserId=user_id,
        novelId=artifact.novelId,
        projectId=scene.projectId,
        sceneId=scene.id,
        artifactId=artifact.id,
        sourceTaskId=source_task.id,
        decision="approve",
        expectedArtifactRevision=request.expectedArtifactRevision,
        clientRequestId=request.clientRequestId,
        requestHash=request_hash,
        status="succeeded",
        resultJson=result_json,
        createdAt=completed_at,
        updatedAt=completed_at,
        completedAt=completed_at,
    )


def _video_approval_state_error() -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_APPROVAL_STATE_INCONSISTENT",
        message="视频场景与审核候选状态不一致，不能安全批准",
    )


def _video_approval_result_error() -> ApiError:
    return ApiError(
        status_code=409,
        code="VIDEO_REVIEW_DECISION_RESULT_INVALID",
        message="首次批准结果已损坏，不能安全重放",
    )


async def _require_video_approval_context(
    session: AsyncSession,
    *,
    user_id: str,
    scene_id: str,
    expected_artifact_revision: int,
) -> tuple[VideoScene, ReviewArtifact, VideoGenerationTask]:
    """按固定顺序锁定归属、场景、候选和生成来源，并校验状态矩阵。"""

    scene = await session.scalar(
        select(VideoScene)
        .join(VideoProject, VideoProject.id == VideoScene.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(VideoScene.id == scene_id, Novel.userId == user_id)
        .with_for_update()
    )
    if scene is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_SCENE_NOT_FOUND",
            message="视频场景不存在",
        )
    await _require_long_serial_project_by_id(
        session,
        scene.projectId,
        lock=True,
    )
    artifact = await session.scalar(
        select(ReviewArtifact)
        .where(ReviewArtifact.videoSceneId == scene.id)
        .order_by(ReviewArtifact.revision.desc(), ReviewArtifact.createdAt.desc())
        .with_for_update()
    )
    if artifact is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_SCENE_NOT_AWAITING_REVIEW",
            message="当前场景没有等待批准的方案",
        )
    if artifact.revision != expected_artifact_revision:
        raise ApiError(
            status_code=409,
            code="VIDEO_ARTIFACT_REVISION_CONFLICT",
            message="视频候选版本已经变化，请刷新后再批准",
            details={"currentRevision": artifact.revision},
        )
    if artifact.kind != "video_scene_plan":
        raise ApiError(
            status_code=409,
            code="VIDEO_APPROVAL_ARTIFACT_INVALID",
            message="当前审核候选不是视频场景方案",
        )
    if artifact.status == "awaiting_user":
        if scene.status != "awaiting_review" or scene.planJson is not None:
            raise _video_approval_state_error()
    elif artifact.status == "applied":
        if scene.status != "approved" or scene.planJson is None:
            raise _video_approval_state_error()
    else:
        raise ApiError(
            status_code=409,
            code="VIDEO_SCENE_NOT_AWAITING_REVIEW",
            message="当前场景没有等待批准的方案",
        )
    source_task = await _require_video_approval_source_task(session, scene, artifact)
    return scene, artifact, source_task


async def _replay_applied_video_approval(
    session: AsyncSession,
    *,
    user_id: str,
    scene: VideoScene,
    artifact: ReviewArtifact,
    source_task: VideoGenerationTask,
    request_hash: str,
) -> tuple[ApproveVideoSceneResponse, str]:
    """为新的请求键复制同一候选首次批准结果；兼容迁移前已批准数据。"""

    prior_command = await session.scalar(
        select(VideoReviewDecisionCommand)
        .where(
            VideoReviewDecisionCommand.requestedByUserId == user_id,
            VideoReviewDecisionCommand.artifactId == artifact.id,
            VideoReviewDecisionCommand.expectedArtifactRevision == artifact.revision,
            VideoReviewDecisionCommand.decision == "approve",
        )
        .order_by(
            VideoReviewDecisionCommand.createdAt,
            VideoReviewDecisionCommand.id,
        )
        .limit(1)
        .with_for_update()
    )
    if prior_command is None:
        response = ApproveVideoSceneResponse(scene=await _scene_response(session, scene))
        return response, response.model_dump_json()
    response = _approval_response_from_command(
        prior_command,
        user_id=user_id,
        scene_id=scene.id,
        expected_artifact_revision=artifact.revision,
        request_hash=request_hash,
        artifact_id=artifact.id,
        source_task_id=source_task.id,
    )
    return response, prior_command.resultJson


def _apply_video_approval_candidate(
    scene: VideoScene,
    artifact: ReviewArtifact,
    *,
    approved_at: datetime,
) -> None:
    """完整校验待审载荷后，才把同一份场景方案投影到正式字段。"""

    try:
        payload = json.loads(artifact.payloadJson)
        if not isinstance(payload, dict):
            raise ValueError("候选载荷不是对象")
        if payload.get("applyTarget") != {
            "type": "video_scene_plan",
            "sceneId": scene.id,
        }:
            raise ValueError("候选应用目标与场景不一致")
        raw_scene_plan = payload["scenePlan"]
        if not isinstance(raw_scene_plan, dict):
            raise ValueError("候选场景方案不是对象")
        scene_plan = ScenePromptSpec.model_validate(raw_scene_plan)
        package = SeedancePromptPackage.model_validate(payload["promptPackage"])
        plan_asset_ids = {asset.assetId for asset in scene_plan.assets}
        package_asset_ids = {binding.assetId for binding in package.assetBindings}
        if (
            scene_plan.sceneId != scene.id
            or package.sceneId != scene.id
            or package.output != scene_plan.output
            or package_asset_ids != plan_asset_ids
            or len(package.assetBindings) != len(package_asset_ids)
        ):
            raise ValueError("候选方案、提示词包与场景绑定不一致")
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_APPROVAL_ARTIFACT_INVALID",
            message="视频候选内容已损坏，不能安全批准",
        ) from exc

    scene.planJson = json.dumps(raw_scene_plan, ensure_ascii=False)
    # 旧包只有 prompt；新包明确把数据库兼容字段镜像为 Provider 短提示词。
    scene.promptText = package.providerPrompt or package.prompt
    scene.promptCharacterCount = (
        package.providerPromptCharacterCount or package.promptCharacterCount
    )
    scene.status = "approved"
    scene.revision += 1
    scene.updatedAt = approved_at
    artifact.status = "applied"
    artifact.appliedAt = approved_at
    artifact.updatedAt = approved_at


async def _require_video_approval_source_task(
    session: AsyncSession,
    scene: VideoScene,
    artifact: ReviewArtifact,
) -> VideoGenerationTask:
    """锁定当前候选对应的最新成功规划任务，避免批准无来源候选。"""

    task = await session.scalar(
        select(VideoGenerationTask)
        .where(
            VideoGenerationTask.sceneId == scene.id,
            VideoGenerationTask.projectId == scene.projectId,
            VideoGenerationTask.kind == "plan",
        )
        .order_by(
            VideoGenerationTask.createdAt.desc(),
            VideoGenerationTask.id.desc(),
        )
        .limit(1)
        .with_for_update()
    )
    if task is None or task.status != "completed" or task.provider != "deepseek":
        raise ApiError(
            status_code=409,
            code="VIDEO_APPROVAL_SOURCE_TASK_INVALID",
            message="当前候选没有可核验的已完成规划任务",
        )
    _validate_artifact_matches_task(task, artifact, operation="approve")
    return task


def _validate_create_replay_payload(
    task: VideoGenerationTask,
    project: VideoProject,
    request: CreateVideoSceneRequest,
) -> VideoPlanJobPayload:
    """同一创建请求标识只能重放相同的冻结业务输入。"""

    try:
        payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_SCENE_IDEMPOTENCY_CONFLICT",
            message="原场景创建请求的冻结输入已损坏",
        ) from exc
    if (
        task.kind != "plan"
        or task.projectId != project.id
        or payload.projectId != project.id
        or payload.sceneId != task.sceneId
        or payload.chapterId != request.chapterId
        or payload.title != request.title.strip()
        or payload.sourceText != request.selectedText
        or payload.durationSeconds != request.durationSeconds
        or payload.ratio != project.targetAspectRatio
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_SCENE_IDEMPOTENCY_CONFLICT",
            message="同一场景创建请求标识不能提交不同内容",
        )
    return payload


def _validated_chapter_selection(
    chapter: Chapter,
    request: CreateVideoSceneRequest,
) -> str:
    """按浏览器 UTF-16 语义重切章节，并拒绝过期或被伪造的来源。"""

    if not isinstance(chapter.updatedAt, datetime):
        raise RuntimeError("章节更新时间缺失")
    if _utc_naive(chapter.updatedAt) != _utc_naive(request.expectedChapterUpdatedAt):
        raise ApiError(
            status_code=409,
            code="VIDEO_SOURCE_CHANGED",
            message="章节内容已经变化，请重新选择原文事件",
        )
    try:
        start = _utf16_offset_to_codepoint_index(
            chapter.content,
            request.selectionStartUtf16,
        )
        end = _utf16_offset_to_codepoint_index(
            chapter.content,
            request.selectionEndUtf16,
        )
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_SOURCE_CHANGED",
            message="原文选区已经失效，请重新选择",
        ) from exc
    selected = chapter.content[start:end]
    if selected != request.selectedText:
        raise ApiError(
            status_code=409,
            code="VIDEO_SOURCE_CHANGED",
            message="原文选区与当前章节不一致，请重新选择",
        )
    if len(selected) > 2_000:
        raise ApiError(
            status_code=422,
            code="VIDEO_SOURCE_TOO_LONG",
            message="单场景来源不能超过 2000 字，请缩小选区",
        )
    return selected


def _utf16_offset_to_codepoint_index(value: str, offset: int) -> int:
    """把 JavaScript textarea 偏移转换为 Python 字符下标，并拒绝半个代理对。"""

    if offset < 0:
        raise ValueError("UTF-16 偏移不能为负数")
    consumed = 0
    for index, character in enumerate(value):
        if consumed == offset:
            return index
        consumed += 2 if ord(character) > 0xFFFF else 1
        if consumed > offset:
            raise ValueError("UTF-16 偏移落在代理对内部")
    if consumed == offset:
        return len(value)
    raise ValueError("UTF-16 偏移超出正文")


def _utc_naive(value: datetime) -> datetime:
    """把 API 时区时间与数据库 UTC naive 时间归一到同一比较语义。"""

    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _validate_revise_replay_payload(
    task: VideoGenerationTask,
    scene: VideoScene,
    project: VideoProject,
    user_message: str,
) -> VideoPlanJobPayload:
    """同一幂等键只能重放完全相同的返工意见和冻结输入。"""

    if task.kind != "plan":
        raise ApiError(
            status_code=409,
            code="VIDEO_REVISE_IDEMPOTENCY_CONFLICT",
            message="返工请求标识已被其他任务占用",
        )
    payload = _validate_retry_payload(task, scene, project)
    if payload.revisionInstruction != user_message:
        raise ApiError(
            status_code=409,
            code="VIDEO_REVISE_IDEMPOTENCY_CONFLICT",
            message="同一返工请求标识不能提交不同意见",
        )
    return payload


def _validate_artifact_matches_task(
    task: VideoGenerationTask,
    artifact: ReviewArtifact,
    *,
    operation: Literal["revise", "approve"] = "revise",
) -> None:
    """返工和批准都必须基于最新完成任务实际产出的当前候选。"""

    invalid_code = (
        "VIDEO_REVISE_ARTIFACT_INVALID"
        if operation == "revise"
        else "VIDEO_APPROVAL_ARTIFACT_INVALID"
    )
    invalid_message = (
        "当前候选的生成来源已无法安全读取"
        if operation == "revise"
        else "当前候选的生成来源已损坏，不能安全批准"
    )
    mismatch_code = (
        "VIDEO_REVISE_ARTIFACT_MISMATCH"
        if operation == "revise"
        else "VIDEO_APPROVAL_ARTIFACT_MISMATCH"
    )
    mismatch_message = (
        "当前候选与最新完成任务不一致，不能安全返工"
        if operation == "revise"
        else "当前候选与最新完成任务不一致，不能安全批准"
    )

    try:
        terminal = decode_video_plan_terminal_result(task.resultJson)
        if terminal is not None:
            if terminal.status != "completed":
                raise ValueError("最新任务没有成功候选")
            task_result: object = terminal.result
        else:
            task_result = json.loads(task.resultJson or "")
        artifact_payload = json.loads(artifact.payloadJson)
    except (TypeError, ValueError, VideoPlanTerminalResultFormatError) as exc:
        raise ApiError(
            status_code=409,
            code=invalid_code,
            message=invalid_message,
        ) from exc
    if task_result != artifact_payload:
        raise ApiError(
            status_code=409,
            code=mismatch_code,
            message=mismatch_message,
        )


def _revision_baseline_from_artifact(
    artifact: ReviewArtifact,
    scene: VideoScene,
) -> ScenePromptSpec:
    """从已核对来源的待审载荷提取返工基线，并再次绑定当前场景。"""

    try:
        payload = json.loads(artifact.payloadJson)
        if not isinstance(payload, dict):
            raise ValueError("候选载荷不是对象")
        baseline = ScenePromptSpec.model_validate(payload["scenePlan"])
        if baseline.sceneId != scene.id:
            raise ValueError("候选场景与当前场景不一致")
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_REVISE_ARTIFACT_INVALID",
            message="当前候选无法作为返工基线读取",
        ) from exc
    return baseline


def _artifact_revision_snapshot(artifact: ReviewArtifact) -> ReviewArtifactRevision:
    """复制返工前候选的全部可审计字段，原 Artifact 随后才允许回到 draft。"""

    return ReviewArtifactRevision(
        artifactId=artifact.id,
        revision=artifact.revision,
        summary=artifact.summary,
        payloadJson=artifact.payloadJson,
        diffJson=artifact.diffJson,
        createdByAgent=artifact.updatedByAgent or artifact.createdByAgent,
    )


def _apply_revised_artifact(
    artifact: ReviewArtifact,
    *,
    scene_title: str,
    summary: str,
    payload_json: str,
) -> None:
    """把返工结果写回同一 Artifact，并保留稳定审核标识。"""

    artifact.status = "awaiting_user"
    artifact.title = f"视频场景方案：{scene_title}"
    artifact.summary = summary
    artifact.payloadJson = payload_json
    artifact.diffJson = None
    artifact.updatedByAgent = "剧情"
    artifact.revision += 1
    artifact.updatedAt = utc_now()


async def _require_current_scene_task(
    session: AsyncSession,
    task: VideoGenerationTask,
    scene: VideoScene,
) -> None:
    """拒绝旧尝试的迟到回调覆盖同场景的新任务状态。"""

    latest_task_id = await session.scalar(
        select(VideoGenerationTask.id)
        .where(VideoGenerationTask.sceneId == scene.id)
        .order_by(
            VideoGenerationTask.createdAt.desc(),
            VideoGenerationTask.id.desc(),
        )
        .limit(1)
    )
    if latest_task_id != task.id:
        raise ApiError(
            status_code=409,
            code="VIDEO_CALLBACK_STALE_ATTEMPT",
            message="旧视频规划尝试的回调已失效",
        )


def _validate_callback_binding(
    task: VideoGenerationTask,
    scene: VideoScene,
    project: VideoProject,
    callback: (
        VideoPlanCompletionCallback
        | VideoPlanFailureCallback
        | VideoPlanCallReservationRequest
        | VideoPlanProgressQuery
        | VideoStoryPlanCheckpointCallback
    ),
) -> None:
    """拒绝签名正确但六重资源身份交叉绑定的内部请求。"""

    if (
        task.id != callback.taskId
        or task.jobId != callback.jobId
        # 视频投递器以 taskId 作为唯一 runId；现有表无需新增重复列。
        or task.id != callback.runId
        or task.projectId != callback.projectId
        or task.sceneId != callback.sceneId
        or scene.projectId != callback.projectId
        or project.id != callback.projectId
        or project.novelId != callback.novelId
    ):
        raise ApiError(
            status_code=403,
            code="VIDEO_CALLBACK_RESOURCE_MISMATCH",
            message="视频回调资源绑定不匹配",
        )

    if isinstance(callback, VideoPlanCompletionCallback) and (
        callback.sceneId != callback.scenePlan.sceneId
        or callback.sceneId != callback.promptPackage.sceneId
    ):
        raise ApiError(
            status_code=403,
            code="VIDEO_CALLBACK_RESOURCE_MISMATCH",
            message="视频回调内部场景标识不匹配",
        )


def _video_dispatch_backoff(attempt_count: int) -> timedelta:
    """视频投递按 2、4、8 秒指数退避，最高五分钟。"""

    seconds = min(300, 2 ** min(max(attempt_count, 1), 8))
    return timedelta(seconds=seconds)


def _fail_dispatch_task(
    task: VideoGenerationTask,
    scene: VideoScene | None,
    *,
    code: str,
    message: str,
    status: Literal["failed", "cancelled"] = "failed",
) -> None:
    """在同一事务中收敛无法继续投递的任务和公共场景状态。"""

    now = utc_now()
    task.status = status
    task.lastErrorCode = code
    task.lastErrorMessage = message
    task.completedAt = now
    task.updatedAt = now
    if scene is not None:
        scene.status = "failed"
        scene.lastErrorCode = code
        scene.lastErrorMessage = message
        scene.updatedAt = now


def _validate_plan_against_frozen_snapshot(
    task: VideoGenerationTask,
    scene_plan: ScenePromptSpec,
) -> None:
    """候选方案只能引用任务 requestJson 中已冻结的类型化设定。"""

    try:
        payload = VideoPlanJobPayload.model_validate_json(task.requestJson)
        for asset in scene_plan.assets:
            if asset.bindingScope == "canon_slot":
                if asset.settingReference is None:
                    raise ValueError("canon_slot 缺少设定引用")
                payload.settingSnapshot.resolve(asset.settingReference)
    except ValueError as exc:
        raise ApiError(
            status_code=409,
            code="VIDEO_PLAN_SETTING_REFERENCE_INVALID",
            message="视频方案引用了任务冻结快照之外的设定",
        ) from exc


def _project_response(project: VideoProject, scene_count: int) -> VideoProjectResponse:
    """把 ORM 对象转换成稳定公共响应。"""

    return VideoProjectResponse(
        id=project.id,
        novelId=project.novelId,
        title=project.title,
        mode=project.mode,
        status=project.status,
        targetAspectRatio=project.targetAspectRatio,
        targetLanguage=project.targetLanguage,
        provider=project.provider,
        revision=project.revision,
        sceneCount=scene_count,
        createdAt=project.createdAt,
        updatedAt=project.updatedAt,
    )


async def _scene_response(session: AsyncSession, scene: VideoScene) -> VideoSceneResponse:
    """聚合场景、最新任务和当前候选 ReviewArtifact。"""

    task = await session.scalar(
        select(VideoGenerationTask)
        .where(VideoGenerationTask.sceneId == scene.id)
        .order_by(VideoGenerationTask.createdAt.desc(), VideoGenerationTask.id.desc())
    )
    artifact = await session.scalar(
        select(ReviewArtifact)
        .where(ReviewArtifact.videoSceneId == scene.id)
        .order_by(ReviewArtifact.revision.desc(), ReviewArtifact.createdAt.desc())
    )
    bindings = (
        await session.scalars(
            select(VideoAssetBinding)
            .where(VideoAssetBinding.sceneId == scene.id)
            .order_by(VideoAssetBinding.priority.desc(), VideoAssetBinding.createdAt)
        )
    ).all()
    candidate_package: SeedancePromptPackage | None = None
    candidate_plan: dict[str, object] | None = None
    # 返工生成期间 Artifact 会回到 draft；此时不得继续向页面泄露旧候选。
    if artifact is not None and artifact.status == "awaiting_user":
        payload = json.loads(artifact.payloadJson)
        candidate_package = SeedancePromptPackage.model_validate(payload["promptPackage"])
        candidate_plan = payload["scenePlan"]
    plan = json.loads(scene.planJson) if scene.planJson is not None else None
    return VideoSceneResponse(
        id=scene.id,
        projectId=scene.projectId,
        chapterId=scene.chapterId,
        ordinal=scene.ordinal,
        title=scene.title,
        sourceText=scene.sourceText,
        sourceHash=scene.sourceHash,
        durationSeconds=scene.durationSeconds,
        status=scene.status,
        promptText=scene.promptText,
        promptCharacterCount=scene.promptCharacterCount,
        plan=plan,
        candidatePlan=candidate_plan,
        candidatePackage=candidate_package,
        reviewArtifact=(
            VideoReviewArtifactSummary(
                id=artifact.id,
                status=artifact.status,
                revision=artifact.revision,
                title=artifact.title,
                summary=artifact.summary,
            )
            if artifact is not None
            else None
        ),
        latestTask=_task_response(task) if task is not None else None,
        assetBindings=[_binding_response(binding) for binding in bindings],
        revision=scene.revision,
        createdAt=scene.createdAt,
        updatedAt=scene.updatedAt,
    )


def _task_response(task: VideoGenerationTask) -> VideoGenerationTaskResponse:
    """把耐久任务转换成浏览器可见且不包含冻结输入的状态。"""

    return VideoGenerationTaskResponse(
        id=task.id,
        jobId=task.jobId,
        kind=task.kind,
        status=task.status,
        lastErrorCode=task.lastErrorCode,
        lastErrorMessage=task.lastErrorMessage,
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
    )


def _asset_response(asset: VideoAsset) -> VideoAssetResponse:
    """隐藏 storageKey，仅向浏览器返回可展示媒体元数据。"""

    return VideoAssetResponse(
        id=asset.id,
        projectId=asset.projectId,
        name=asset.name,
        modality=cast(AssetModality, asset.modality),
        duty=cast(AssetDuty, asset.duty),
        mimeType=asset.mimeType,
        byteSize=asset.byteSize,
        durationMs=asset.durationMs,
        sha256=asset.sha256,
        sourceKind=asset.sourceKind,
        rightsStatus=asset.rightsStatus,
        lockedAt=asset.lockedAt,
        createdAt=asset.createdAt,
        updatedAt=asset.updatedAt,
    )


def _binding_response(binding: VideoAssetBinding) -> VideoAssetBindingResponse:
    """把文本 JSON 数组恢复为公共契约中的字符串列表。"""

    return VideoAssetBindingResponse(
        id=binding.id,
        sceneId=binding.sceneId,
        assetId=binding.assetId,
        targetEntity=binding.targetEntity,
        includeFeatures=json.loads(binding.includeFeaturesJson),
        excludeFeatures=json.loads(binding.excludeFeaturesJson),
        priority=binding.priority,
        createdAt=binding.createdAt,
        updatedAt=binding.updatedAt,
    )

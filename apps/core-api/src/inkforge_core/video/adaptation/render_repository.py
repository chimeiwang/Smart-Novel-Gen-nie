"""逐镜 Seedance 任务、不可变 Take 与确认 head 的 PostgreSQL 实现。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast

from inkforge_contracts.video import AssetDuty, AssetModality
from inkforge_contracts.video_adaptation import VisualCanonDuty
from inkforge_contracts.video_render import (
    AspectRatio,
    ShotRenderKeyframeManifest,
    ShotRenderReferenceManifest,
    VideoShotRenderManifest,
)
from pydantic import JsonValue, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db.base import generate_id, utc_now
from ...db.models import (
    Novel,
    VideoAsset,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoProject,
    VideoShot,
    VideoShotKeyframeHead,
    VideoShotKeyframeVersion,
    VideoShotPromptHead,
    VideoShotPromptVersion,
    VideoShotPromptVisualReference,
    VideoShotRenderTask,
    VideoShotTake,
    VideoShotTakeDecisionCommand,
    VideoShotTakeHead,
    VideoVisualCanon,
    VideoVisualCanonVersion,
)
from ...errors import ApiError
from ..repository import VideoAssetFile
from ..schemas import VideoAssetResponse
from ..storage import StoredVideoAsset
from .schemas import (
    ChapterRenderWorkspaceResponse,
    ConfirmShotTakeRequest,
    RetryShotRenderRequest,
    ShotRenderTaskResponse,
    ShotRenderTaskStatus,
    ShotTakeDecisionResponse,
    ShotTakeHeadResponse,
    ShotTakeResponse,
    StartShotRenderRequest,
    VideoRenderReadinessResponse,
)

_TASK_TERMINAL_STATUSES = {
    "submission_unknown",
    "succeeded",
    "failed",
    "expired",
    "cancelled",
}
_TASK_QUERY_STATUSES = {"queued", "running", "archiving"}


@dataclass(frozen=True, slots=True)
class ShotRenderClaim:
    task_id: str
    project_id: str
    novel_id: str
    status: str
    provider_task_id: str | None
    poll_count: int
    manifest: VideoShotRenderManifest

    @property
    def operation(self) -> Literal["submit", "query"]:
        return "submit" if self.status == "submitting" else "query"


@dataclass(frozen=True, slots=True)
class CompletedTakeInput:
    asset_id: str
    stored: StoredVideoAsset
    provider_metadata: dict[str, JsonValue]
    duration_ms: int | None


class VideoShotRenderRepository:
    """独立于旧 Scene 生成任务，只引用当前章节改编正式对象。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_task(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        request: StartShotRenderRequest,
        *,
        model: str,
        reference_transport_configured: bool,
    ) -> ShotRenderTaskResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_render_request(
                    session,
                    namespace="render-task",
                    identity=shot_id,
                    client_request_id=request.clientRequestId,
                )
                existing = await session.scalar(
                    select(VideoShotRenderTask)
                    .join(
                        VideoChapterAdaptation,
                        VideoChapterAdaptation.id == VideoShotRenderTask.adaptationId,
                    )
                    .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .where(
                        VideoShotRenderTask.shotId == shot_id,
                        VideoShotRenderTask.clientRequestId == request.clientRequestId,
                        Novel.userId == user_id,
                    )
                )
                if existing is not None:
                    manifest = _parse_manifest(existing)
                    _validate_start_replay(existing, manifest, adaptation_id, request)
                    return _task_response(existing, manifest)

                adaptation, project, head = await _require_owned_context(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                plan_id = head.currentShotPlanVersionId
                if plan_id is None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_RENDER_FORMAL_PLAN_REQUIRED",
                        message="请先确认正式镜头方案",
                    )
                shot = await session.scalar(
                    select(VideoShot)
                    .where(VideoShot.id == shot_id, VideoShot.planVersionId == plan_id)
                    .with_for_update()
                )
                if shot is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_RENDER_SHOT_NOT_FOUND",
                        message="当前正式镜头不存在",
                    )
                # 首次无锁幂等查询与并发创建之间存在窗口；正式方案 head 和镜头锁定后
                # 必须再次查询，保证同一用户操作始终返回同一任务而不是误报“任务执行中”。
                existing = await session.scalar(
                    select(VideoShotRenderTask).where(
                        VideoShotRenderTask.shotId == shot.id,
                        VideoShotRenderTask.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    manifest = _parse_manifest(existing)
                    _validate_start_replay(existing, manifest, adaptation_id, request)
                    return _task_response(existing, manifest)
                await _require_no_active_task(session, shot.id)
                prompt_head = await session.scalar(
                    select(VideoShotPromptHead)
                    .where(
                        VideoShotPromptHead.shotId == shot.id,
                        VideoShotPromptHead.shotPlanVersionId == plan_id,
                    )
                    .with_for_update()
                )
                if prompt_head is None or prompt_head.currentVersionId is None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_RENDER_PROMPT_REQUIRED",
                        message="请先保存当前镜头的正式提示词",
                    )
                if prompt_head.revision != request.expectedPromptRevision:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_RENDER_PROMPT_REVISION_CONFLICT",
                        message="提示词版本已经变化，请刷新后重新生成",
                    )
                prompt = await session.get(VideoShotPromptVersion, prompt_head.currentVersionId)
                if (
                    prompt is None
                    or prompt.shotId != shot.id
                    or prompt.shotPlanVersionId != plan_id
                ):
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_RENDER_PROMPT_HEAD_INVALID",
                        message="当前正式提示词指针无效",
                    )
                references = await _load_prompt_reference_manifest(session, prompt.id)
                keyframes = await _load_keyframe_manifest(session, shot.id)
                if references or keyframes:
                    if not reference_transport_configured:
                        raise ApiError(
                            status_code=503,
                            code="VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED",
                            message="当前环境尚未配置供应商可访问的视觉参考图地址",
                        )
                provider_prompt = _provider_prompt(prompt.currentText, references, keyframes)
                if len(provider_prompt) > 2_500:
                    raise ApiError(
                        status_code=422,
                        code="VIDEO_RENDER_PROVIDER_PROMPT_TOO_LONG",
                        message=(
                            "加入关键帧控制语句后的供应商提示词超过 2500 字符，"
                            "请精简正式提示词"
                        ),
                    )
                manifest = VideoShotRenderManifest(
                    schemaVersion="video-shot-render-manifest/1.1",
                    adaptationId=adaptation.id,
                    projectId=project.id,
                    novelId=adaptation.novelId,
                    shotId=shot.id,
                    shotKey=shot.shotKey,
                    shotPlanVersionId=plan_id,
                    promptVersionId=prompt.id,
                    promptContentHash=prompt.contentHash,
                    promptText=prompt.currentText,
                    providerPromptText=provider_prompt if keyframes else None,
                    sourceTimelineDurationMs=shot.timelineDurationMs,
                    model=model,
                    ratio=cast(AspectRatio, project.targetAspectRatio),
                    durationSeconds=request.durationSeconds,
                    resolution=request.resolution,
                    generateAudio=request.generateAudio,
                    watermark=request.watermark,
                    references=references,
                    keyframes=keyframes,
                )
                now = utc_now()
                task = VideoShotRenderTask(
                    id=generate_id(),
                    adaptationId=adaptation.id,
                    projectId=project.id,
                    novelId=adaptation.novelId,
                    shotId=shot.id,
                    shotPlanVersionId=plan_id,
                    promptVersionId=prompt.id,
                    retryOfTaskId=None,
                    provider="seedance",
                    model=model,
                    status="pending",
                    clientRequestId=request.clientRequestId,
                    inputHash=_manifest_hash(manifest),
                    requestManifestJson=manifest.model_dump_json(),
                    providerTaskId=None,
                    pollCount=0,
                    attemptCount=0,
                    nextAttemptAt=now,
                    lastErrorCode=None,
                    lastErrorMessage=None,
                    createdAt=now,
                    updatedAt=now,
                    submittedAt=None,
                    completedAt=None,
                )
                session.add(task)
                await session.flush()
                return _task_response(task, manifest)

    async def retry_task(
        self,
        user_id: str,
        task_id: str,
        request: RetryShotRenderRequest,
        *,
        reference_transport_configured: bool,
    ) -> ShotRenderTaskResponse:
        async with self._session_factory() as session:
            async with session.begin():
                source = await _require_owned_task(session, user_id, task_id, lock=True)
                await _lock_render_request(
                    session,
                    namespace="render-task",
                    identity=source.shotId,
                    client_request_id=request.clientRequestId,
                )
                existing = await session.scalar(
                    select(VideoShotRenderTask).where(
                        VideoShotRenderTask.shotId == source.shotId,
                        VideoShotRenderTask.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    if existing.retryOfTaskId != source.id:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_RENDER_CLIENT_REQUEST_REUSED",
                            message="clientRequestId 已用于另一条视频任务",
                        )
                    return _task_response(existing, _parse_manifest(existing))
                if source.status not in _TASK_TERMINAL_STATUSES:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_RENDER_TASK_STILL_ACTIVE",
                        message="当前任务仍在执行，不能重复提交同一输入",
                    )
                _adaptation, _project, adaptation_head = await _require_owned_context(
                    session,
                    user_id=user_id,
                    adaptation_id=source.adaptationId,
                    lock=True,
                )
                if adaptation_head.currentShotPlanVersionId != source.shotPlanVersionId:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_RENDER_RETRY_STALE_PLAN",
                        message="原任务不属于当前正式镜头方案，请从当前镜头重新生成候选",
                    )
                locked_shot = await session.scalar(
                    select(VideoShot.id)
                    .where(
                        VideoShot.id == source.shotId,
                        VideoShot.planVersionId == source.shotPlanVersionId,
                    )
                    .with_for_update()
                )
                if locked_shot is None:
                    raise RuntimeError("原逐镜视频任务引用的正式镜头不存在")
                await _require_no_active_task(session, source.shotId)
                manifest = _parse_manifest(source)
                if (
                    manifest.references or manifest.keyframes
                ) and not reference_transport_configured:
                    raise ApiError(
                        status_code=503,
                        code="VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED",
                        message="当前环境尚未配置供应商可访问的视觉参考图地址",
                    )
                now = utc_now()
                retry = VideoShotRenderTask(
                    id=generate_id(),
                    adaptationId=source.adaptationId,
                    projectId=source.projectId,
                    novelId=source.novelId,
                    shotId=source.shotId,
                    shotPlanVersionId=source.shotPlanVersionId,
                    promptVersionId=source.promptVersionId,
                    retryOfTaskId=source.id,
                    provider=source.provider,
                    model=source.model,
                    status="pending",
                    clientRequestId=request.clientRequestId,
                    inputHash=source.inputHash,
                    requestManifestJson=source.requestManifestJson,
                    providerTaskId=None,
                    pollCount=0,
                    attemptCount=0,
                    nextAttemptAt=now,
                    lastErrorCode=None,
                    lastErrorMessage=None,
                    createdAt=now,
                    updatedAt=now,
                    submittedAt=None,
                    completedAt=None,
                )
                session.add(retry)
                await session.flush()
                return _task_response(retry, manifest)

    async def get_task(self, user_id: str, task_id: str) -> ShotRenderTaskResponse:
        async with self._session_factory() as session:
            task = await _require_owned_task(session, user_id, task_id, lock=False)
            return _task_response(task, _parse_manifest(task))

    async def get_workspace(
        self,
        user_id: str,
        adaptation_id: str,
        readiness: VideoRenderReadinessResponse,
    ) -> ChapterRenderWorkspaceResponse:
        async with self._session_factory() as session:
            adaptation, _project, head = await _require_owned_context(
                session,
                user_id=user_id,
                adaptation_id=adaptation_id,
                lock=False,
            )
            plan_id = head.currentShotPlanVersionId
            if plan_id is None:
                return ChapterRenderWorkspaceResponse(
                    adaptationId=adaptation.id,
                    readiness=readiness,
                    tasks=[],
                    takes=[],
                    takeHeads=[],
                )
            tasks = list(
                (
                    await session.scalars(
                        select(VideoShotRenderTask)
                        .where(
                            VideoShotRenderTask.adaptationId == adaptation.id,
                            VideoShotRenderTask.shotPlanVersionId == plan_id,
                        )
                        .order_by(
                            VideoShotRenderTask.createdAt.desc(),
                            VideoShotRenderTask.id.desc(),
                        )
                    )
                ).all()
            )
            take_rows = (
                await session.execute(
                    select(VideoShotTake, VideoAsset)
                    .join(VideoAsset, VideoAsset.id == VideoShotTake.assetId)
                    .where(
                        VideoShotTake.adaptationId == adaptation.id,
                        VideoShotTake.shotPlanVersionId == plan_id,
                    )
                    .order_by(VideoShotTake.shotId, VideoShotTake.takeNo)
                )
            ).all()
            heads = list(
                (
                    await session.scalars(
                        select(VideoShotTakeHead).where(
                            VideoShotTakeHead.shotPlanVersionId == plan_id
                        )
                    )
                ).all()
            )
            head_by_shot = {item.shotId: item for item in heads}
            shot_ids = list(
                (
                    await session.scalars(
                        select(VideoShot.id).where(VideoShot.planVersionId == plan_id)
                    )
                ).all()
            )
            now = utc_now()
            take_heads = [
                _head_response(head_by_shot.get(shot_id), shot_id, now)
                for shot_id in shot_ids
            ]
            return ChapterRenderWorkspaceResponse(
                adaptationId=adaptation.id,
                readiness=readiness,
                tasks=[_task_response(item, _parse_manifest(item)) for item in tasks],
                takes=[_take_response(take, asset) for take, asset in take_rows],
                takeHeads=take_heads,
            )

    async def confirm_take(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        take_id: str,
        request: ConfirmShotTakeRequest,
    ) -> ShotTakeDecisionResponse:
        request_hash = _decision_hash(
            user_id=user_id,
            adaptation_id=adaptation_id,
            shot_id=shot_id,
            take_id=take_id,
            request=request,
        )
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_render_request(
                    session,
                    namespace="take-decision",
                    identity=user_id,
                    client_request_id=request.clientRequestId,
                )
                existing = await session.scalar(
                    select(VideoShotTakeDecisionCommand).where(
                        VideoShotTakeDecisionCommand.requestedByUserId == user_id,
                        VideoShotTakeDecisionCommand.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    if existing.requestHash != request_hash:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_TAKE_CLIENT_REQUEST_REUSED",
                            message="clientRequestId 已用于不同的选片确认请求",
                        )
                    return _decision_response(existing)
                adaptation, _project, head = await _require_owned_context(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                take = await session.scalar(
                    select(VideoShotTake).where(
                        VideoShotTake.id == take_id,
                        VideoShotTake.shotId == shot_id,
                        VideoShotTake.adaptationId == adaptation.id,
                    )
                )
                if take is None or take.shotPlanVersionId != head.currentShotPlanVersionId:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_TAKE_NOT_FOUND",
                        message="当前正式方案中不存在该候选 Take",
                    )
                take_head = await session.scalar(
                    select(VideoShotTakeHead)
                    .where(VideoShotTakeHead.shotId == shot_id)
                    .with_for_update()
                )
                now = utc_now()
                if take_head is None:
                    take_head = VideoShotTakeHead(
                        shotId=shot_id,
                        shotPlanVersionId=take.shotPlanVersionId,
                        currentTakeId=None,
                        revision=1,
                        updatedAt=now,
                    )
                    session.add(take_head)
                    await session.flush()
                status: Literal["succeeded", "conflict"]
                resulting_revision: int | None
                error_code: str | None
                if take_head.revision != request.expectedTakeRevision:
                    status = "conflict"
                    resulting_revision = None
                    error_code = "VIDEO_TAKE_REVISION_CONFLICT"
                else:
                    take_head.currentTakeId = take.id
                    take_head.revision += 1
                    take_head.updatedAt = now
                    status = "succeeded"
                    resulting_revision = take_head.revision
                    error_code = None
                command = VideoShotTakeDecisionCommand(
                    id=generate_id(),
                    requestedByUserId=user_id,
                    novelId=adaptation.novelId,
                    projectId=adaptation.projectId,
                    adaptationId=adaptation.id,
                    shotId=shot_id,
                    takeId=take.id,
                    clientRequestId=request.clientRequestId,
                    expectedRevision=request.expectedTakeRevision,
                    requestHash=request_hash,
                    status=status,
                    observedCurrentTakeId=take_head.currentTakeId,
                    resultingRevision=resulting_revision,
                    errorCode=error_code,
                    createdAt=now,
                )
                session.add(command)
                await session.flush()
                return _decision_response(command)

    async def get_take_file(self, user_id: str, take_id: str) -> VideoAssetFile:
        async with self._session_factory() as session:
            row = await session.execute(
                select(VideoAsset)
                .join(VideoShotTake, VideoShotTake.assetId == VideoAsset.id)
                .join(VideoProject, VideoProject.id == VideoShotTake.projectId)
                .join(Novel, Novel.id == VideoProject.novelId)
                .where(VideoShotTake.id == take_id, Novel.userId == user_id)
            )
            asset = row.scalar_one_or_none()
            if asset is None:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_TAKE_NOT_FOUND",
                    message="候选 Take 不存在",
                )
            return VideoAssetFile(
                storage_key=asset.storageKey,
                mime_type=asset.mimeType,
                name=asset.name,
            )

    async def get_provider_asset_file(self, asset_id: str, sha256: str) -> VideoAssetFile:
        async with self._session_factory() as session:
            asset = await session.scalar(
                select(VideoAsset).where(
                    VideoAsset.id == asset_id,
                    VideoAsset.sha256 == sha256,
                    VideoAsset.modality == "image",
                    VideoAsset.rightsStatus == "confirmed",
                    VideoAsset.lockedAt.is_not(None),
                )
            )
            if asset is None:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_PROVIDER_ASSET_NOT_FOUND",
                    message="供应商参考素材不存在或不可用",
                )
            return VideoAssetFile(
                storage_key=asset.storageKey,
                mime_type=asset.mimeType,
                name=asset.name,
            )

    async def claim_due_tasks(self, limit: int) -> list[ShotRenderClaim]:
        if limit < 1:
            raise ValueError("逐镜渲染任务领取数量必须为正整数")
        now = utc_now()
        # submit/query 都是有界短调用；90 秒租约覆盖 Agent 40 秒超时，同时让崩溃
        # 恢复保持在可接受窗口内。归档开始后会单独续到三分钟。
        lease_until = now + timedelta(seconds=90)
        async with self._session_factory() as session:
            async with session.begin():
                tasks = list(
                    (
                        await session.scalars(
                            select(VideoShotRenderTask)
                            .where(
                                VideoShotRenderTask.status.in_(
                                    {"pending", "submitting", *_TASK_QUERY_STATUSES}
                                ),
                                VideoShotRenderTask.nextAttemptAt <= now,
                            )
                            .order_by(
                                VideoShotRenderTask.nextAttemptAt,
                                VideoShotRenderTask.createdAt,
                            )
                            .limit(limit)
                            .with_for_update(skip_locked=True)
                        )
                    ).all()
                )
                claims: list[ShotRenderClaim] = []
                for task in tasks:
                    if task.status == "submitting":
                        task.status = "submission_unknown"
                        task.lastErrorCode = "SEEDANCE_SUBMISSION_RECOVERY_UNKNOWN"
                        task.lastErrorMessage = (
                            "服务在供应商创建请求期间中断，未自动重提以避免重复计费"
                        )
                        task.completedAt = now
                        task.updatedAt = now
                        continue
                    manifest = _parse_manifest(task)
                    if task.status == "pending":
                        task.status = "submitting"
                        task.attemptCount += 1
                        claimed_status = "submitting"
                    else:
                        task.pollCount += 1
                        claimed_status = task.status
                    task.nextAttemptAt = lease_until
                    task.updatedAt = now
                    claims.append(
                        ShotRenderClaim(
                            task_id=task.id,
                            project_id=task.projectId,
                            novel_id=task.novelId,
                            status=claimed_status,
                            provider_task_id=task.providerTaskId,
                            poll_count=task.pollCount,
                            manifest=manifest,
                        )
                    )
        return claims

    async def mark_submitted(self, task_id: str, provider_task_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoShotRenderTask, task_id, with_for_update=True)
                if task is None or task.status != "submitting":
                    return
                now = utc_now()
                task.providerTaskId = provider_task_id
                task.status = "queued"
                task.submittedAt = now
                task.nextAttemptAt = now + timedelta(seconds=5)
                task.lastErrorCode = None
                task.lastErrorMessage = None
                task.updatedAt = now

    async def mark_submission_unknown(self, task_id: str, message: str) -> None:
        await self._finish_task(
            task_id,
            expected={"submitting"},
            status="submission_unknown",
            code="SEEDANCE_SUBMISSION_UNKNOWN",
            message=message,
        )

    async def mark_submission_rejected(self, task_id: str, code: str, message: str) -> None:
        await self._finish_task(
            task_id,
            expected={"submitting"},
            status="failed",
            code=code,
            message=message,
        )

    async def mark_query_progress(self, task_id: str, status: Literal["queued", "running"]) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoShotRenderTask, task_id, with_for_update=True)
                if task is None or task.status not in _TASK_QUERY_STATUSES:
                    return
                now = utc_now()
                task.status = status
                task.nextAttemptAt = now + _poll_backoff(task.pollCount)
                task.lastErrorCode = None
                task.lastErrorMessage = None
                task.updatedAt = now

    async def mark_query_error(self, task_id: str, message: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoShotRenderTask, task_id, with_for_update=True)
                if task is None or task.status not in _TASK_QUERY_STATUSES:
                    return
                now = utc_now()
                task.attemptCount += 1
                task.nextAttemptAt = now + _poll_backoff(task.pollCount)
                task.lastErrorCode = "SEEDANCE_QUERY_RETRY"
                task.lastErrorMessage = message[:2_000]
                task.updatedAt = now

    async def begin_archiving(self, task_id: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoShotRenderTask, task_id, with_for_update=True)
                if task is None or task.status not in _TASK_QUERY_STATUSES:
                    return False
                task.status = "archiving"
                task.nextAttemptAt = utc_now() + timedelta(minutes=3)
                task.updatedAt = utc_now()
                return True

    async def mark_provider_terminal(
        self,
        task_id: str,
        *,
        status: Literal["failed", "expired", "cancelled"],
        code: str,
        message: str,
    ) -> None:
        await self._finish_task(
            task_id,
            expected=_TASK_QUERY_STATUSES,
            status=status,
            code=code,
            message=message,
        )

    async def fail_archiving(self, task_id: str, message: str) -> bool:
        return await self._finish_task(
            task_id,
            expected={"archiving"},
            status="failed",
            code="SEEDANCE_RESULT_ARCHIVE_FAILED",
            message=message,
        )

    async def complete_take(
        self,
        task_id: str,
        completed: CompletedTakeInput,
    ) -> ShotTakeResponse:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoShotRenderTask, task_id, with_for_update=True)
                if task is None:
                    raise RuntimeError("逐镜渲染任务不存在")
                existing = await session.scalar(
                    select(VideoShotTake).where(VideoShotTake.taskId == task.id)
                )
                if existing is not None:
                    asset = await session.get(VideoAsset, existing.assetId)
                    if asset is None:
                        raise RuntimeError("已完成 Take 缺少受控素材")
                    return _take_response(existing, asset)
                if task.status != "archiving" or task.providerTaskId is None:
                    raise RuntimeError("逐镜渲染任务不在归档阶段")
                await session.scalar(
                    select(VideoShot).where(VideoShot.id == task.shotId).with_for_update()
                )
                next_take_no = int(
                    (
                        await session.scalar(
                            select(func.coalesce(func.max(VideoShotTake.takeNo), 0)).where(
                                VideoShotTake.shotId == task.shotId
                            )
                        )
                    )
                    or 0
                ) + 1
                manifest = _parse_manifest(task)
                now = utc_now()
                asset = VideoAsset(
                    id=completed.asset_id,
                    projectId=task.projectId,
                    name=f"{manifest.shotKey} · Take {next_take_no}",
                    modality="video",
                    duty="motion",
                    mimeType=completed.stored.mime_type,
                    byteSize=completed.stored.byte_size,
                    durationMs=completed.duration_ms,
                    sha256=completed.stored.sha256,
                    sourceKind="model_generated",
                    rightsStatus="confirmed",
                    lockedAt=now,
                    storageKey=completed.stored.storage_key,
                    createdAt=now,
                    updatedAt=now,
                )
                take = VideoShotTake(
                    id=generate_id(),
                    taskId=task.id,
                    adaptationId=task.adaptationId,
                    projectId=task.projectId,
                    novelId=task.novelId,
                    shotId=task.shotId,
                    shotPlanVersionId=task.shotPlanVersionId,
                    promptVersionId=task.promptVersionId,
                    assetId=asset.id,
                    takeNo=next_take_no,
                    provider=task.provider,
                    model=task.model,
                    providerTaskId=task.providerTaskId,
                    inputHash=task.inputHash,
                    providerMetadataJson=json.dumps(
                        completed.provider_metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    createdAt=now,
                )
                session.add_all([asset, take])
                task.status = "succeeded"
                task.lastErrorCode = None
                task.lastErrorMessage = None
                task.completedAt = now
                task.nextAttemptAt = now
                task.updatedAt = now
                await session.flush()
                return _take_response(take, asset)

    async def _finish_task(
        self,
        task_id: str,
        *,
        expected: set[str],
        status: str,
        code: str,
        message: str,
    ) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoShotRenderTask, task_id, with_for_update=True)
                if task is None or task.status not in expected:
                    return False
                now = utc_now()
                task.status = status
                task.lastErrorCode = code[:240]
                task.lastErrorMessage = message[:2_000]
                task.completedAt = now
                task.nextAttemptAt = now
                task.updatedAt = now
                return True


async def _lock_render_request(
    session: AsyncSession,
    *,
    namespace: str,
    identity: str,
    client_request_id: str,
) -> None:
    """串行化渲染和选片幂等键，避免并发插入唯一约束竞争。"""

    digest = hashlib.sha256(
        f"video-shot-render\0{namespace}\0{identity}\0{client_request_id}".encode()
    ).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


async def _require_owned_context(
    session: AsyncSession,
    *,
    user_id: str,
    adaptation_id: str,
    lock: bool,
) -> tuple[VideoChapterAdaptation, VideoProject, VideoChapterAdaptationHead]:
    query = (
        select(VideoChapterAdaptation, VideoProject, VideoChapterAdaptationHead)
        .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .join(
            VideoChapterAdaptationHead,
            VideoChapterAdaptationHead.adaptationId == VideoChapterAdaptation.id,
        )
        .where(VideoChapterAdaptation.id == adaptation_id, Novel.userId == user_id)
    )
    if lock:
        query = query.with_for_update(of=VideoChapterAdaptationHead)
    row = (await session.execute(query)).one_or_none()
    if row is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_ADAPTATION_NOT_FOUND",
            message="章节影视化改编不存在",
        )
    return row[0], row[1], row[2]


async def _require_owned_task(
    session: AsyncSession,
    user_id: str,
    task_id: str,
    *,
    lock: bool,
) -> VideoShotRenderTask:
    query = (
        select(VideoShotRenderTask)
        .join(
            VideoChapterAdaptation,
            VideoChapterAdaptation.id == VideoShotRenderTask.adaptationId,
        )
        .join(VideoProject, VideoProject.id == VideoChapterAdaptation.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(VideoShotRenderTask.id == task_id, Novel.userId == user_id)
    )
    if lock:
        query = query.with_for_update(of=VideoShotRenderTask)
    task = await session.scalar(query)
    if task is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_RENDER_TASK_NOT_FOUND",
            message="逐镜视频任务不存在",
        )
    return task


async def _load_prompt_reference_manifest(
    session: AsyncSession,
    prompt_version_id: str,
) -> list[ShotRenderReferenceManifest]:
    rows = (
        await session.execute(
            select(
                VideoShotPromptVisualReference,
                VideoVisualCanonVersion,
                VideoVisualCanon,
                VideoAsset,
            )
            .join(
                VideoVisualCanonVersion,
                VideoVisualCanonVersion.id
                == VideoShotPromptVisualReference.canonVersionId,
            )
            .join(VideoVisualCanon, VideoVisualCanon.id == VideoVisualCanonVersion.canonId)
            .join(VideoAsset, VideoAsset.id == VideoVisualCanonVersion.assetId)
            .where(VideoShotPromptVisualReference.promptVersionId == prompt_version_id)
            .order_by(VideoShotPromptVisualReference.ordinal)
        )
    ).all()
    references: list[ShotRenderReferenceManifest] = []
    for binding, _version, canon, asset in rows:
        if (
            asset.modality != "image"
            or asset.rightsStatus != "confirmed"
            or asset.lockedAt is None
        ):
            raise ApiError(
                status_code=409,
                code="VIDEO_RENDER_REFERENCE_NOT_READY",
                message=f"视觉参考“{canon.settingName}”未完成权利确认和锁定",
            )
        references.append(
            ShotRenderReferenceManifest(
                ordinal=binding.ordinal,
                canonVersionId=binding.canonVersionId,
                assetId=asset.id,
                sha256=asset.sha256,
                mimeType=asset.mimeType,
                duty=cast(VisualCanonDuty, canon.duty),
                strength=binding.strength,
            )
        )
    return references


async def _load_keyframe_manifest(
    session: AsyncSession,
    shot_id: str,
) -> list[ShotRenderKeyframeManifest]:
    rows = (
        await session.execute(
            select(VideoShotKeyframeHead, VideoShotKeyframeVersion, VideoAsset)
            .join(
                VideoShotKeyframeVersion,
                VideoShotKeyframeVersion.id == VideoShotKeyframeHead.currentVersionId,
            )
            .join(VideoAsset, VideoAsset.id == VideoShotKeyframeVersion.assetId)
            .where(VideoShotKeyframeHead.shotId == shot_id)
        )
    ).all()
    role_order = {
        "initial_state": 1,
        "transition_anchor": 2,
        "end_state": 3,
    }
    result: list[ShotRenderKeyframeManifest] = []
    for head, version, asset in sorted(
        rows,
        key=lambda row: role_order.get(row[0].role, 99),
    ):
        ordinal = role_order.get(head.role)
        if ordinal is None:
            raise ApiError(
                status_code=409,
                code="VIDEO_RENDER_KEYFRAME_ROLE_INVALID",
                message="当前关键帧包含未知角色",
            )
        if (
            version.shotId != shot_id
            or version.role != head.role
            or asset.modality != "image"
            or asset.duty not in {"keyframe", "storyboard"}
            or asset.rightsStatus != "confirmed"
            or asset.lockedAt is None
        ):
            raise ApiError(
                status_code=409,
                code="VIDEO_RENDER_KEYFRAME_NOT_READY",
                message="当前关键帧素材不存在或未完成权利确认和锁定",
            )
        result.append(
            ShotRenderKeyframeManifest(
                ordinal=ordinal,
                keyframeVersionId=version.id,
                role=cast(
                    Literal["initial_state", "transition_anchor", "end_state"],
                    version.role,
                ),
                assetId=asset.id,
                sha256=asset.sha256,
                mimeType=asset.mimeType,
                duty=cast(Literal["storyboard", "keyframe"], asset.duty),
            )
        )
    return result


def _provider_prompt(
    prompt_text: str,
    references: list[ShotRenderReferenceManifest],
    keyframes: list[ShotRenderKeyframeManifest],
) -> str:
    if not keyframes:
        return prompt_text
    image_index = 1
    instructions: list[str] = []
    by_role = {frame.role: frame for frame in keyframes}
    if "initial_state" in by_role:
        instructions.append(f"图片{image_index}严格作为首帧构图与人物状态")
        image_index += 1
    image_index += len(references)
    if "transition_anchor" in by_role:
        instructions.append(f"图片{image_index}作为镜头中段的状态过渡锚点")
        image_index += 1
    if "end_state" in by_role:
        instructions.append(f"图片{image_index}严格作为尾帧状态与最终构图")
    return f"关键帧控制：{'；'.join(instructions)}。\n{prompt_text}"


async def _require_no_active_task(session: AsyncSession, shot_id: str) -> None:
    active = await session.scalar(
        select(VideoShotRenderTask.id).where(
            VideoShotRenderTask.shotId == shot_id,
            VideoShotRenderTask.status.in_(
                {"pending", "submitting", "queued", "running", "archiving"}
            ),
        )
    )
    if active is not None:
        raise ApiError(
            status_code=409,
            code="VIDEO_RENDER_SHOT_TASK_ACTIVE",
            message="当前镜头已有生成任务在执行，请等待完成后再创建新候选",
        )


def _manifest_hash(manifest: VideoShotRenderManifest) -> str:
    encoded = json.dumps(
        manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _parse_manifest(task: VideoShotRenderTask) -> VideoShotRenderManifest:
    try:
        manifest = VideoShotRenderManifest.model_validate_json(task.requestManifestJson)
    except ValidationError as exc:
        raise RuntimeError("逐镜视频任务 manifest 已损坏") from exc
    if _manifest_hash(manifest) != task.inputHash:
        raise RuntimeError("逐镜视频任务 manifest 哈希不一致")
    return manifest


def _validate_start_replay(
    task: VideoShotRenderTask,
    manifest: VideoShotRenderManifest,
    adaptation_id: str,
    request: StartShotRenderRequest,
) -> None:
    if (
        task.adaptationId != adaptation_id
        or manifest.durationSeconds != request.durationSeconds
        or manifest.resolution != request.resolution
        or manifest.generateAudio != request.generateAudio
        or manifest.watermark != request.watermark
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_RENDER_CLIENT_REQUEST_REUSED",
            message="clientRequestId 已用于不同的视频生成请求",
        )


def _task_response(
    task: VideoShotRenderTask,
    manifest: VideoShotRenderManifest,
) -> ShotRenderTaskResponse:
    return ShotRenderTaskResponse(
        id=task.id,
        adaptationId=task.adaptationId,
        shotId=task.shotId,
        shotPlanVersionId=task.shotPlanVersionId,
        promptVersionId=task.promptVersionId,
        retryOfTaskId=task.retryOfTaskId,
        provider=cast(Literal["seedance"], task.provider),
        model=task.model,
        status=cast(ShotRenderTaskStatus, task.status),
        inputHash=task.inputHash,
        manifest=manifest,
        providerTaskId=task.providerTaskId,
        pollCount=task.pollCount,
        attemptCount=task.attemptCount,
        lastErrorCode=task.lastErrorCode,
        lastErrorMessage=task.lastErrorMessage,
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
        submittedAt=task.submittedAt,
        completedAt=task.completedAt,
    )


def _take_response(take: VideoShotTake, asset: VideoAsset) -> ShotTakeResponse:
    metadata = json.loads(take.providerMetadataJson)
    if not isinstance(metadata, dict):
        raise RuntimeError("候选 Take 的供应商元数据无效")
    return ShotTakeResponse(
        id=take.id,
        taskId=take.taskId,
        adaptationId=take.adaptationId,
        shotId=take.shotId,
        shotPlanVersionId=take.shotPlanVersionId,
        promptVersionId=take.promptVersionId,
        takeNo=take.takeNo,
        provider=cast(Literal["seedance"], take.provider),
        model=take.model,
        providerTaskId=take.providerTaskId,
        inputHash=take.inputHash,
        providerMetadata=cast(dict[str, object], metadata),
        asset=_asset_response(asset),
        createdAt=take.createdAt,
    )


def _asset_response(asset: VideoAsset) -> VideoAssetResponse:
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


def _head_response(
    head: VideoShotTakeHead | None,
    shot_id: str,
    fallback_time: datetime,
) -> ShotTakeHeadResponse:
    if head is not None:
        return ShotTakeHeadResponse(
            shotId=head.shotId,
            currentTakeId=head.currentTakeId,
            revision=head.revision,
            updatedAt=head.updatedAt,
        )
    return ShotTakeHeadResponse(
        shotId=shot_id,
        currentTakeId=None,
        revision=1,
        updatedAt=fallback_time,
    )


def _decision_hash(
    *,
    user_id: str,
    adaptation_id: str,
    shot_id: str,
    take_id: str,
    request: ConfirmShotTakeRequest,
) -> str:
    payload = {
        "userId": user_id,
        "adaptationId": adaptation_id,
        "shotId": shot_id,
        "takeId": take_id,
        "expectedTakeRevision": request.expectedTakeRevision,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _decision_response(command: VideoShotTakeDecisionCommand) -> ShotTakeDecisionResponse:
    return ShotTakeDecisionResponse(
        commandId=command.id,
        status=cast(Literal["succeeded", "conflict", "rejected"], command.status),
        shotId=command.shotId,
        takeId=command.takeId,
        currentTakeId=command.observedCurrentTakeId,
        resultingRevision=command.resultingRevision,
        errorCode=command.errorCode,
    )


def _poll_backoff(poll_count: int) -> timedelta:
    return timedelta(seconds=min(5 + max(poll_count - 1, 0) * 2, 30))

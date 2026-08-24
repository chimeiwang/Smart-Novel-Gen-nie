"""P1–P3 关键帧、粗剪、声音字幕和整集导出的 PostgreSQL 实现。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, cast

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...db.base import generate_id, utc_now
from ...db.models import (
    Novel,
    VideoAsset,
    VideoChapterAdaptation,
    VideoChapterAdaptationHead,
    VideoEpisodeAudioClip,
    VideoEpisodeBoundary,
    VideoEpisodeEditClip,
    VideoEpisodeEditHead,
    VideoEpisodeEditVersion,
    VideoEpisodeExport,
    VideoEpisodeExportTask,
    VideoEpisodeMixHead,
    VideoEpisodeMixVersion,
    VideoEpisodePlanVersion,
    VideoEpisodeSubtitleCue,
    VideoProject,
    VideoShot,
    VideoShotKeyframeHead,
    VideoShotKeyframeVersion,
    VideoShotPromptHead,
    VideoShotPromptVisualReference,
    VideoShotTake,
    VideoShotTakeHead,
    VideoTakeFrameExtraction,
    VideoVisualCanon,
    VideoVisualCanonVersion,
)
from ...errors import ApiError
from ..repository import VideoAssetFile
from ..storage import StoredVideoAsset
from .post_production_manifest import (
    FrozenExportAsset,
    FrozenExportAudioClip,
    FrozenExportSubtitleCue,
    FrozenExportVideoClip,
    VideoEpisodeExportManifest,
)
from .post_production_schemas import (
    ChapterPostProductionWorkspaceResponse,
    ContinuityIssueResponse,
    EpisodeAudioClipResponse,
    EpisodeEditClipInput,
    EpisodeEditClipResponse,
    EpisodeEditHeadResponse,
    EpisodeEditVersionResponse,
    EpisodeEditVersionSummaryResponse,
    EpisodeExportResponse,
    EpisodeExportTaskResponse,
    EpisodeMixHeadResponse,
    EpisodeMixVersionResponse,
    EpisodeMixVersionSummaryResponse,
    EpisodePostProductionResponse,
    EpisodeShotResponse,
    EpisodeSubtitleCueInput,
    EpisodeSubtitleCueResponse,
    ExportTaskStatus,
    PostProductionAssetResponse,
    PostProductionReadinessResponse,
    PostProductionTakeResponse,
    RetryEpisodeExportRequest,
    SaveEpisodeEditVersionRequest,
    SaveEpisodeMixVersionRequest,
    SaveShotKeyframeVersionRequest,
    ShotKeyframeHeadResponse,
    ShotKeyframeVersionResponse,
    ShotPostProductionResponse,
    StartEpisodeExportRequest,
)

_KEYFRAME_ROLES = ("initial_state", "transition_anchor", "end_state")
_EXPORT_RETRYABLE_STATUSES = {"failed"}


@dataclass(frozen=True, slots=True)
class OwnedPostProductionContext:
    adaptation: VideoChapterAdaptation
    project: VideoProject
    head: VideoChapterAdaptationHead
    episode_plan: VideoEpisodePlanVersion
    shots: list[VideoShot]
    episodes: list[list[VideoShot]]


@dataclass(frozen=True, slots=True)
class TakeFrameSource:
    take_id: str
    shot_id: str
    adaptation_id: str
    project_id: str
    novel_id: str
    storage_key: str
    sha256: str
    duration_ms: int | None


@dataclass(frozen=True, slots=True)
class EpisodeExportClaim:
    task_id: str
    project_id: str
    manifest: VideoEpisodeExportManifest


class VideoPostProductionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_workspace(
        self,
        user_id: str,
        adaptation_id: str,
        readiness: PostProductionReadinessResponse,
    ) -> ChapterPostProductionWorkspaceResponse:
        async with self._session_factory() as session:
            context = await _require_context(
                session,
                user_id=user_id,
                adaptation_id=adaptation_id,
                lock=False,
            )
            assets = list(
                (
                    await session.scalars(
                        select(VideoAsset)
                        .where(
                            VideoAsset.projectId == context.project.id,
                            VideoAsset.rightsStatus == "confirmed",
                            VideoAsset.lockedAt.is_not(None),
                        )
                        .order_by(VideoAsset.createdAt, VideoAsset.id)
                    )
                ).all()
            )
            keyframe_assets = [
                _asset_response(asset)
                for asset in assets
                if asset.modality == "image" and asset.duty in {"keyframe", "storyboard"}
            ]
            audio_assets = [
                _asset_response(asset)
                for asset in assets
                if asset.modality == "audio"
                and asset.duty in {"voice", "ambience", "sfx", "music"}
            ]
            shot_workspaces = await _load_keyframe_workspace(session, context)
            continuity = await _load_continuity_issues(session, context, shot_workspaces)
            episodes = [
                await _load_episode_workspace(session, context, episode_no, episode_shots)
                for episode_no, episode_shots in enumerate(context.episodes, start=1)
            ]
            return ChapterPostProductionWorkspaceResponse(
                adaptationId=context.adaptation.id,
                projectId=context.project.id,
                novelId=context.adaptation.novelId,
                shotPlanVersionId=cast(str, context.head.currentShotPlanVersionId),
                episodePlanVersionId=context.episode_plan.id,
                readiness=readiness,
                keyframeAssets=keyframe_assets,
                audioAssets=audio_assets,
                shots=shot_workspaces,
                continuityIssues=continuity,
                episodes=episodes,
            )

    async def save_keyframe(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        request: SaveShotKeyframeVersionRequest,
    ) -> ShotKeyframeHeadResponse:
        request_hash = _hash_payload(
            {
                "adaptationId": adaptation_id,
                "shotId": shot_id,
                **request.model_dump(mode="json"),
            }
        )
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_post_production_request(
                    session,
                    namespace="keyframe",
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                )
                existing = await session.scalar(
                    select(VideoShotKeyframeVersion).where(
                        VideoShotKeyframeVersion.createdByUserId == user_id,
                        VideoShotKeyframeVersion.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    if existing.requestHash != request_hash:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_KEYFRAME_CLIENT_REQUEST_REUSED",
                            message="clientRequestId 已用于不同的关键帧请求",
                        )
                    return await _keyframe_head_response(
                        session,
                        shot_id=existing.shotId,
                        role=existing.role,
                    )

                context = await _require_context(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                plan_id = cast(str, context.head.currentShotPlanVersionId)
                shot = next((item for item in context.shots if item.id == shot_id), None)
                if shot is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_KEYFRAME_SHOT_NOT_FOUND",
                        message="当前正式方案中不存在该镜头",
                    )
                head = await session.scalar(
                    select(VideoShotKeyframeHead)
                    .where(
                        VideoShotKeyframeHead.shotId == shot.id,
                        VideoShotKeyframeHead.role == request.role,
                    )
                    .with_for_update()
                )
                now = utc_now()
                if head is None:
                    head = VideoShotKeyframeHead(
                        shotId=shot.id,
                        shotPlanVersionId=plan_id,
                        role=request.role,
                        currentVersionId=None,
                        revision=1,
                        updatedAt=now,
                    )
                    session.add(head)
                    await session.flush()
                if head.revision != request.expectedRevision:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_KEYFRAME_REVISION_CONFLICT",
                        message="关键帧已经变化，请刷新后重新确认",
                    )

                asset: VideoAsset | None = None
                source_kind: Literal["asset", "take_frame", "cleared"] = "cleared"
                if request.assetId is not None:
                    asset = await session.scalar(
                        select(VideoAsset).where(
                            VideoAsset.id == request.assetId,
                            VideoAsset.projectId == context.project.id,
                        )
                    )
                    if (
                        asset is None
                        or asset.modality != "image"
                        or asset.duty not in {"keyframe", "storyboard"}
                        or asset.rightsStatus != "confirmed"
                        or asset.lockedAt is None
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_KEYFRAME_ASSET_NOT_READY",
                            message="关键帧必须使用本项目已确认并锁定的 keyframe/storyboard 图片",
                        )
                    source_kind = "asset"
                if request.sourceTakeId is not None:
                    take = await session.scalar(
                        select(VideoShotTake).where(
                            VideoShotTake.id == request.sourceTakeId,
                            VideoShotTake.shotId == shot.id,
                            VideoShotTake.adaptationId == context.adaptation.id,
                        )
                    )
                    if take is None:
                        raise ApiError(
                            status_code=404,
                            code="VIDEO_KEYFRAME_SOURCE_TAKE_NOT_FOUND",
                            message="关键帧来源 Take 不存在",
                        )
                    take_asset = await session.get(VideoAsset, take.assetId)
                    if (
                        take_asset is None
                        or take_asset.durationMs is None
                        or request.sourceTimeMs is None
                        or request.sourceTimeMs >= take_asset.durationMs
                    ):
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_KEYFRAME_SOURCE_TIME_INVALID",
                            message="抽帧时间必须位于来源 Take 的已知时长内",
                        )
                    extraction = await session.scalar(
                        select(VideoTakeFrameExtraction).where(
                            VideoTakeFrameExtraction.assetId == request.assetId,
                            VideoTakeFrameExtraction.takeId == request.sourceTakeId,
                            VideoTakeFrameExtraction.timestampMs == request.sourceTimeMs,
                        )
                    )
                    if extraction is None:
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_KEYFRAME_EXTRACTION_NOT_PROVEN",
                            message="该图片没有与 Take 和时间点匹配的受控抽帧记录",
                        )
                    source_kind = "take_frame"

                version_no = int(
                    (
                        await session.scalar(
                            select(
                                func.coalesce(func.max(VideoShotKeyframeVersion.versionNo), 0)
                            ).where(
                                VideoShotKeyframeVersion.shotId == shot.id,
                                VideoShotKeyframeVersion.role == request.role,
                            )
                        )
                    )
                    or 0
                ) + 1
                content = {
                    "shotId": shot.id,
                    "role": request.role,
                    "assetId": asset.id if asset is not None else None,
                    "assetSha256": asset.sha256 if asset is not None else None,
                    "sourceKind": source_kind,
                    "sourceTakeId": request.sourceTakeId,
                    "sourceTimeMs": request.sourceTimeMs,
                }
                version = VideoShotKeyframeVersion(
                    id=generate_id(),
                    adaptationId=context.adaptation.id,
                    projectId=context.project.id,
                    novelId=context.adaptation.novelId,
                    shotId=shot.id,
                    shotPlanVersionId=plan_id,
                    role=request.role,
                    versionNo=version_no,
                    basedOnVersionId=head.currentVersionId,
                    assetId=asset.id if asset is not None else None,
                    sourceKind=source_kind,
                    sourceTakeId=request.sourceTakeId,
                    sourceTimeMs=request.sourceTimeMs,
                    clientRequestId=request.clientRequestId,
                    requestHash=request_hash,
                    contentHash=_hash_payload(content),
                    createdByUserId=user_id,
                    createdAt=now,
                )
                session.add(version)
                await session.flush()
                head.currentVersionId = version.id
                head.revision += 1
                head.updatedAt = now
                await session.flush()
                return await _keyframe_head_response(
                    session,
                    shot_id=shot.id,
                    role=request.role,
                )

    async def get_take_frame_source(
        self,
        user_id: str,
        take_id: str,
        timestamp_ms: int,
    ) -> TakeFrameSource:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(VideoShotTake, VideoAsset)
                    .join(VideoAsset, VideoAsset.id == VideoShotTake.assetId)
                    .join(VideoProject, VideoProject.id == VideoShotTake.projectId)
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .where(VideoShotTake.id == take_id, Novel.userId == user_id)
                )
            ).one_or_none()
            if row is None:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_TAKE_NOT_FOUND",
                    message="候选 Take 不存在",
                )
            take, asset = row
            if (
                asset.modality != "video"
                or asset.rightsStatus != "confirmed"
                or asset.lockedAt is None
            ):
                raise ApiError(
                    status_code=409,
                    code="VIDEO_KEYFRAME_SOURCE_TAKE_NOT_READY",
                    message="来源 Take 的视频素材未确认、未锁定或类型无效",
                )
            if asset.durationMs is None or timestamp_ms >= asset.durationMs:
                raise ApiError(
                    status_code=422,
                    code="VIDEO_KEYFRAME_SOURCE_TIME_INVALID",
                    message="抽帧时间必须位于 Take 的已知时长内",
                )
            return TakeFrameSource(
                take_id=take.id,
                shot_id=take.shotId,
                adaptation_id=take.adaptationId,
                project_id=take.projectId,
                novel_id=take.novelId,
                storage_key=asset.storageKey,
                sha256=asset.sha256,
                duration_ms=asset.durationMs,
            )

    async def get_extraction_replay(
        self,
        user_id: str,
        client_request_id: str,
        request_hash: str,
    ) -> PostProductionAssetResponse | None:
        async with self._session_factory() as session:
            extraction = await session.scalar(
                select(VideoTakeFrameExtraction).where(
                    VideoTakeFrameExtraction.requestedByUserId == user_id,
                    VideoTakeFrameExtraction.clientRequestId == client_request_id,
                )
            )
            if extraction is None:
                return None
            if extraction.requestHash != request_hash:
                raise ApiError(
                    status_code=409,
                    code="VIDEO_KEYFRAME_EXTRACTION_REQUEST_REUSED",
                    message="clientRequestId 已用于不同的抽帧请求",
                )
            asset = await session.get(VideoAsset, extraction.assetId)
            if asset is None:
                raise ApiError(
                    status_code=409,
                    code="VIDEO_KEYFRAME_EXTRACTION_ASSET_MISSING",
                    message="既有抽帧记录缺少受控图片素材",
                )
            return _asset_response(asset)

    async def complete_extracted_frame(
        self,
        *,
        user_id: str,
        source: TakeFrameSource,
        asset_id: str,
        name: str,
        timestamp_ms: int,
        client_request_id: str,
        request_hash: str,
        stored: StoredVideoAsset,
    ) -> PostProductionAssetResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_post_production_request(
                    session,
                    namespace="frame-extraction",
                    user_id=user_id,
                    client_request_id=client_request_id,
                )
                replay = await session.scalar(
                    select(VideoTakeFrameExtraction).where(
                        VideoTakeFrameExtraction.requestedByUserId == user_id,
                        VideoTakeFrameExtraction.clientRequestId == client_request_id,
                    )
                )
                if replay is not None:
                    if (
                        replay.requestHash != request_hash
                        or replay.takeId != source.take_id
                        or replay.timestampMs != timestamp_ms
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_KEYFRAME_EXTRACTION_REQUEST_REUSED",
                            message="clientRequestId 已用于不同的抽帧请求",
                        )
                    replay_asset = await session.get(VideoAsset, replay.assetId)
                    if replay_asset is None:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_KEYFRAME_EXTRACTION_ASSET_MISSING",
                            message="既有抽帧记录缺少受控图片素材",
                        )
                    return _asset_response(replay_asset)
                owned = await session.scalar(
                    select(VideoProject.id)
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .where(VideoProject.id == source.project_id, Novel.userId == user_id)
                )
                if owned is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_PROJECT_NOT_FOUND",
                        message="视频项目不存在",
                    )
                existing = await session.get(VideoAsset, asset_id)
                if existing is not None:
                    if existing.projectId != source.project_id or existing.sha256 != stored.sha256:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_KEYFRAME_EXTRACTION_REUSED",
                            message="抽帧请求标识已用于不同结果",
                        )
                    extraction = await session.get(VideoTakeFrameExtraction, asset_id)
                    if (
                        extraction is None
                        or extraction.takeId != source.take_id
                        or extraction.timestampMs != timestamp_ms
                        or extraction.requestHash != request_hash
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_KEYFRAME_EXTRACTION_REUSED",
                            message="抽帧素材缺少匹配的来源事实",
                        )
                    return _asset_response(existing)
                now = utc_now()
                asset = VideoAsset(
                    id=asset_id,
                    projectId=source.project_id,
                    name=name,
                    modality="image",
                    duty="keyframe",
                    mimeType=stored.mime_type,
                    byteSize=stored.byte_size,
                    durationMs=None,
                    sha256=stored.sha256,
                    sourceKind="model_generated",
                    rightsStatus="confirmed",
                    lockedAt=now,
                    storageKey=stored.storage_key,
                    createdAt=now,
                    updatedAt=now,
                )
                session.add(asset)
                await session.flush()
                extraction = VideoTakeFrameExtraction(
                    assetId=asset.id,
                    takeId=source.take_id,
                    shotId=source.shot_id,
                    adaptationId=source.adaptation_id,
                    projectId=source.project_id,
                    novelId=source.novel_id,
                    timestampMs=timestamp_ms,
                    clientRequestId=client_request_id,
                    requestHash=request_hash,
                    requestedByUserId=user_id,
                    createdAt=now,
                )
                session.add(extraction)
                await session.flush()
                return _asset_response(asset)

    async def save_edit_version(
        self,
        user_id: str,
        adaptation_id: str,
        episode_no: int,
        request: SaveEpisodeEditVersionRequest,
    ) -> EpisodeEditHeadResponse:
        request_hash = _hash_payload(
            {
                "adaptationId": adaptation_id,
                "episodeNo": episode_no,
                **request.model_dump(mode="json"),
            }
        )
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_post_production_request(
                    session,
                    namespace="edit",
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                )
                existing = await session.scalar(
                    select(VideoEpisodeEditVersion).where(
                        VideoEpisodeEditVersion.createdByUserId == user_id,
                        VideoEpisodeEditVersion.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    if existing.requestHash != request_hash:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_EDIT_CLIENT_REQUEST_REUSED",
                            message="clientRequestId 已用于不同的粗剪请求",
                        )
                    return await _edit_head_response(
                        session,
                        episode_plan_id=existing.episodePlanVersionId,
                        episode_no=existing.episodeNo,
                    )

                context = await _require_context(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                episode_shots = _require_episode(context, episode_no)
                expected_shot_ids = {shot.id for shot in episode_shots}
                supplied_shot_ids = {clip.shotId for clip in request.clips}
                if supplied_shot_ids != expected_shot_ids or len(request.clips) != len(
                    episode_shots
                ):
                    raise ApiError(
                        status_code=422,
                        code="VIDEO_EDIT_SHOT_SET_MISMATCH",
                        message="粗剪必须让本集每个正式镜头恰好出现一次",
                    )
                head = await _get_or_create_edit_head(session, context, episode_no, lock=True)
                if head.revision != request.expectedRevision:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_EDIT_REVISION_CONFLICT",
                        message="粗剪版本已经变化，请刷新后重新保存",
                    )
                based_on_version_id = head.currentVersionId
                if request.basedOnVersionId is not None:
                    based_on = await session.scalar(
                        select(VideoEpisodeEditVersion).where(
                            VideoEpisodeEditVersion.id == request.basedOnVersionId,
                            VideoEpisodeEditVersion.episodePlanVersionId
                            == context.episode_plan.id,
                            VideoEpisodeEditVersion.episodeNo == episode_no,
                        )
                    )
                    if based_on is None:
                        raise ApiError(
                            status_code=404,
                            code="VIDEO_EDIT_BASE_VERSION_NOT_FOUND",
                            message="粗剪基线版本不存在或不属于当前分集",
                        )
                    based_on_version_id = based_on.id

                take_ids = [clip.takeId for clip in request.clips if clip.takeId is not None]
                take_rows = (
                    (
                        await session.execute(
                            select(VideoShotTake, VideoAsset)
                            .join(VideoAsset, VideoAsset.id == VideoShotTake.assetId)
                            .where(VideoShotTake.id.in_(take_ids))
                        )
                    ).all()
                    if take_ids
                    else []
                )
                takes = {take.id: (take, asset) for take, asset in take_rows}
                timeline_start = 0
                normalized: list[tuple[EpisodeEditClipInput, int]] = []
                for clip in request.clips:
                    if clip.takeId is not None:
                        pair = takes.get(clip.takeId)
                        if pair is None:
                            raise ApiError(
                                status_code=404,
                                code="VIDEO_EDIT_TAKE_NOT_FOUND",
                                message="粗剪引用的 Take 不存在",
                            )
                        take, asset = pair
                        if (
                            take.shotId != clip.shotId
                            or take.shotPlanVersionId != context.episode_plan.shotPlanVersionId
                        ):
                            raise ApiError(
                                status_code=422,
                                code="VIDEO_EDIT_TAKE_SCOPE_INVALID",
                                message="Take 必须属于同一正式镜头和镜头方案",
                            )
                        if asset.durationMs is None:
                            raise ApiError(
                                status_code=409,
                                code="VIDEO_EDIT_TAKE_DURATION_REQUIRED",
                                message="该 Take 缺少已知时长，暂不能进入非破坏性裁切",
                            )
                        if clip.sourceInMs is None or clip.sourceOutMs is None:
                            raise ApiError(
                                status_code=422,
                                code="VIDEO_EDIT_TRIM_REQUIRED",
                                message="选择 Take 后必须设置源入点和出点",
                            )
                        if clip.sourceOutMs > asset.durationMs:
                            raise ApiError(
                                status_code=422,
                                code="VIDEO_EDIT_TRIM_OUT_OF_RANGE",
                                message="粗剪出点超过 Take 实际时长",
                            )
                        if clip.outputDurationMs != clip.sourceOutMs - clip.sourceInMs:
                            raise ApiError(
                                status_code=422,
                                code="VIDEO_EDIT_DURATION_MISMATCH",
                                message="真实 Take 的输出时长必须等于源出点减入点",
                            )
                    normalized.append((clip, timeline_start))
                    timeline_start += clip.outputDurationMs

                plan_id = context.episode_plan.shotPlanVersionId
                version_no = int(
                    (
                        await session.scalar(
                            select(
                                func.coalesce(func.max(VideoEpisodeEditVersion.versionNo), 0)
                            ).where(
                                VideoEpisodeEditVersion.episodePlanVersionId
                                == context.episode_plan.id,
                                VideoEpisodeEditVersion.episodeNo == episode_no,
                            )
                        )
                    )
                    or 0
                ) + 1
                content = {
                    "episodePlanVersionId": context.episode_plan.id,
                    "episodeNo": episode_no,
                    "clips": [
                        {**clip.model_dump(mode="json"), "timelineStartMs": start}
                        for clip, start in normalized
                    ],
                }
                now = utc_now()
                version = VideoEpisodeEditVersion(
                    id=generate_id(),
                    adaptationId=context.adaptation.id,
                    projectId=context.project.id,
                    novelId=context.adaptation.novelId,
                    episodePlanVersionId=context.episode_plan.id,
                    shotPlanVersionId=plan_id,
                    episodeNo=episode_no,
                    versionNo=version_no,
                    basedOnVersionId=based_on_version_id,
                    totalDurationMs=timeline_start,
                    clientRequestId=request.clientRequestId,
                    requestHash=request_hash,
                    contentHash=_hash_payload(content),
                    createdByUserId=user_id,
                    createdAt=now,
                )
                session.add(version)
                await session.flush()
                session.add_all(
                    [
                        VideoEpisodeEditClip(
                            editVersionId=version.id,
                            shotPlanVersionId=plan_id,
                            shotId=clip.shotId,
                            takeId=clip.takeId,
                            ordinal=ordinal,
                            sourceInMs=clip.sourceInMs,
                            sourceOutMs=clip.sourceOutMs,
                            timelineStartMs=start,
                            outputDurationMs=clip.outputDurationMs,
                            transitionAfter=clip.transitionAfter,
                            transitionDurationMs=clip.transitionDurationMs,
                        )
                        for ordinal, (clip, start) in enumerate(normalized, start=1)
                    ]
                )
                head.currentVersionId = version.id
                head.revision += 1
                head.updatedAt = now
                await session.flush()
                return await _edit_head_response(
                    session,
                    episode_plan_id=context.episode_plan.id,
                    episode_no=episode_no,
                )

    async def get_edit_version(
        self,
        user_id: str,
        version_id: str,
    ) -> EpisodeEditVersionResponse:
        async with self._session_factory() as session:
            version = await _require_owned_edit_version(session, user_id, version_id)
            return await _edit_version_response(session, version)

    async def save_mix_version(
        self,
        user_id: str,
        adaptation_id: str,
        episode_no: int,
        request: SaveEpisodeMixVersionRequest,
    ) -> EpisodeMixHeadResponse:
        request_hash = _hash_payload(
            {
                "adaptationId": adaptation_id,
                "episodeNo": episode_no,
                **request.model_dump(mode="json"),
            }
        )
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_post_production_request(
                    session,
                    namespace="mix",
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                )
                existing = await session.scalar(
                    select(VideoEpisodeMixVersion).where(
                        VideoEpisodeMixVersion.createdByUserId == user_id,
                        VideoEpisodeMixVersion.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    if existing.requestHash != request_hash:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_MIX_CLIENT_REQUEST_REUSED",
                            message="clientRequestId 已用于不同的声音字幕请求",
                        )
                    return await _mix_head_response(
                        session,
                        episode_plan_id=existing.episodePlanVersionId,
                        episode_no=existing.episodeNo,
                    )

                context = await _require_context(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                episode_shots = _require_episode(context, episode_no)
                episode_shot_ids = {shot.id for shot in episode_shots}
                edit = await session.scalar(
                    select(VideoEpisodeEditVersion).where(
                        VideoEpisodeEditVersion.id == request.editVersionId,
                        VideoEpisodeEditVersion.episodePlanVersionId
                        == context.episode_plan.id,
                        VideoEpisodeEditVersion.episodeNo == episode_no,
                        VideoEpisodeEditVersion.adaptationId == context.adaptation.id,
                    )
                )
                if edit is None:
                    raise ApiError(
                        status_code=404,
                        code="VIDEO_MIX_EDIT_VERSION_NOT_FOUND",
                        message="声音字幕所引用的粗剪版本不存在",
                    )
                head = await _get_or_create_mix_head(session, context, episode_no, lock=True)
                if head.revision != request.expectedRevision:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_MIX_REVISION_CONFLICT",
                        message="声音字幕版本已经变化，请刷新后重新保存",
                    )
                based_on_version_id = head.currentVersionId
                if request.basedOnVersionId is not None:
                    based_on = await session.scalar(
                        select(VideoEpisodeMixVersion).where(
                            VideoEpisodeMixVersion.id == request.basedOnVersionId,
                            VideoEpisodeMixVersion.episodePlanVersionId
                            == context.episode_plan.id,
                            VideoEpisodeMixVersion.episodeNo == episode_no,
                        )
                    )
                    if based_on is None:
                        raise ApiError(
                            status_code=404,
                            code="VIDEO_MIX_BASE_VERSION_NOT_FOUND",
                            message="声音字幕基线版本不存在或不属于当前分集",
                        )
                    based_on_version_id = based_on.id

                asset_ids = {clip.assetId for clip in request.audioClips}
                assets = (
                    {
                        asset.id: asset
                        for asset in (
                            await session.scalars(
                                select(VideoAsset).where(VideoAsset.id.in_(asset_ids))
                            )
                        ).all()
                    }
                    if asset_ids
                    else {}
                )
                for clip in request.audioClips:
                    asset = assets.get(clip.assetId)
                    if (
                        asset is None
                        or asset.projectId != context.project.id
                        or asset.modality != "audio"
                        or asset.duty not in {"voice", "ambience", "sfx", "music"}
                        or asset.rightsStatus != "confirmed"
                        or asset.lockedAt is None
                    ):
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_MIX_AUDIO_ASSET_NOT_READY",
                            message="音轨只能使用本项目已确认并锁定的音频素材",
                        )
                    if asset.durationMs is None or clip.sourceOutMs > asset.durationMs:
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_MIX_AUDIO_RANGE_INVALID",
                            message="音频片段出点超过素材的已知时长",
                        )
                    audio_end = (
                        clip.timelineStartMs + clip.sourceOutMs - clip.sourceInMs
                    )
                    if audio_end > edit.totalDurationMs:
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_MIX_AUDIO_TIMELINE_OVERFLOW",
                            message="音频片段超过粗剪总时长",
                        )
                    if clip.shotId is not None and clip.shotId not in episode_shot_ids:
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_MIX_AUDIO_SHOT_INVALID",
                            message="音频片段引用了其他分集的镜头",
                        )
                for cue in request.subtitleCues:
                    if cue.endMs > edit.totalDurationMs:
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_MIX_SUBTITLE_TIMELINE_OVERFLOW",
                            message="字幕超过粗剪总时长",
                        )
                    if cue.shotId is not None and cue.shotId not in episode_shot_ids:
                        raise ApiError(
                            status_code=422,
                            code="VIDEO_MIX_SUBTITLE_SHOT_INVALID",
                            message="字幕引用了其他分集的镜头",
                        )

                version_no = int(
                    (
                        await session.scalar(
                            select(
                                func.coalesce(func.max(VideoEpisodeMixVersion.versionNo), 0)
                            ).where(
                                VideoEpisodeMixVersion.episodePlanVersionId
                                == context.episode_plan.id,
                                VideoEpisodeMixVersion.episodeNo == episode_no,
                            )
                        )
                    )
                    or 0
                ) + 1
                content = {
                    "episodePlanVersionId": context.episode_plan.id,
                    "episodeNo": episode_no,
                    "editVersionId": edit.id,
                    "audioClips": [
                        clip.model_dump(mode="json") for clip in request.audioClips
                    ],
                    "subtitleCues": [
                        cue.model_dump(mode="json") for cue in request.subtitleCues
                    ],
                }
                now = utc_now()
                version = VideoEpisodeMixVersion(
                    id=generate_id(),
                    adaptationId=context.adaptation.id,
                    projectId=context.project.id,
                    novelId=context.adaptation.novelId,
                    episodePlanVersionId=context.episode_plan.id,
                    shotPlanVersionId=context.episode_plan.shotPlanVersionId,
                    episodeNo=episode_no,
                    editVersionId=edit.id,
                    versionNo=version_no,
                    basedOnVersionId=based_on_version_id,
                    clientRequestId=request.clientRequestId,
                    requestHash=request_hash,
                    contentHash=_hash_payload(content),
                    createdByUserId=user_id,
                    createdAt=now,
                )
                session.add(version)
                await session.flush()
                session.add_all(
                    [
                        VideoEpisodeAudioClip(
                            mixVersionId=version.id,
                            projectId=context.project.id,
                            shotPlanVersionId=context.episode_plan.shotPlanVersionId,
                            ordinal=ordinal,
                            trackKind=clip.trackKind,
                            assetId=clip.assetId,
                            shotId=clip.shotId,
                            timelineStartMs=clip.timelineStartMs,
                            sourceInMs=clip.sourceInMs,
                            sourceOutMs=clip.sourceOutMs,
                            gainMillibels=clip.gainMillibels,
                            fadeInMs=clip.fadeInMs,
                            fadeOutMs=clip.fadeOutMs,
                        )
                        for ordinal, clip in enumerate(request.audioClips, start=1)
                    ]
                    + [
                        VideoEpisodeSubtitleCue(
                            mixVersionId=version.id,
                            shotPlanVersionId=context.episode_plan.shotPlanVersionId,
                            ordinal=ordinal,
                            shotId=cue.shotId,
                            startMs=cue.startMs,
                            endMs=cue.endMs,
                            speaker=cue.speaker,
                            text=cue.text,
                        )
                        for ordinal, cue in enumerate(request.subtitleCues, start=1)
                    ]
                )
                head.currentVersionId = version.id
                head.revision += 1
                head.updatedAt = now
                await session.flush()
                return await _mix_head_response(
                    session,
                    episode_plan_id=context.episode_plan.id,
                    episode_no=episode_no,
                )

    async def get_mix_version(
        self,
        user_id: str,
        version_id: str,
    ) -> EpisodeMixVersionResponse:
        async with self._session_factory() as session:
            version = await _require_owned_mix_version(session, user_id, version_id)
            return await _mix_version_response(session, version)

    async def create_export_task(
        self,
        user_id: str,
        adaptation_id: str,
        episode_no: int,
        request: StartEpisodeExportRequest,
    ) -> EpisodeExportTaskResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_post_production_request(
                    session,
                    namespace="export",
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                )
                existing = await session.scalar(
                    select(VideoEpisodeExportTask).where(
                        VideoEpisodeExportTask.requestedByUserId == user_id,
                        VideoEpisodeExportTask.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    _validate_export_start_replay(existing, adaptation_id, episode_no, request)
                    return await _export_task_response(session, existing)
                context = await _require_context(
                    session,
                    user_id=user_id,
                    adaptation_id=adaptation_id,
                    lock=True,
                )
                _require_episode(context, episode_no)
                active = await session.scalar(
                    select(VideoEpisodeExportTask.id).where(
                        VideoEpisodeExportTask.episodePlanVersionId
                        == context.episode_plan.id,
                        VideoEpisodeExportTask.episodeNo == episode_no,
                        VideoEpisodeExportTask.status.in_({"pending", "rendering"}),
                    )
                )
                if active is not None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_EXPORT_TASK_ACTIVE",
                        message="本集已有导出任务正在执行",
                    )
                manifest = await _build_export_manifest(
                    session,
                    context,
                    episode_no,
                    request.editVersionId,
                    request.mixVersionId,
                    resolution=request.resolution,
                    frames_per_second=request.framesPerSecond,
                    burn_subtitles=request.burnSubtitles,
                )
                now = utc_now()
                task = VideoEpisodeExportTask(
                    id=generate_id(),
                    requestedByUserId=user_id,
                    adaptationId=context.adaptation.id,
                    projectId=context.project.id,
                    novelId=context.adaptation.novelId,
                    episodePlanVersionId=context.episode_plan.id,
                    shotPlanVersionId=context.episode_plan.shotPlanVersionId,
                    episodeNo=episode_no,
                    editVersionId=manifest.editVersionId,
                    mixVersionId=manifest.mixVersionId,
                    retryOfTaskId=None,
                    clientRequestId=request.clientRequestId,
                    status="pending",
                    inputHash=_manifest_hash(manifest),
                    requestManifestJson=manifest.model_dump_json(),
                    resolution=request.resolution,
                    framesPerSecond=request.framesPerSecond,
                    burnSubtitles=request.burnSubtitles,
                    attemptCount=0,
                    nextAttemptAt=now,
                    lastErrorCode=None,
                    lastErrorMessage=None,
                    createdAt=now,
                    updatedAt=now,
                    startedAt=None,
                    completedAt=None,
                )
                session.add(task)
                await session.flush()
                return await _export_task_response(session, task)

    async def retry_export_task(
        self,
        user_id: str,
        task_id: str,
        request: RetryEpisodeExportRequest,
    ) -> EpisodeExportTaskResponse:
        async with self._session_factory() as session:
            async with session.begin():
                await _lock_post_production_request(
                    session,
                    namespace="export",
                    user_id=user_id,
                    client_request_id=request.clientRequestId,
                )
                source = await _require_owned_export_task(session, user_id, task_id, lock=True)
                existing = await session.scalar(
                    select(VideoEpisodeExportTask).where(
                        VideoEpisodeExportTask.requestedByUserId == user_id,
                        VideoEpisodeExportTask.clientRequestId == request.clientRequestId,
                    )
                )
                if existing is not None:
                    if existing.retryOfTaskId != source.id:
                        raise ApiError(
                            status_code=409,
                            code="VIDEO_EXPORT_CLIENT_REQUEST_REUSED",
                            message="clientRequestId 已用于另一条导出任务",
                        )
                    return await _export_task_response(session, existing)
                if source.status not in _EXPORT_RETRYABLE_STATUSES:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_EXPORT_TASK_NOT_RETRYABLE",
                        message="只有失败的整集导出任务可以按原清单重试",
                    )
                context = await _require_context(
                    session,
                    user_id=user_id,
                    adaptation_id=source.adaptationId,
                    lock=True,
                )
                if context.episode_plan.id != source.episodePlanVersionId:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_EXPORT_RETRY_STALE_PLAN",
                        message="原导出不属于当前正式分集方案，不能直接重试",
                    )
                active = await session.scalar(
                    select(VideoEpisodeExportTask.id).where(
                        VideoEpisodeExportTask.episodePlanVersionId
                        == source.episodePlanVersionId,
                        VideoEpisodeExportTask.episodeNo == source.episodeNo,
                        VideoEpisodeExportTask.status.in_({"pending", "rendering"}),
                    )
                )
                if active is not None:
                    raise ApiError(
                        status_code=409,
                        code="VIDEO_EXPORT_TASK_ACTIVE",
                        message="本集已有导出任务正在执行",
                    )
                manifest = _parse_export_manifest(source)
                now = utc_now()
                task = VideoEpisodeExportTask(
                    id=generate_id(),
                    requestedByUserId=user_id,
                    adaptationId=source.adaptationId,
                    projectId=source.projectId,
                    novelId=source.novelId,
                    episodePlanVersionId=source.episodePlanVersionId,
                    shotPlanVersionId=source.shotPlanVersionId,
                    episodeNo=source.episodeNo,
                    editVersionId=source.editVersionId,
                    mixVersionId=source.mixVersionId,
                    retryOfTaskId=source.id,
                    clientRequestId=request.clientRequestId,
                    status="pending",
                    inputHash=_manifest_hash(manifest),
                    requestManifestJson=source.requestManifestJson,
                    resolution=source.resolution,
                    framesPerSecond=source.framesPerSecond,
                    burnSubtitles=source.burnSubtitles,
                    attemptCount=0,
                    nextAttemptAt=now,
                    lastErrorCode=None,
                    lastErrorMessage=None,
                    createdAt=now,
                    updatedAt=now,
                    startedAt=None,
                    completedAt=None,
                )
                session.add(task)
                await session.flush()
                return await _export_task_response(session, task)

    async def get_export_task(
        self,
        user_id: str,
        task_id: str,
    ) -> EpisodeExportTaskResponse:
        async with self._session_factory() as session:
            task = await _require_owned_export_task(session, user_id, task_id, lock=False)
            return await _export_task_response(session, task)

    async def get_export_file(
        self,
        user_id: str,
        export_id: str,
    ) -> VideoAssetFile:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(VideoAsset)
                    .join(VideoEpisodeExport, VideoEpisodeExport.assetId == VideoAsset.id)
                    .join(VideoProject, VideoProject.id == VideoEpisodeExport.projectId)
                    .join(Novel, Novel.id == VideoProject.novelId)
                    .where(VideoEpisodeExport.id == export_id, Novel.userId == user_id)
                )
            ).scalar_one_or_none()
            if row is None:
                raise ApiError(
                    status_code=404,
                    code="VIDEO_EPISODE_EXPORT_NOT_FOUND",
                    message="整集导出不存在",
                )
            return VideoAssetFile(
                storage_key=row.storageKey,
                mime_type=row.mimeType,
                name=row.name,
            )

    async def claim_due_export_tasks(self, limit: int) -> list[EpisodeExportClaim]:
        if limit < 1:
            raise ValueError("整集导出任务领取数量必须为正整数")
        now = utc_now()
        lease_until = now + timedelta(minutes=30)
        async with self._session_factory() as session:
            async with session.begin():
                tasks = list(
                    (
                        await session.scalars(
                            select(VideoEpisodeExportTask)
                            .where(
                                VideoEpisodeExportTask.status.in_({"pending", "rendering"}),
                                VideoEpisodeExportTask.nextAttemptAt <= now,
                            )
                            .order_by(
                                VideoEpisodeExportTask.nextAttemptAt,
                                VideoEpisodeExportTask.createdAt,
                            )
                            .limit(limit)
                            .with_for_update(skip_locked=True)
                        )
                    ).all()
                )
                claims: list[EpisodeExportClaim] = []
                for task in tasks:
                    task.status = "rendering"
                    task.attemptCount += 1
                    task.nextAttemptAt = lease_until
                    task.startedAt = task.startedAt or now
                    task.updatedAt = now
                    claims.append(
                        EpisodeExportClaim(
                            task_id=task.id,
                            project_id=task.projectId,
                            manifest=_parse_export_manifest(task),
                        )
                    )
                return claims

    async def complete_export(
        self,
        task_id: str,
        *,
        asset_id: str,
        stored: StoredVideoAsset,
        duration_ms: int,
    ) -> EpisodeExportTaskResponse:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoEpisodeExportTask, task_id, with_for_update=True)
                if task is None:
                    raise RuntimeError("整集导出任务不存在")
                existing = await session.scalar(
                    select(VideoEpisodeExport).where(VideoEpisodeExport.taskId == task.id)
                )
                if existing is not None:
                    return await _export_task_response(session, task)
                if task.status != "rendering":
                    raise RuntimeError("整集导出任务不在渲染阶段")
                next_version_no = int(
                    (
                        await session.scalar(
                            select(func.coalesce(func.max(VideoEpisodeExport.versionNo), 0)).where(
                                VideoEpisodeExport.episodePlanVersionId
                                == task.episodePlanVersionId,
                                VideoEpisodeExport.episodeNo == task.episodeNo,
                            )
                        )
                    )
                    or 0
                ) + 1
                now = utc_now()
                asset = VideoAsset(
                    id=asset_id,
                    projectId=task.projectId,
                    name=f"第 {task.episodeNo} 集 · 成片 v{next_version_no}",
                    modality="video",
                    duty="episode_export",
                    mimeType=stored.mime_type,
                    byteSize=stored.byte_size,
                    durationMs=duration_ms,
                    sha256=stored.sha256,
                    sourceKind="model_generated",
                    rightsStatus="confirmed",
                    lockedAt=now,
                    storageKey=stored.storage_key,
                    createdAt=now,
                    updatedAt=now,
                )
                exported = VideoEpisodeExport(
                    id=generate_id(),
                    taskId=task.id,
                    adaptationId=task.adaptationId,
                    projectId=task.projectId,
                    episodePlanVersionId=task.episodePlanVersionId,
                    episodeNo=task.episodeNo,
                    editVersionId=task.editVersionId,
                    mixVersionId=task.mixVersionId,
                    assetId=asset.id,
                    versionNo=next_version_no,
                    inputHash=task.inputHash,
                    createdAt=now,
                )
                session.add_all([asset, exported])
                task.status = "succeeded"
                task.lastErrorCode = None
                task.lastErrorMessage = None
                task.nextAttemptAt = now
                task.updatedAt = now
                task.completedAt = now
                await session.flush()
                return await _export_task_response(session, task)

    async def fail_export(self, task_id: str, code: str, message: str) -> bool:
        async with self._session_factory() as session:
            async with session.begin():
                task = await session.get(VideoEpisodeExportTask, task_id, with_for_update=True)
                if task is None or task.status != "rendering":
                    return False
                now = utc_now()
                task.status = "failed"
                task.lastErrorCode = code
                task.lastErrorMessage = message
                task.nextAttemptAt = now
                task.updatedAt = now
                task.completedAt = now
                return True


async def _lock_post_production_request(
    session: AsyncSession,
    *,
    namespace: str,
    user_id: str,
    client_request_id: str,
) -> None:
    """串行化同类幂等键，消除并发请求都在唯一记录创建前查空的窗口。"""

    digest = hashlib.sha256(
        f"video-post-production\0{namespace}\0{user_id}\0{client_request_id}".encode()
    ).digest()
    lock_key = int.from_bytes(digest[:8], byteorder="big", signed=True)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": lock_key},
    )


async def _require_context(
    session: AsyncSession,
    *,
    user_id: str,
    adaptation_id: str,
    lock: bool,
) -> OwnedPostProductionContext:
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
    adaptation, project, head = row
    if head.currentShotPlanVersionId is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_POST_PRODUCTION_FORMAL_PLAN_REQUIRED",
            message="请先确认正式镜头方案",
        )
    if head.currentEpisodePlanVersionId is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_POST_PRODUCTION_EPISODE_PLAN_REQUIRED",
            message="请先保存正式分集方案",
        )
    episode_plan = await session.get(VideoEpisodePlanVersion, head.currentEpisodePlanVersionId)
    if (
        episode_plan is None
        or episode_plan.adaptationId != adaptation.id
        or episode_plan.shotPlanVersionId != head.currentShotPlanVersionId
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_POST_PRODUCTION_PLAN_INVALID",
            message="当前正式镜头与分集版本指针不一致",
        )
    shots = list(
        (
            await session.scalars(
                select(VideoShot)
                .where(VideoShot.planVersionId == head.currentShotPlanVersionId)
                .order_by(VideoShot.ordinal)
            )
        ).all()
    )
    if not shots:
        raise ApiError(
            status_code=409,
            code="VIDEO_POST_PRODUCTION_SHOTS_REQUIRED",
            message="当前正式方案没有可制作镜头",
        )
    boundaries = list(
        (
            await session.scalars(
                select(VideoEpisodeBoundary)
                .where(VideoEpisodeBoundary.episodePlanVersionId == episode_plan.id)
                .order_by(VideoEpisodeBoundary.ordinal)
            )
        ).all()
    )
    break_ids = {boundary.afterShotId for boundary in boundaries}
    shot_ids = {shot.id for shot in shots}
    if not break_ids.issubset(shot_ids):
        raise ApiError(
            status_code=409,
            code="VIDEO_POST_PRODUCTION_EPISODE_PLAN_INVALID",
            message="当前分集版本引用了其他镜头方案",
        )
    episodes: list[list[VideoShot]] = []
    current: list[VideoShot] = []
    for shot in shots:
        current.append(shot)
        if shot.id in break_ids:
            episodes.append(current)
            current = []
    if current:
        episodes.append(current)
    if not episodes or any(not episode for episode in episodes):
        raise ApiError(
            status_code=409,
            code="VIDEO_POST_PRODUCTION_EPISODE_PLAN_INVALID",
            message="当前分集版本无法形成有效分集",
        )
    return OwnedPostProductionContext(
        adaptation=adaptation,
        project=project,
        head=head,
        episode_plan=episode_plan,
        shots=shots,
        episodes=episodes,
    )


def _require_episode(
    context: OwnedPostProductionContext,
    episode_no: int,
) -> list[VideoShot]:
    if episode_no < 1 or episode_no > len(context.episodes):
        raise ApiError(
            status_code=404,
            code="VIDEO_EPISODE_NOT_FOUND",
            message="正式分集不存在",
        )
    return context.episodes[episode_no - 1]


async def _load_keyframe_workspace(
    session: AsyncSession,
    context: OwnedPostProductionContext,
) -> list[ShotPostProductionResponse]:
    shot_ids = [shot.id for shot in context.shots]
    heads = list(
        (
            await session.scalars(
                select(VideoShotKeyframeHead).where(
                    VideoShotKeyframeHead.shotId.in_(shot_ids)
                )
            )
        ).all()
    )
    versions = list(
        (
            await session.scalars(
                select(VideoShotKeyframeVersion)
                .where(VideoShotKeyframeVersion.shotId.in_(shot_ids))
                .order_by(
                    VideoShotKeyframeVersion.shotId,
                    VideoShotKeyframeVersion.role,
                    VideoShotKeyframeVersion.versionNo.desc(),
                )
            )
        ).all()
    )
    asset_ids = {version.assetId for version in versions if version.assetId is not None}
    assets = {
        asset.id: asset
        for asset in (
            await session.scalars(select(VideoAsset).where(VideoAsset.id.in_(asset_ids)))
        ).all()
    }
    heads_by_key = {(head.shotId, head.role): head for head in heads}
    versions_by_key: dict[tuple[str, str], list[VideoShotKeyframeVersion]] = {}
    for version in versions:
        versions_by_key.setdefault((version.shotId, version.role), []).append(version)

    return [
        ShotPostProductionResponse(
            shotId=shot.id,
            shotKey=shot.shotKey,
            title=shot.title,
            heads=[
                _keyframe_head_from_loaded(
                    shot_id=shot.id,
                    role=role,
                    head=heads_by_key.get((shot.id, role)),
                    versions=versions_by_key.get((shot.id, role), []),
                    assets=assets,
                )
                for role in _KEYFRAME_ROLES
            ],
        )
        for shot in context.shots
    ]


async def _keyframe_head_response(
    session: AsyncSession,
    *,
    shot_id: str,
    role: str,
) -> ShotKeyframeHeadResponse:
    head = await session.scalar(
        select(VideoShotKeyframeHead).where(
            VideoShotKeyframeHead.shotId == shot_id,
            VideoShotKeyframeHead.role == role,
        )
    )
    versions = list(
        (
            await session.scalars(
                select(VideoShotKeyframeVersion)
                .where(
                    VideoShotKeyframeVersion.shotId == shot_id,
                    VideoShotKeyframeVersion.role == role,
                )
                .order_by(VideoShotKeyframeVersion.versionNo.desc())
            )
        ).all()
    )
    asset_ids = {version.assetId for version in versions if version.assetId is not None}
    assets = {
        asset.id: asset
        for asset in (
            await session.scalars(select(VideoAsset).where(VideoAsset.id.in_(asset_ids)))
        ).all()
    }
    return _keyframe_head_from_loaded(
        shot_id=shot_id,
        role=role,
        head=head,
        versions=versions,
        assets=assets,
    )


def _keyframe_head_from_loaded(
    *,
    shot_id: str,
    role: str,
    head: VideoShotKeyframeHead | None,
    versions: list[VideoShotKeyframeVersion],
    assets: dict[str, VideoAsset],
) -> ShotKeyframeHeadResponse:
    by_id = {version.id: version for version in versions}
    current = by_id.get(head.currentVersionId) if head and head.currentVersionId else None
    if head is not None and head.currentVersionId is not None and current is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_KEYFRAME_HEAD_INVALID",
            message="当前关键帧版本指针无效",
        )
    response_versions = [
        _keyframe_version_response(
            version,
            assets.get(version.assetId) if version.assetId is not None else None,
        )
        for version in versions
    ]
    current_response = next(
        (version for version in response_versions if current and version.id == current.id),
        None,
    )
    return ShotKeyframeHeadResponse(
        shotId=shot_id,
        role=cast(Literal["initial_state", "transition_anchor", "end_state"], role),
        revision=head.revision if head is not None else 1,
        currentVersion=current_response,
        history=response_versions,
    )


def _keyframe_version_response(
    version: VideoShotKeyframeVersion,
    asset: VideoAsset | None,
) -> ShotKeyframeVersionResponse:
    return ShotKeyframeVersionResponse(
        id=version.id,
        shotId=version.shotId,
        shotPlanVersionId=version.shotPlanVersionId,
        role=cast(
            Literal["initial_state", "transition_anchor", "end_state"],
            version.role,
        ),
        versionNo=version.versionNo,
        basedOnVersionId=version.basedOnVersionId,
        asset=_asset_response(asset) if asset is not None else None,
        sourceKind=cast(Literal["asset", "take_frame", "cleared"], version.sourceKind),
        sourceTakeId=version.sourceTakeId,
        sourceTimeMs=version.sourceTimeMs,
        contentHash=version.contentHash,
        createdAt=version.createdAt,
    )


async def _load_continuity_issues(
    session: AsyncSession,
    context: OwnedPostProductionContext,
    shot_workspaces: list[ShotPostProductionResponse],
) -> list[ContinuityIssueResponse]:
    issues: list[ContinuityIssueResponse] = []
    by_shot = {item.shotId: item for item in shot_workspaces}
    active_asset_ids = {
        version.asset.id
        for workspace in shot_workspaces
        for head in workspace.heads
        if (version := head.currentVersion) is not None and version.asset is not None
    }
    # 设定关键帧时素材一定已确认并锁定，但素材权利状态可能随后被管理员撤销。
    # 工作台每次读取都重新核对数据库事实，不能把历史响应里的图片信息当成仍可用于生成。
    current_assets = {
        asset.id: asset
        for asset in (
            await session.scalars(select(VideoAsset).where(VideoAsset.id.in_(active_asset_ids)))
        ).all()
    }
    for shot in context.shots:
        workspace = by_shot[shot.id]
        active_assets: dict[str, PostProductionAssetResponse] = {}
        for head in workspace.heads:
            version = head.currentVersion
            if version is None or version.asset is None:
                continue
            active_assets[head.role] = version.asset
            if version.asset.modality != "image":
                issues.append(
                    ContinuityIssueResponse(
                        code="VIDEO_CONTINUITY_KEYFRAME_MODALITY_INVALID",
                        severity="blocking",
                        message="已确认关键帧不再是图片素材",
                        shotIds=[shot.id],
                        duty="keyframe",
                    )
                )
            current_asset = current_assets.get(version.asset.id)
            if (
                current_asset is None
                or current_asset.rightsStatus != "confirmed"
                or current_asset.lockedAt is None
            ):
                issues.append(
                    ContinuityIssueResponse(
                        code="VIDEO_CONTINUITY_KEYFRAME_RIGHTS_INVALID",
                        severity="blocking",
                        message="已确认关键帧的素材授权或锁定状态已失效，请重新选择素材",
                        shotIds=[shot.id],
                        duty="keyframe",
                    )
                )
        initial = active_assets.get("initial_state")
        ending = active_assets.get("end_state")
        if initial is not None and ending is not None and initial.sha256 == ending.sha256:
            issues.append(
                ContinuityIssueResponse(
                    code="VIDEO_CONTINUITY_IDENTICAL_ENDPOINTS",
                    severity="warning",
                    message="首帧与尾帧使用同一图片，请确认镜头是否确实没有状态变化",
                    shotIds=[shot.id],
                    duty="keyframe",
                )
            )
        high_risk = shot.narrativePurpose == "action" or any(
            marker in (shot.storyFunction or "") for marker in ("动作", "冲突", "揭示", "转折")
        )
        if high_risk and not active_assets:
            issues.append(
                ContinuityIssueResponse(
                    code="VIDEO_CONTINUITY_HIGH_RISK_WITHOUT_KEYFRAME",
                    severity="info",
                    message="动作或转折镜头尚未设置关键帧，可先生成候选，也可继续纯提示词生成",
                    shotIds=[shot.id],
                    duty="keyframe",
                )
            )

    prompt_rows = (
        await session.execute(
            select(
                VideoShotPromptHead.shotId,
                VideoVisualCanonVersion.canonId,
                VideoVisualCanonVersion.assetId,
                VideoVisualCanon.duty,
                VideoAsset.modality,
                VideoAsset.rightsStatus,
                VideoAsset.lockedAt,
            )
            .join(
                VideoShotPromptVisualReference,
                VideoShotPromptVisualReference.promptVersionId
                == VideoShotPromptHead.currentVersionId,
            )
            .join(
                VideoVisualCanonVersion,
                VideoVisualCanonVersion.id
                == VideoShotPromptVisualReference.canonVersionId,
            )
            .join(VideoVisualCanon, VideoVisualCanon.id == VideoVisualCanonVersion.canonId)
            .outerjoin(VideoAsset, VideoAsset.id == VideoVisualCanonVersion.assetId)
            .where(VideoShotPromptHead.shotId.in_([shot.id for shot in context.shots]))
        )
    ).all()
    references: dict[str, dict[str, tuple[str, str]]] = {}
    for (
        shot_id,
        canon_id,
        asset_id,
        duty,
        modality,
        rights_status,
        locked_at,
    ) in prompt_rows:
        references.setdefault(shot_id, {})[canon_id] = (asset_id, duty)
        if modality != "image" or rights_status != "confirmed" or locked_at is None:
            issues.append(
                ContinuityIssueResponse(
                    code="VIDEO_CONTINUITY_PROMPT_REFERENCE_NOT_READY",
                    severity="blocking",
                    message="正式提示词冻结的视觉参考已丢失、授权失效或不再是图片",
                    shotIds=[shot_id],
                    duty=duty,
                )
            )
    for left, right in zip(context.shots, context.shots[1:], strict=False):
        left_refs = references.get(left.id, {})
        right_refs = references.get(right.id, {})
        for canon_id in sorted(left_refs.keys() & right_refs.keys()):
            left_asset, duty = left_refs[canon_id]
            right_asset, _ = right_refs[canon_id]
            if left_asset != right_asset:
                issues.append(
                    ContinuityIssueResponse(
                        code="VIDEO_CONTINUITY_ADJACENT_CANON_VERSION_CHANGED",
                        severity="warning",
                        message="相邻镜头的同一视觉设定采用了不同素材版本，请确认这是有意变化",
                        shotIds=[left.id, right.id],
                        duty=duty,
                    )
                )
    return issues


async def _load_episode_workspace(
    session: AsyncSession,
    context: OwnedPostProductionContext,
    episode_no: int,
    episode_shots: list[VideoShot],
) -> EpisodePostProductionResponse:
    shot_ids = [shot.id for shot in episode_shots]
    take_rows = (
        await session.execute(
            select(VideoShotTake, VideoAsset)
            .join(VideoAsset, VideoAsset.id == VideoShotTake.assetId)
            .where(VideoShotTake.shotId.in_(shot_ids))
            .order_by(VideoShotTake.shotId, VideoShotTake.takeNo)
        )
    ).all()
    takes_by_shot: dict[str, list[PostProductionTakeResponse]] = {
        shot_id: [] for shot_id in shot_ids
    }
    take_assets: dict[str, VideoAsset] = {}
    for take, asset in take_rows:
        take_assets[take.id] = asset
        takes_by_shot[take.shotId].append(_take_response(take, asset))
    take_heads = {
        head.shotId: head.currentTakeId
        for head in (
            await session.scalars(
                select(VideoShotTakeHead).where(VideoShotTakeHead.shotId.in_(shot_ids))
            )
        ).all()
    }
    shot_responses = [
        EpisodeShotResponse(
            shotId=shot.id,
            shotKey=shot.shotKey,
            ordinal=shot.ordinal,
            title=shot.title,
            timelineDurationMs=shot.timelineDurationMs,
            speechMode=_speech_mode(shot),
            spokenText=shot.spokenText,
            takes=takes_by_shot[shot.id],
            confirmedTakeId=take_heads.get(shot.id),
        )
        for shot in episode_shots
    ]
    default_clips: list[EpisodeEditClipResponse] = []
    timeline_start = 0
    for ordinal, shot in enumerate(episode_shots, start=1):
        take_id = take_heads.get(shot.id)
        asset = take_assets.get(take_id) if take_id is not None else None
        if asset is not None and asset.durationMs is not None and asset.durationMs >= 500:
            duration = min(shot.timelineDurationMs, asset.durationMs)
            source_in: int | None = 0
            source_out: int | None = duration
        else:
            take_id = None
            duration = shot.timelineDurationMs
            source_in = None
            source_out = None
        default_clips.append(
            EpisodeEditClipResponse(
                shotId=shot.id,
                takeId=take_id,
                sourceInMs=source_in,
                sourceOutMs=source_out,
                outputDurationMs=duration,
                transitionAfter="cut",
                transitionDurationMs=0,
                ordinal=ordinal,
                timelineStartMs=timeline_start,
            )
        )
        timeline_start += duration

    edit_head = await _edit_head_response(
        session,
        episode_plan_id=context.episode_plan.id,
        episode_no=episode_no,
    )
    edit_history_rows = list(
        (
            await session.scalars(
                select(VideoEpisodeEditVersion)
                .where(
                    VideoEpisodeEditVersion.episodePlanVersionId == context.episode_plan.id,
                    VideoEpisodeEditVersion.episodeNo == episode_no,
                )
                .order_by(VideoEpisodeEditVersion.versionNo.desc())
            )
        ).all()
    )
    mix_head = await _mix_head_response(
        session,
        episode_plan_id=context.episode_plan.id,
        episode_no=episode_no,
        current_edit_id=(
            edit_head.currentVersion.id if edit_head.currentVersion is not None else None
        ),
    )
    mix_history_rows = list(
        (
            await session.scalars(
                select(VideoEpisodeMixVersion)
                .where(
                    VideoEpisodeMixVersion.episodePlanVersionId == context.episode_plan.id,
                    VideoEpisodeMixVersion.episodeNo == episode_no,
                )
                .order_by(VideoEpisodeMixVersion.versionNo.desc())
            )
        ).all()
    )
    export_task_rows = list(
        (
            await session.scalars(
                select(VideoEpisodeExportTask)
                .where(
                    VideoEpisodeExportTask.episodePlanVersionId == context.episode_plan.id,
                    VideoEpisodeExportTask.episodeNo == episode_no,
                )
                .order_by(VideoEpisodeExportTask.createdAt.desc())
            )
        ).all()
    )
    subtitle_base = edit_head.currentVersion.clips if edit_head.currentVersion else default_clips
    suggested_subtitles = _subtitle_suggestions(episode_shots, subtitle_base)
    return EpisodePostProductionResponse(
        episodeNo=episode_no,
        shots=shot_responses,
        defaultClips=default_clips,
        suggestedSubtitleCues=suggested_subtitles,
        editHead=edit_head,
        editHistory=[_edit_summary(version) for version in edit_history_rows],
        mixHead=mix_head,
        mixHistory=[_mix_summary(version) for version in mix_history_rows],
        exportTasks=[
            await _export_task_response(session, task) for task in export_task_rows
        ],
    )


def _subtitle_suggestions(
    shots: list[VideoShot],
    clips: list[EpisodeEditClipResponse],
) -> list[EpisodeSubtitleCueInput]:
    shot_map = {shot.id: shot for shot in shots}
    suggestions: list[EpisodeSubtitleCueInput] = []
    for clip in clips:
        shot = shot_map[clip.shotId]
        if _speech_mode(shot) == "none" or not shot.spokenText:
            continue
        duration = min(
            clip.outputDurationMs,
            max(800, len(shot.spokenText) * 180),
        )
        suggestions.append(
            EpisodeSubtitleCueInput(
                shotId=shot.id,
                startMs=clip.timelineStartMs,
                endMs=clip.timelineStartMs + duration,
                speaker=None,
                text=shot.spokenText,
            )
        )
    return suggestions


async def _get_or_create_edit_head(
    session: AsyncSession,
    context: OwnedPostProductionContext,
    episode_no: int,
    *,
    lock: bool,
) -> VideoEpisodeEditHead:
    query = select(VideoEpisodeEditHead).where(
        VideoEpisodeEditHead.episodePlanVersionId == context.episode_plan.id,
        VideoEpisodeEditHead.episodeNo == episode_no,
    )
    if lock:
        query = query.with_for_update()
    head = await session.scalar(query)
    if head is None:
        head = VideoEpisodeEditHead(
            episodePlanVersionId=context.episode_plan.id,
            shotPlanVersionId=context.episode_plan.shotPlanVersionId,
            adaptationId=context.adaptation.id,
            episodeNo=episode_no,
            currentVersionId=None,
            revision=1,
            updatedAt=utc_now(),
        )
        session.add(head)
        await session.flush()
    return head


async def _edit_head_response(
    session: AsyncSession,
    *,
    episode_plan_id: str,
    episode_no: int,
) -> EpisodeEditHeadResponse:
    head = await session.scalar(
        select(VideoEpisodeEditHead).where(
            VideoEpisodeEditHead.episodePlanVersionId == episode_plan_id,
            VideoEpisodeEditHead.episodeNo == episode_no,
        )
    )
    if head is None or head.currentVersionId is None:
        return EpisodeEditHeadResponse(
            episodePlanVersionId=episode_plan_id,
            episodeNo=episode_no,
            revision=head.revision if head is not None else 1,
            currentVersion=None,
        )
    version = await session.get(VideoEpisodeEditVersion, head.currentVersionId)
    if version is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_EDIT_HEAD_INVALID",
            message="当前粗剪版本指针无效",
        )
    return EpisodeEditHeadResponse(
        episodePlanVersionId=episode_plan_id,
        episodeNo=episode_no,
        revision=head.revision,
        currentVersion=await _edit_version_response(session, version),
    )


async def _edit_version_response(
    session: AsyncSession,
    version: VideoEpisodeEditVersion,
) -> EpisodeEditVersionResponse:
    clips = list(
        (
            await session.scalars(
                select(VideoEpisodeEditClip)
                .where(VideoEpisodeEditClip.editVersionId == version.id)
                .order_by(VideoEpisodeEditClip.ordinal)
            )
        ).all()
    )
    return EpisodeEditVersionResponse(
        **_edit_summary(version).model_dump(),
        adaptationId=version.adaptationId,
        episodePlanVersionId=version.episodePlanVersionId,
        shotPlanVersionId=version.shotPlanVersionId,
        clips=[
            EpisodeEditClipResponse(
                shotId=clip.shotId,
                takeId=clip.takeId,
                sourceInMs=clip.sourceInMs,
                sourceOutMs=clip.sourceOutMs,
                outputDurationMs=clip.outputDurationMs,
                transitionAfter=cast(Literal["cut", "fade_black"], clip.transitionAfter),
                transitionDurationMs=clip.transitionDurationMs,
                ordinal=clip.ordinal,
                timelineStartMs=clip.timelineStartMs,
            )
            for clip in clips
        ],
    )


def _edit_summary(version: VideoEpisodeEditVersion) -> EpisodeEditVersionSummaryResponse:
    return EpisodeEditVersionSummaryResponse(
        id=version.id,
        episodeNo=version.episodeNo,
        versionNo=version.versionNo,
        basedOnVersionId=version.basedOnVersionId,
        totalDurationMs=version.totalDurationMs,
        contentHash=version.contentHash,
        createdAt=version.createdAt,
    )


async def _get_or_create_mix_head(
    session: AsyncSession,
    context: OwnedPostProductionContext,
    episode_no: int,
    *,
    lock: bool,
) -> VideoEpisodeMixHead:
    query = select(VideoEpisodeMixHead).where(
        VideoEpisodeMixHead.episodePlanVersionId == context.episode_plan.id,
        VideoEpisodeMixHead.episodeNo == episode_no,
    )
    if lock:
        query = query.with_for_update()
    head = await session.scalar(query)
    if head is None:
        head = VideoEpisodeMixHead(
            episodePlanVersionId=context.episode_plan.id,
            shotPlanVersionId=context.episode_plan.shotPlanVersionId,
            adaptationId=context.adaptation.id,
            episodeNo=episode_no,
            currentVersionId=None,
            revision=1,
            updatedAt=utc_now(),
        )
        session.add(head)
        await session.flush()
    return head


async def _mix_head_response(
    session: AsyncSession,
    *,
    episode_plan_id: str,
    episode_no: int,
    current_edit_id: str | None = None,
) -> EpisodeMixHeadResponse:
    head = await session.scalar(
        select(VideoEpisodeMixHead).where(
            VideoEpisodeMixHead.episodePlanVersionId == episode_plan_id,
            VideoEpisodeMixHead.episodeNo == episode_no,
        )
    )
    if current_edit_id is None:
        edit_head = await session.scalar(
            select(VideoEpisodeEditHead).where(
                VideoEpisodeEditHead.episodePlanVersionId == episode_plan_id,
                VideoEpisodeEditHead.episodeNo == episode_no,
            )
        )
        current_edit_id = edit_head.currentVersionId if edit_head is not None else None
    if head is None or head.currentVersionId is None:
        return EpisodeMixHeadResponse(
            episodePlanVersionId=episode_plan_id,
            episodeNo=episode_no,
            revision=head.revision if head is not None else 1,
            staleAgainstCurrentEdit=False,
            currentVersion=None,
        )
    version = await session.get(VideoEpisodeMixVersion, head.currentVersionId)
    if version is None:
        raise ApiError(
            status_code=409,
            code="VIDEO_MIX_HEAD_INVALID",
            message="当前声音字幕版本指针无效",
        )
    return EpisodeMixHeadResponse(
        episodePlanVersionId=episode_plan_id,
        episodeNo=episode_no,
        revision=head.revision,
        staleAgainstCurrentEdit=(
            current_edit_id is not None and version.editVersionId != current_edit_id
        ),
        currentVersion=await _mix_version_response(session, version),
    )


async def _mix_version_response(
    session: AsyncSession,
    version: VideoEpisodeMixVersion,
) -> EpisodeMixVersionResponse:
    audio_rows = (
        await session.execute(
            select(VideoEpisodeAudioClip, VideoAsset)
            .join(VideoAsset, VideoAsset.id == VideoEpisodeAudioClip.assetId)
            .where(VideoEpisodeAudioClip.mixVersionId == version.id)
            .order_by(VideoEpisodeAudioClip.ordinal)
        )
    ).all()
    subtitle_rows = list(
        (
            await session.scalars(
                select(VideoEpisodeSubtitleCue)
                .where(VideoEpisodeSubtitleCue.mixVersionId == version.id)
                .order_by(VideoEpisodeSubtitleCue.ordinal)
            )
        ).all()
    )
    return EpisodeMixVersionResponse(
        **_mix_summary(version).model_dump(),
        adaptationId=version.adaptationId,
        episodePlanVersionId=version.episodePlanVersionId,
        shotPlanVersionId=version.shotPlanVersionId,
        audioClips=[
            EpisodeAudioClipResponse(
                trackKind=cast(
                    Literal["dialogue", "narration", "ambience", "sfx", "music"],
                    clip.trackKind,
                ),
                assetId=clip.assetId,
                shotId=clip.shotId,
                timelineStartMs=clip.timelineStartMs,
                sourceInMs=clip.sourceInMs,
                sourceOutMs=clip.sourceOutMs,
                gainMillibels=clip.gainMillibels,
                fadeInMs=clip.fadeInMs,
                fadeOutMs=clip.fadeOutMs,
                ordinal=clip.ordinal,
                asset=_asset_response(asset),
            )
            for clip, asset in audio_rows
        ],
        subtitleCues=[
            EpisodeSubtitleCueResponse(
                shotId=cue.shotId,
                startMs=cue.startMs,
                endMs=cue.endMs,
                speaker=cue.speaker,
                text=cue.text,
                ordinal=cue.ordinal,
            )
            for cue in subtitle_rows
        ],
    )


def _mix_summary(version: VideoEpisodeMixVersion) -> EpisodeMixVersionSummaryResponse:
    return EpisodeMixVersionSummaryResponse(
        id=version.id,
        episodeNo=version.episodeNo,
        versionNo=version.versionNo,
        basedOnVersionId=version.basedOnVersionId,
        editVersionId=version.editVersionId,
        contentHash=version.contentHash,
        createdAt=version.createdAt,
    )


async def _require_owned_edit_version(
    session: AsyncSession,
    user_id: str,
    version_id: str,
) -> VideoEpisodeEditVersion:
    version = await session.scalar(
        select(VideoEpisodeEditVersion)
        .join(VideoProject, VideoProject.id == VideoEpisodeEditVersion.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(VideoEpisodeEditVersion.id == version_id, Novel.userId == user_id)
    )
    if version is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_EDIT_VERSION_NOT_FOUND",
            message="粗剪版本不存在",
        )
    return version


async def _require_owned_mix_version(
    session: AsyncSession,
    user_id: str,
    version_id: str,
) -> VideoEpisodeMixVersion:
    version = await session.scalar(
        select(VideoEpisodeMixVersion)
        .join(VideoProject, VideoProject.id == VideoEpisodeMixVersion.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(VideoEpisodeMixVersion.id == version_id, Novel.userId == user_id)
    )
    if version is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_MIX_VERSION_NOT_FOUND",
            message="声音字幕版本不存在",
        )
    return version


async def _build_export_manifest(
    session: AsyncSession,
    context: OwnedPostProductionContext,
    episode_no: int,
    edit_version_id: str,
    mix_version_id: str,
    *,
    resolution: Literal["720p", "1080p"],
    frames_per_second: Literal[24, 25, 30],
    burn_subtitles: bool,
) -> VideoEpisodeExportManifest:
    edit = await session.scalar(
        select(VideoEpisodeEditVersion).where(
            VideoEpisodeEditVersion.id == edit_version_id,
            VideoEpisodeEditVersion.episodePlanVersionId == context.episode_plan.id,
            VideoEpisodeEditVersion.episodeNo == episode_no,
        )
    )
    mix = await session.scalar(
        select(VideoEpisodeMixVersion).where(
            VideoEpisodeMixVersion.id == mix_version_id,
            VideoEpisodeMixVersion.episodePlanVersionId == context.episode_plan.id,
            VideoEpisodeMixVersion.episodeNo == episode_no,
        )
    )
    if edit is None or mix is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_EXPORT_VERSION_NOT_FOUND",
            message="导出引用的粗剪或声音字幕版本不存在",
        )
    if mix.editVersionId != edit.id:
        raise ApiError(
            status_code=409,
            code="VIDEO_EXPORT_MIX_STALE",
            message="声音字幕版本不是基于所选粗剪，请先重新保存声音版本",
        )
    ratio = context.project.targetAspectRatio
    if ratio == "adaptive":
        raise ApiError(
            status_code=409,
            code="VIDEO_EXPORT_FIXED_RATIO_REQUIRED",
            message="整集导出需要项目使用固定画幅，不能使用 adaptive",
        )
    allowed_ratios = {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9"}
    if ratio not in allowed_ratios:
        raise ApiError(
            status_code=409,
            code="VIDEO_EXPORT_RATIO_INVALID",
            message="项目画幅无法用于整集导出",
        )
    edit_clips = list(
        (
            await session.scalars(
                select(VideoEpisodeEditClip)
                .where(VideoEpisodeEditClip.editVersionId == edit.id)
                .order_by(VideoEpisodeEditClip.ordinal)
            )
        ).all()
    )
    if not edit_clips or any(clip.takeId is None for clip in edit_clips):
        raise ApiError(
            status_code=409,
            code="VIDEO_EXPORT_PLACEHOLDER_REMAINING",
            message="粗剪仍有未确认 Take 的占位镜头，不能导出正式成片",
        )
    take_ids = [cast(str, clip.takeId) for clip in edit_clips]
    take_rows = (
        await session.execute(
            select(VideoShotTake, VideoAsset)
            .join(VideoAsset, VideoAsset.id == VideoShotTake.assetId)
            .where(VideoShotTake.id.in_(take_ids))
        )
    ).all()
    take_map = {take.id: (take, asset) for take, asset in take_rows}
    frozen_video: list[FrozenExportVideoClip] = []
    for clip in edit_clips:
        pair = take_map.get(cast(str, clip.takeId))
        if pair is None:
            raise ApiError(
                status_code=409,
                code="VIDEO_EXPORT_TAKE_MISSING",
                message="粗剪引用的 Take 或受控视频素材已丢失",
            )
        take, asset = pair
        _require_locked_asset(asset, modality="video")
        frozen_video.append(
            FrozenExportVideoClip(
                ordinal=clip.ordinal,
                shotId=clip.shotId,
                takeId=take.id,
                asset=_frozen_asset(asset),
                sourceInMs=clip.sourceInMs,
                sourceOutMs=clip.sourceOutMs,
                outputDurationMs=clip.outputDurationMs,
                transitionAfter=cast(Literal["cut", "fade_black"], clip.transitionAfter),
                transitionDurationMs=clip.transitionDurationMs,
            )
        )
    audio_rows = (
        await session.execute(
            select(VideoEpisodeAudioClip, VideoAsset)
            .join(VideoAsset, VideoAsset.id == VideoEpisodeAudioClip.assetId)
            .where(VideoEpisodeAudioClip.mixVersionId == mix.id)
            .order_by(VideoEpisodeAudioClip.ordinal)
        )
    ).all()
    frozen_audio: list[FrozenExportAudioClip] = []
    for clip, asset in audio_rows:
        _require_locked_asset(asset, modality="audio")
        frozen_audio.append(
            FrozenExportAudioClip(
                ordinal=clip.ordinal,
                trackKind=cast(
                    Literal["dialogue", "narration", "ambience", "sfx", "music"],
                    clip.trackKind,
                ),
                shotId=clip.shotId,
                asset=_frozen_asset(asset),
                timelineStartMs=clip.timelineStartMs,
                sourceInMs=clip.sourceInMs,
                sourceOutMs=clip.sourceOutMs,
                gainMillibels=clip.gainMillibels,
                fadeInMs=clip.fadeInMs,
                fadeOutMs=clip.fadeOutMs,
            )
        )
    subtitle_rows = list(
        (
            await session.scalars(
                select(VideoEpisodeSubtitleCue)
                .where(VideoEpisodeSubtitleCue.mixVersionId == mix.id)
                .order_by(VideoEpisodeSubtitleCue.ordinal)
            )
        ).all()
    )
    return VideoEpisodeExportManifest(
        adaptationId=context.adaptation.id,
        projectId=context.project.id,
        novelId=context.adaptation.novelId,
        episodePlanVersionId=context.episode_plan.id,
        shotPlanVersionId=context.episode_plan.shotPlanVersionId,
        episodeNo=episode_no,
        editVersionId=edit.id,
        editContentHash=edit.contentHash,
        mixVersionId=mix.id,
        mixContentHash=mix.contentHash,
        targetAspectRatio=cast(
            Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"], ratio
        ),
        resolution=resolution,
        framesPerSecond=frames_per_second,
        burnSubtitles=burn_subtitles,
        totalDurationMs=edit.totalDurationMs,
        videoClips=frozen_video,
        audioClips=frozen_audio,
        subtitleCues=[
            FrozenExportSubtitleCue(
                ordinal=cue.ordinal,
                shotId=cue.shotId,
                startMs=cue.startMs,
                endMs=cue.endMs,
                speaker=cue.speaker,
                text=cue.text,
            )
            for cue in subtitle_rows
        ],
    )


def _require_locked_asset(asset: VideoAsset, *, modality: str) -> None:
    if (
        asset.modality != modality
        or asset.rightsStatus != "confirmed"
        or asset.lockedAt is None
    ):
        raise ApiError(
            status_code=409,
            code="VIDEO_EXPORT_ASSET_NOT_READY",
            message="导出引用的素材不再处于已确认锁定状态",
        )


def _frozen_asset(asset: VideoAsset) -> FrozenExportAsset:
    return FrozenExportAsset(
        assetId=asset.id,
        storageKey=asset.storageKey,
        sha256=asset.sha256,
        mimeType=asset.mimeType,
        durationMs=asset.durationMs,
    )


async def _require_owned_export_task(
    session: AsyncSession,
    user_id: str,
    task_id: str,
    *,
    lock: bool,
) -> VideoEpisodeExportTask:
    query = (
        select(VideoEpisodeExportTask)
        .join(VideoProject, VideoProject.id == VideoEpisodeExportTask.projectId)
        .join(Novel, Novel.id == VideoProject.novelId)
        .where(VideoEpisodeExportTask.id == task_id, Novel.userId == user_id)
    )
    if lock:
        query = query.with_for_update(of=VideoEpisodeExportTask)
    task = await session.scalar(query)
    if task is None:
        raise ApiError(
            status_code=404,
            code="VIDEO_EXPORT_TASK_NOT_FOUND",
            message="整集导出任务不存在",
        )
    return task


async def _export_task_response(
    session: AsyncSession,
    task: VideoEpisodeExportTask,
) -> EpisodeExportTaskResponse:
    exported = await session.scalar(
        select(VideoEpisodeExport).where(VideoEpisodeExport.taskId == task.id)
    )
    export_response: EpisodeExportResponse | None = None
    if exported is not None:
        asset = await session.get(VideoAsset, exported.assetId)
        if asset is None:
            raise ApiError(
                status_code=409,
                code="VIDEO_EPISODE_EXPORT_ASSET_MISSING",
                message="整集导出的受控素材已丢失",
            )
        asset_response = _asset_response(asset).model_copy(
            update={"contentUrl": f"/api/v1/video/exports/{exported.id}/content"}
        )
        export_response = EpisodeExportResponse(
            id=exported.id,
            episodeNo=exported.episodeNo,
            versionNo=exported.versionNo,
            editVersionId=exported.editVersionId,
            mixVersionId=exported.mixVersionId,
            inputHash=exported.inputHash,
            createdAt=exported.createdAt,
            asset=asset_response,
        )
    return EpisodeExportTaskResponse(
        id=task.id,
        adaptationId=task.adaptationId,
        episodeNo=task.episodeNo,
        editVersionId=task.editVersionId,
        mixVersionId=task.mixVersionId,
        retryOfTaskId=task.retryOfTaskId,
        status=cast(ExportTaskStatus, task.status),
        clientRequestId=task.clientRequestId,
        inputHash=task.inputHash,
        resolution=cast(Literal["720p", "1080p"], task.resolution),
        framesPerSecond=cast(Literal[24, 25, 30], task.framesPerSecond),
        burnSubtitles=task.burnSubtitles,
        attemptCount=task.attemptCount,
        lastErrorCode=task.lastErrorCode,
        lastErrorMessage=task.lastErrorMessage,
        createdAt=task.createdAt,
        updatedAt=task.updatedAt,
        startedAt=task.startedAt,
        completedAt=task.completedAt,
        export=export_response,
    )


def _validate_export_start_replay(
    task: VideoEpisodeExportTask,
    adaptation_id: str,
    episode_no: int,
    request: StartEpisodeExportRequest,
) -> None:
    expected = (
        task.adaptationId,
        task.episodeNo,
        task.editVersionId,
        task.mixVersionId,
        task.resolution,
        task.framesPerSecond,
        task.burnSubtitles,
    )
    actual = (
        adaptation_id,
        episode_no,
        request.editVersionId,
        request.mixVersionId,
        request.resolution,
        request.framesPerSecond,
        request.burnSubtitles,
    )
    if expected != actual:
        raise ApiError(
            status_code=409,
            code="VIDEO_EXPORT_CLIENT_REQUEST_REUSED",
            message="clientRequestId 已用于不同的导出请求",
        )


def _parse_export_manifest(task: VideoEpisodeExportTask) -> VideoEpisodeExportManifest:
    try:
        manifest = VideoEpisodeExportManifest.model_validate_json(task.requestManifestJson)
    except ValidationError as exc:
        raise RuntimeError("整集导出任务清单无效") from exc
    if _manifest_hash(manifest) != task.inputHash:
        raise RuntimeError("整集导出任务清单哈希不一致")
    return manifest


def _manifest_hash(manifest: VideoEpisodeExportManifest) -> str:
    return hashlib.sha256(
        manifest.model_dump_json().encode("utf-8")
    ).hexdigest()


def _hash_payload(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _asset_response(asset: VideoAsset) -> PostProductionAssetResponse:
    return PostProductionAssetResponse(
        id=asset.id,
        name=asset.name,
        modality=cast(Literal["image", "video", "audio"], asset.modality),
        duty=asset.duty,
        mimeType=asset.mimeType,
        durationMs=asset.durationMs,
        sha256=asset.sha256,
        contentUrl=f"/api/v1/video/assets/{asset.id}/content",
    )


def _take_response(take: VideoShotTake, asset: VideoAsset) -> PostProductionTakeResponse:
    return PostProductionTakeResponse(
        id=take.id,
        shotId=take.shotId,
        takeNo=take.takeNo,
        durationMs=asset.durationMs,
        createdAt=take.createdAt,
        asset=_asset_response(asset).model_copy(
            update={"contentUrl": f"/api/v1/video/takes/{take.id}/content"}
        ),
    )


def _speech_mode(
    shot: VideoShot,
) -> Literal["none", "sync", "offscreen", "voiceover"]:
    if shot.speechMode in {"none", "sync", "offscreen", "voiceover"}:
        return cast(Literal["none", "sync", "offscreen", "voiceover"], shot.speechMode)
    legacy = {
        "sync_dialogue": "sync",
        "offscreen_dialogue": "offscreen",
        "voiceover": "voiceover",
    }.get(shot.audioMode, "none")
    return cast(Literal["none", "sync", "offscreen", "voiceover"], legacy)

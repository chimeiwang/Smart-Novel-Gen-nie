"""章节影视化 P1–P3 公共用例。"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from weakref import WeakValueDictionary

from ...errors import ApiError
from ..storage import VideoAssetStorage
from .post_production_media import MediaProcessingError, VideoPostProductionMediaProcessor
from .post_production_repository import VideoPostProductionRepository
from .post_production_schemas import (
    ChapterPostProductionWorkspaceResponse,
    EpisodeEditHeadResponse,
    EpisodeEditVersionResponse,
    EpisodeExportTaskResponse,
    EpisodeMixHeadResponse,
    EpisodeMixVersionResponse,
    ExtractTakeFrameRequest,
    PostProductionAssetResponse,
    PostProductionReadinessResponse,
    RetryEpisodeExportRequest,
    SaveEpisodeEditVersionRequest,
    SaveEpisodeMixVersionRequest,
    SaveShotKeyframeVersionRequest,
    ShotKeyframeHeadResponse,
    StartEpisodeExportRequest,
)


class VideoPostProductionService:
    def __init__(
        self,
        repository: VideoPostProductionRepository,
        storage: VideoAssetStorage,
        media: VideoPostProductionMediaProcessor,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._media = media
        # Core 按部署约束只有一个 worker；弱引用锁只串行化同一抽帧幂等键且不会无限积累。
        self._frame_extraction_locks: WeakValueDictionary[str, asyncio.Lock] = (
            WeakValueDictionary()
        )

    @property
    def readiness(self) -> PostProductionReadinessResponse:
        media = self._media.readiness
        blockers: list[str] = []
        if not media.ffmpeg_available:
            blockers.append("当前环境缺少 ffmpeg，不能抽帧或导出")
        if not media.ffprobe_available:
            blockers.append("当前环境缺少 ffprobe，不能检查 Take 音轨")
        return PostProductionReadinessResponse(
            ffmpegAvailable=media.ffmpeg_available,
            ffprobeAvailable=media.ffprobe_available,
            blockers=blockers,
        )

    async def get_workspace(
        self,
        user_id: str,
        adaptation_id: str,
    ) -> ChapterPostProductionWorkspaceResponse:
        return await self._repository.get_workspace(
            user_id,
            adaptation_id,
            self.readiness,
        )

    async def save_keyframe(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        request: SaveShotKeyframeVersionRequest,
    ) -> ShotKeyframeHeadResponse:
        return await self._repository.save_keyframe(
            user_id,
            adaptation_id,
            shot_id,
            request,
        )

    async def extract_take_frame(
        self,
        user_id: str,
        take_id: str,
        request: ExtractTakeFrameRequest,
    ) -> PostProductionAssetResponse:
        self._require_media_ready()
        request_hash = hashlib.sha256(
            "\x00".join(
                (
                    user_id,
                    take_id,
                    request.clientRequestId,
                    str(request.timestampMs),
                    request.name.strip(),
                )
            ).encode("utf-8")
        ).hexdigest()
        lock = self._frame_extraction_locks.get(request_hash)
        if lock is None:
            lock = asyncio.Lock()
            self._frame_extraction_locks[request_hash] = lock
        async with lock:
            return await self._extract_take_frame_locked(
                user_id=user_id,
                take_id=take_id,
                request=request,
                request_hash=request_hash,
            )

    async def _extract_take_frame_locked(
        self,
        *,
        user_id: str,
        take_id: str,
        request: ExtractTakeFrameRequest,
        request_hash: str,
    ) -> PostProductionAssetResponse:
        asset_id = f"frame_{request_hash[:40]}"
        existing = await self._repository.get_extraction_replay(
            user_id,
            request.clientRequestId,
            request_hash,
        )
        if existing is not None:
            return existing
        source = await self._repository.get_take_frame_source(
            user_id,
            take_id,
            request.timestampMs,
        )
        stale_storage_key = f"{source.project_id}/{asset_id}.png"
        self._storage.delete(stale_storage_key)
        try:
            stored = await self._media.extract_frame(
                source_path=self._storage.resolve(source.storage_key),
                expected_sha256=source.sha256,
                timestamp_ms=request.timestampMs,
                storage=self._storage,
                project_id=source.project_id,
                asset_id=asset_id,
            )
        except MediaProcessingError as exc:
            raise _media_api_error(exc) from exc
        try:
            return await self._repository.complete_extracted_frame(
                user_id=user_id,
                source=source,
                asset_id=asset_id,
                name=request.name.strip(),
                timestamp_ms=request.timestampMs,
                client_request_id=request.clientRequestId,
                request_hash=request_hash,
                stored=stored,
            )
        except Exception:
            # 数据库提交可能成功但响应丢失。新事务能重放到来源事实时必须保留文件；
            # 只有确认没有持久化结果时才执行补偿删除。
            replay = await self._repository.get_extraction_replay(
                user_id,
                request.clientRequestId,
                request_hash,
            )
            if replay is not None:
                return replay
            self._storage.delete(stored.storage_key)
            raise

    async def save_edit_version(
        self,
        user_id: str,
        adaptation_id: str,
        episode_no: int,
        request: SaveEpisodeEditVersionRequest,
    ) -> EpisodeEditHeadResponse:
        return await self._repository.save_edit_version(
            user_id,
            adaptation_id,
            episode_no,
            request,
        )

    async def get_edit_version(
        self,
        user_id: str,
        version_id: str,
    ) -> EpisodeEditVersionResponse:
        return await self._repository.get_edit_version(user_id, version_id)

    async def save_mix_version(
        self,
        user_id: str,
        adaptation_id: str,
        episode_no: int,
        request: SaveEpisodeMixVersionRequest,
    ) -> EpisodeMixHeadResponse:
        return await self._repository.save_mix_version(
            user_id,
            adaptation_id,
            episode_no,
            request,
        )

    async def get_mix_version(
        self,
        user_id: str,
        version_id: str,
    ) -> EpisodeMixVersionResponse:
        return await self._repository.get_mix_version(user_id, version_id)

    async def create_export_task(
        self,
        user_id: str,
        adaptation_id: str,
        episode_no: int,
        request: StartEpisodeExportRequest,
    ) -> EpisodeExportTaskResponse:
        self._require_media_ready()
        return await self._repository.create_export_task(
            user_id,
            adaptation_id,
            episode_no,
            request,
        )

    async def retry_export_task(
        self,
        user_id: str,
        task_id: str,
        request: RetryEpisodeExportRequest,
    ) -> EpisodeExportTaskResponse:
        self._require_media_ready()
        return await self._repository.retry_export_task(user_id, task_id, request)

    async def get_export_task(
        self,
        user_id: str,
        task_id: str,
    ) -> EpisodeExportTaskResponse:
        return await self._repository.get_export_task(user_id, task_id)

    async def get_export_file(
        self,
        user_id: str,
        export_id: str,
    ) -> tuple[Path, str, str]:
        asset = await self._repository.get_export_file(user_id, export_id)
        return self._storage.resolve(asset.storage_key), asset.mime_type, asset.name

    def _require_media_ready(self) -> None:
        if not self._media.readiness.ready:
            raise ApiError(
                status_code=503,
                code="VIDEO_MEDIA_TOOLS_UNAVAILABLE",
                message="当前环境缺少 ffmpeg 或 ffprobe，不能执行抽帧或整集导出",
            )


def _media_api_error(error: MediaProcessingError) -> ApiError:
    status_code = 503 if error.code == "VIDEO_MEDIA_TOOLS_UNAVAILABLE" else 422
    return ApiError(
        status_code=status_code,
        code=error.code,
        message=error.message,
    )

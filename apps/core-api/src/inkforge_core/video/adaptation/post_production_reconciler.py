"""整集导出耐久任务协调器。"""

from __future__ import annotations

import asyncio
import logging

from ...operations.transient_errors import is_transient_infrastructure_error
from ..storage import VideoAssetStorage
from .post_production_media import MediaProcessingError, VideoPostProductionMediaProcessor
from .post_production_repository import EpisodeExportClaim, VideoPostProductionRepository

logger = logging.getLogger(__name__)


class VideoPostProductionReconciler:
    def __init__(
        self,
        repository: VideoPostProductionRepository,
        media: VideoPostProductionMediaProcessor,
        storage: VideoAssetStorage,
        *,
        batch_size: int = 1,
        interval_seconds: float = 3.0,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("整集导出协调器配置无效")
        self._repository = repository
        self._media = media
        self._storage = storage
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        claims = await self._repository.claim_due_export_tasks(self._batch_size)
        # 单机 2 核默认只并发一个 FFmpeg，避免与模型 worker 争抢内存和 CPU。
        for claim in claims:
            await self._process(claim)
        return len(claims)

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                if not is_transient_infrastructure_error(exc):
                    raise
                logger.warning(
                    "整集导出后台协调暂时失败",
                    extra={"errorCode": type(exc).__name__},
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                pass

    async def _process(self, claim: EpisodeExportClaim) -> None:
        asset_id = f"export_{claim.task_id}"
        stale_storage_key = f"{claim.project_id}/{asset_id}.mp4"
        self._storage.delete(stale_storage_key)
        try:
            stored = await self._media.render_episode(
                manifest=claim.manifest,
                storage=self._storage,
                asset_id=asset_id,
            )
        except MediaProcessingError as exc:
            logger.warning(
                "整集媒体导出失败",
                extra={"taskId": claim.task_id, "errorCode": exc.code, "detail": exc.message},
            )
            await self._repository.fail_export(
                claim.task_id,
                exc.code,
                _public_media_error(exc),
            )
            return
        except Exception:
            logger.exception("整集导出发生未预期错误", extra={"taskId": claim.task_id})
            await self._repository.fail_export(
                claim.task_id,
                "VIDEO_EPISODE_EXPORT_INTERNAL_ERROR",
                "整集导出发生内部错误，请重试同一冻结输入",
            )
            return

        try:
            await self._repository.complete_export(
                claim.task_id,
                asset_id=asset_id,
                stored=stored,
                duration_ms=claim.manifest.totalDurationMs,
            )
        except Exception:
            logger.exception("整集成片登记发生未预期错误", extra={"taskId": claim.task_id})
            # complete_export 可能已经提交，只是响应丢失。只有任务仍为 rendering 并被本次
            # 对账原子改成 failed 时，才允许删除文件；succeeded 必须保留已登记的成片。
            transitioned_to_failed = await self._repository.fail_export(
                claim.task_id,
                "VIDEO_EPISODE_EXPORT_INTERNAL_ERROR",
                "整集成片登记发生内部错误，请重试同一冻结输入",
            )
            if transitioned_to_failed:
                self._storage.delete(stored.storage_key)


def _public_media_error(error: MediaProcessingError) -> str:
    safe_messages = {
        "VIDEO_MEDIA_TOOLS_UNAVAILABLE": "当前环境缺少媒体处理工具",
        "VIDEO_EXPORT_ASSET_MISSING": "导出引用的受控素材文件不存在",
        "VIDEO_EXPORT_ASSET_HASH_MISMATCH": "导出引用的素材哈希已经变化",
        "VIDEO_KEYFRAME_SOURCE_HASH_MISMATCH": "来源 Take 文件与冻结哈希不一致",
        "VIDEO_EXPORT_PLACEHOLDER_REMAINING": "粗剪仍包含占位镜头",
        "VIDEO_EXPORT_PROBE_FAILED": "无法读取某个 Take 的音轨信息",
    }
    return safe_messages.get(error.code, "FFmpeg 无法处理当前素材编码或时间范围")

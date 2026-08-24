"""逐镜视频生成公共用例与供应商素材传输服务。"""

from __future__ import annotations

from pathlib import Path

from ...errors import ApiError
from ..storage import VideoAssetStorage
from .render_repository import VideoShotRenderRepository
from .render_security import ProviderAssetTokenCodec
from .schemas import (
    ChapterRenderWorkspaceResponse,
    ConfirmShotTakeRequest,
    RetryShotRenderRequest,
    ShotRenderTaskResponse,
    ShotTakeDecisionResponse,
    StartShotRenderRequest,
    VideoRenderReadinessResponse,
)


class VideoShotRenderService:
    def __init__(
        self,
        repository: VideoShotRenderRepository,
        storage: VideoAssetStorage,
        *,
        configured: bool,
        enabled: bool,
        model: str,
        provider_media_base_url: str | None,
        provider_asset_token_codec: ProviderAssetTokenCodec | None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._configured = configured
        self._enabled = enabled
        self._model = model
        self._provider_media_base_url = provider_media_base_url
        self._provider_asset_token_codec = provider_asset_token_codec

    @property
    def readiness(self) -> VideoRenderReadinessResponse:
        transport_configured = (
            self._provider_media_base_url is not None
            and self._provider_asset_token_codec is not None
        )
        blockers: list[str] = []
        if not self._configured:
            blockers.append("Seedance 尚未配置")
        if not self._enabled:
            blockers.append("Seedance 真实调用尚未启用")
        if not transport_configured:
            blockers.append("视觉参考图公网短时传输尚未配置；无参考图镜头不受影响")
        return VideoRenderReadinessResponse(
            configured=self._configured,
            enabled=self._enabled,
            referenceTransportConfigured=transport_configured,
            model=self._model,
            blockers=blockers,
        )

    async def create_task(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        request: StartShotRenderRequest,
    ) -> ShotRenderTaskResponse:
        self._require_enabled()
        return await self._repository.create_task(
            user_id,
            adaptation_id,
            shot_id,
            request,
            model=self._model,
            reference_transport_configured=self.readiness.referenceTransportConfigured,
        )

    async def retry_task(
        self,
        user_id: str,
        task_id: str,
        request: RetryShotRenderRequest,
    ) -> ShotRenderTaskResponse:
        self._require_enabled()
        return await self._repository.retry_task(
            user_id,
            task_id,
            request,
            reference_transport_configured=self.readiness.referenceTransportConfigured,
        )

    async def get_task(self, user_id: str, task_id: str) -> ShotRenderTaskResponse:
        return await self._repository.get_task(user_id, task_id)

    async def get_workspace(
        self,
        user_id: str,
        adaptation_id: str,
    ) -> ChapterRenderWorkspaceResponse:
        return await self._repository.get_workspace(
            user_id,
            adaptation_id,
            self.readiness,
        )

    async def confirm_take(
        self,
        user_id: str,
        adaptation_id: str,
        shot_id: str,
        take_id: str,
        request: ConfirmShotTakeRequest,
    ) -> ShotTakeDecisionResponse:
        decision = await self._repository.confirm_take(
            user_id,
            adaptation_id,
            shot_id,
            take_id,
            request,
        )
        if decision.status != "succeeded":
            raise ApiError(
                status_code=409,
                code=decision.errorCode or "VIDEO_TAKE_CONFIRM_REJECTED",
                message="当前采用的 Take 已经变化，请刷新后重新确认",
                details=decision.model_dump(mode="json"),
            )
        return decision

    async def get_take_file(self, user_id: str, take_id: str) -> tuple[Path, str, str]:
        asset = await self._repository.get_take_file(user_id, take_id)
        return self._storage.resolve(asset.storage_key), asset.mime_type, asset.name

    async def get_provider_asset_file(self, token: str) -> tuple[Path, str]:
        codec = self._provider_asset_token_codec
        if codec is None:
            raise ApiError(
                status_code=404,
                code="VIDEO_PROVIDER_ASSET_TRANSPORT_DISABLED",
                message="供应商素材传输未启用",
            )
        grant = codec.decode(token)
        asset = await self._repository.get_provider_asset_file(
            grant.asset_id,
            grant.sha256,
        )
        return self._storage.resolve(asset.storage_key), asset.mime_type

    def _require_enabled(self) -> None:
        if not self._configured:
            raise ApiError(
                status_code=503,
                code="SEEDANCE_NOT_CONFIGURED",
                message="当前环境尚未配置 Seedance",
            )
        if not self._enabled:
            raise ApiError(
                status_code=503,
                code="SEEDANCE_DISABLED",
                message="当前环境尚未启用 Seedance 真实视频生成",
            )

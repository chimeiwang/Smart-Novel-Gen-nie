"""供应商按短时令牌读取新 Episode 链共享参考素材。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import VideoAsset
from ..errors import ApiError
from .adaptation.render_security import ProviderAssetTokenCodec
from .storage import VideoAssetStorage


class VideoProviderAssetService:
    """只查询已确认图片资产，不实例化旧 Render/Take 仓储。"""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: VideoAssetStorage,
        token_codec: ProviderAssetTokenCodec,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._token_codec = token_codec

    async def get_file(self, token: str) -> tuple[Path, str]:
        grant = self._token_codec.decode(token)
        async with self._session_factory() as session:
            asset = await session.scalar(
                select(VideoAsset).where(
                    VideoAsset.id == grant.asset_id,
                    VideoAsset.sha256 == grant.sha256,
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
        return self._storage.resolve(asset.storageKey), asset.mimeType

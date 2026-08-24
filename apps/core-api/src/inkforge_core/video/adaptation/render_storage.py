"""把供应商临时视频 URL 流式归档到 InkForge 受控素材存储。"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..storage import StoredVideoAsset, VideoAssetStorage
from .render_security import require_allowed_seedance_result_url


@dataclass(frozen=True, slots=True)
class ArchivedRenderResult:
    asset_id: str
    stored: StoredVideoAsset


class SeedanceResultArchiver:
    def __init__(
        self,
        storage: VideoAssetStorage,
        *,
        allowed_host_suffixes: tuple[str, ...],
    ) -> None:
        self._storage = storage
        self._allowed_host_suffixes = allowed_host_suffixes

    async def archive(
        self,
        *,
        project_id: str,
        asset_id: str,
        video_url: str,
    ) -> ArchivedRenderResult:
        safe_url = require_allowed_seedance_result_url(
            video_url,
            self._allowed_host_suffixes,
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120, connect=5),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
        ) as client:
            async with client.stream("GET", safe_url) as response:
                if 300 <= response.status_code < 400:
                    raise RuntimeError("SEEDANCE_RESULT_REDIRECT_FORBIDDEN")
                response.raise_for_status()
                stored = await self._storage.save_stream(
                    project_id,
                    asset_id,
                    "video",
                    response.aiter_bytes(),
                )
        return ArchivedRenderResult(asset_id=asset_id, stored=stored)

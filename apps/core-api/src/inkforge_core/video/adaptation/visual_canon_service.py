"""新 Episode 链共享的视觉设定应用服务。"""

from __future__ import annotations

from ...errors import ApiError
from .schemas import (
    ApproveVisualCanonRequest,
    CreateVisualCanonCandidateRequest,
    VisualCanonLibraryResponse,
    VisualCanonResponse,
)
from .visual_canon import VideoVisualCanonRepository


class VideoVisualCanonService:
    """只暴露项目级定妆版本，不依赖旧 ChapterAdaptation 仓储。"""

    def __init__(
        self,
        repository: VideoVisualCanonRepository,
        *,
        video_preview_enabled: bool,
    ) -> None:
        self._repository = repository
        self._video_preview_enabled = video_preview_enabled

    async def list_canons(
        self,
        user_id: str,
        project_id: str,
    ) -> VisualCanonLibraryResponse:
        return await self._repository.list_canons(user_id, project_id)

    async def set_candidate(
        self,
        user_id: str,
        project_id: str,
        request: CreateVisualCanonCandidateRequest,
    ) -> VisualCanonResponse:
        self._require_enabled()
        return await self._repository.set_candidate(user_id, project_id, request)

    async def approve(
        self,
        user_id: str,
        canon_id: str,
        request: ApproveVisualCanonRequest,
    ) -> VisualCanonResponse:
        self._require_enabled()
        return await self._repository.approve(user_id, canon_id, request)

    def _require_enabled(self) -> None:
        if not self._video_preview_enabled:
            raise ApiError(
                status_code=503,
                code="VIDEO_PREVIEW_DISABLED",
                message="当前环境未开启视频开发预览写入",
            )

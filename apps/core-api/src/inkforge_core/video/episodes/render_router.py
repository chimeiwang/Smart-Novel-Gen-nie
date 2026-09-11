"""独立剧集逐镜任务公共路由；Python 只提供 Java Core 的 OpenAPI 权威。"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .render_schemas import (
    RetryVideoEpisodeShotRenderRequest,
    StartVideoEpisodeShotRenderRequest,
    VideoEpisodeRenderTaskResponse,
)

router = APIRouter(prefix="/video", tags=["VideoEpisodeRenders"])
User = Annotated[AuthUser, Depends(get_current_user)]


def _java_runtime_only() -> NoReturn:
    raise ApiError(
        status_code=503,
        code="JAVA_CORE_REQUIRED",
        message="独立剧集逐镜生成由 Java Core 提供服务",
    )


@router.post(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/shots/{shot_id}/render-tasks",
    response_model=VideoEpisodeRenderTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_video_episode_shot_render(
    episode_id: str,
    baseline_id: str,
    shot_id: str,
    body: StartVideoEpisodeShotRenderRequest,
    user: User,
) -> VideoEpisodeRenderTaskResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/render-tasks/{task_id}",
    response_model=VideoEpisodeRenderTaskResponse,
)
async def get_video_episode_render_task(
    episode_id: str,
    task_id: str,
    user: User,
) -> VideoEpisodeRenderTaskResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/render-tasks/{task_id}/retry",
    response_model=VideoEpisodeRenderTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_video_episode_render_task(
    episode_id: str,
    task_id: str,
    body: RetryVideoEpisodeShotRenderRequest,
    user: User,
) -> VideoEpisodeRenderTaskResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/takes/{take_id}/content",
    response_class=FileResponse,
)
async def get_video_episode_take_content(
    episode_id: str,
    take_id: str,
    user: User,
) -> FileResponse:
    _java_runtime_only()

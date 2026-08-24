"""章节影视化 P1–P3 后期制作公共路由。"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .post_production_schemas import (
    ChapterPostProductionWorkspaceResponse,
    EpisodeEditHeadResponse,
    EpisodeEditVersionResponse,
    EpisodeExportTaskResponse,
    EpisodeMixHeadResponse,
    EpisodeMixVersionResponse,
    ExtractTakeFrameRequest,
    PostProductionAssetResponse,
    RetryEpisodeExportRequest,
    SaveEpisodeEditVersionRequest,
    SaveEpisodeMixVersionRequest,
    SaveShotKeyframeVersionRequest,
    ShotKeyframeHeadResponse,
    StartEpisodeExportRequest,
)
from .post_production_service import VideoPostProductionService

router = APIRouter(prefix="/video", tags=["视频后期制作"])


def get_video_post_production_service(request: Request) -> VideoPostProductionService:
    service = cast(
        VideoPostProductionService | None,
        getattr(request.app.state, "video_post_production_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="VIDEO_POST_PRODUCTION_UNAVAILABLE",
            message="视频后期制作服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[VideoPostProductionService, Depends(get_video_post_production_service)]


@router.get(
    "/chapter-adaptations/{adaptation_id}/post-production",
    response_model=ChapterPostProductionWorkspaceResponse,
)
async def get_post_production_workspace(
    adaptation_id: str,
    user: User,
    service: Service,
) -> ChapterPostProductionWorkspaceResponse:
    return await service.get_workspace(user.id, adaptation_id)


@router.post(
    "/chapter-adaptations/{adaptation_id}/shots/{shot_id}/keyframe-versions",
    response_model=ShotKeyframeHeadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_shot_keyframe_version(
    adaptation_id: str,
    shot_id: str,
    body: SaveShotKeyframeVersionRequest,
    user: User,
    service: Service,
) -> ShotKeyframeHeadResponse:
    return await service.save_keyframe(user.id, adaptation_id, shot_id, body)


@router.post(
    "/takes/{take_id}/frames",
    response_model=PostProductionAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def extract_take_frame(
    take_id: str,
    body: ExtractTakeFrameRequest,
    user: User,
    service: Service,
) -> PostProductionAssetResponse:
    return await service.extract_take_frame(user.id, take_id, body)


@router.post(
    "/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/edit-versions",
    response_model=EpisodeEditHeadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_episode_edit_version(
    adaptation_id: str,
    episode_no: int,
    body: SaveEpisodeEditVersionRequest,
    user: User,
    service: Service,
) -> EpisodeEditHeadResponse:
    return await service.save_edit_version(user.id, adaptation_id, episode_no, body)


@router.get(
    "/edit-versions/{version_id}",
    response_model=EpisodeEditVersionResponse,
)
async def get_episode_edit_version(
    version_id: str,
    user: User,
    service: Service,
) -> EpisodeEditVersionResponse:
    return await service.get_edit_version(user.id, version_id)


@router.post(
    "/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/mix-versions",
    response_model=EpisodeMixHeadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_episode_mix_version(
    adaptation_id: str,
    episode_no: int,
    body: SaveEpisodeMixVersionRequest,
    user: User,
    service: Service,
) -> EpisodeMixHeadResponse:
    return await service.save_mix_version(user.id, adaptation_id, episode_no, body)


@router.get(
    "/mix-versions/{version_id}",
    response_model=EpisodeMixVersionResponse,
)
async def get_episode_mix_version(
    version_id: str,
    user: User,
    service: Service,
) -> EpisodeMixVersionResponse:
    return await service.get_mix_version(user.id, version_id)


@router.post(
    "/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/export-tasks",
    response_model=EpisodeExportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_episode_export_task(
    adaptation_id: str,
    episode_no: int,
    body: StartEpisodeExportRequest,
    user: User,
    service: Service,
) -> EpisodeExportTaskResponse:
    return await service.create_export_task(user.id, adaptation_id, episode_no, body)


@router.get(
    "/export-tasks/{task_id}",
    response_model=EpisodeExportTaskResponse,
)
async def get_episode_export_task(
    task_id: str,
    user: User,
    service: Service,
) -> EpisodeExportTaskResponse:
    return await service.get_export_task(user.id, task_id)


@router.post(
    "/export-tasks/{task_id}/retry",
    response_model=EpisodeExportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_episode_export_task(
    task_id: str,
    body: RetryEpisodeExportRequest,
    user: User,
    service: Service,
) -> EpisodeExportTaskResponse:
    return await service.retry_export_task(user.id, task_id, body)


@router.get("/exports/{export_id}/content", response_class=FileResponse)
async def get_episode_export_content(
    export_id: str,
    user: User,
    service: Service,
) -> FileResponse:
    path, mime_type, filename = await service.get_export_file(user.id, export_id)
    return FileResponse(
        path,
        media_type=mime_type,
        filename=filename,
        content_disposition_type="inline",
    )

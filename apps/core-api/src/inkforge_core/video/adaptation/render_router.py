"""逐镜视频任务、候选 Take 与选片确认公共接口。"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .render_service import VideoShotRenderService
from .schemas import (
    ChapterRenderWorkspaceResponse,
    ConfirmShotTakeRequest,
    RetryShotRenderRequest,
    ShotRenderTaskResponse,
    ShotTakeDecisionResponse,
    StartShotRenderRequest,
)

router = APIRouter(prefix="/video", tags=["逐镜视频生成"])


def get_video_shot_render_service(request: Request) -> VideoShotRenderService:
    service = cast(
        VideoShotRenderService | None,
        getattr(request.app.state, "video_shot_render_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="VIDEO_RENDER_SERVICE_UNAVAILABLE",
            message="逐镜视频生成服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[VideoShotRenderService, Depends(get_video_shot_render_service)]


@router.get(
    "/chapter-adaptations/{adaptation_id}/renders",
    response_model=ChapterRenderWorkspaceResponse,
)
async def get_render_workspace(
    adaptation_id: str,
    user: User,
    service: Service,
) -> ChapterRenderWorkspaceResponse:
    return await service.get_workspace(user.id, adaptation_id)


@router.post(
    "/chapter-adaptations/{adaptation_id}/shots/{shot_id}/render-tasks",
    response_model=ShotRenderTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_render_task(
    adaptation_id: str,
    shot_id: str,
    body: StartShotRenderRequest,
    user: User,
    service: Service,
) -> ShotRenderTaskResponse:
    return await service.create_task(user.id, adaptation_id, shot_id, body)


@router.get(
    "/render-tasks/{task_id}",
    response_model=ShotRenderTaskResponse,
)
async def get_render_task(
    task_id: str,
    user: User,
    service: Service,
) -> ShotRenderTaskResponse:
    return await service.get_task(user.id, task_id)


@router.post(
    "/render-tasks/{task_id}/retry",
    response_model=ShotRenderTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_render_task(
    task_id: str,
    body: RetryShotRenderRequest,
    user: User,
    service: Service,
) -> ShotRenderTaskResponse:
    return await service.retry_task(user.id, task_id, body)


@router.post(
    "/chapter-adaptations/{adaptation_id}/shots/{shot_id}/takes/{take_id}/confirm",
    response_model=ShotTakeDecisionResponse,
)
async def confirm_shot_take(
    adaptation_id: str,
    shot_id: str,
    take_id: str,
    body: ConfirmShotTakeRequest,
    user: User,
    service: Service,
) -> ShotTakeDecisionResponse:
    return await service.confirm_take(
        user.id,
        adaptation_id,
        shot_id,
        take_id,
        body,
    )


@router.get("/takes/{take_id}/content", response_class=FileResponse)
async def get_take_content(
    take_id: str,
    user: User,
    service: Service,
) -> FileResponse:
    path, mime_type, filename = await service.get_take_file(user.id, take_id)
    return FileResponse(
        path,
        media_type=mime_type,
        filename=filename,
        content_disposition_type="inline",
    )


@router.get(
    "/provider-assets/{token}",
    response_class=FileResponse,
    include_in_schema=False,
)
async def get_provider_asset(token: str, service: Service) -> FileResponse:
    """只凭短时 HMAC token 返回已确认参考图；该地址供 Seedance 拉取。"""

    path, mime_type = await service.get_provider_asset_file(token)
    return FileResponse(path, media_type=mime_type)

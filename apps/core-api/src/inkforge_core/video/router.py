"""浏览器可访问的视频制作公共接口。"""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse
from inkforge_contracts.video import AssetDuty, AssetModality

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    ApproveVideoSceneRequest,
    ApproveVideoSceneResponse,
    ConfirmVideoAssetRequest,
    CreateVideoProjectRequest,
    CreateVideoSceneRequest,
    CreateVideoSceneResponse,
    PromptPreviewRequest,
    PromptPreviewResponse,
    ReviseVideoSceneRequest,
    VideoAssetResponse,
    VideoProjectDetailResponse,
    VideoProjectListResponse,
    VideoProjectResponse,
    VideoSceneResponse,
)
from .service import VideoService

router = APIRouter(prefix="/video", tags=["视频制作"])


def get_video_service(request: Request) -> VideoService:
    """从应用状态读取视频服务，缺失时返回稳定公共错误。"""

    service = cast(VideoService | None, getattr(request.app.state, "video_service", None))
    if service is None:
        raise ApiError(
            status_code=503,
            code="VIDEO_SERVICE_UNAVAILABLE",
            message="视频制作服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[VideoService, Depends(get_video_service)]


@router.post(
    "/novels/{novel_id}/projects",
    response_model=VideoProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    novel_id: str,
    body: CreateVideoProjectRequest,
    user: User,
    service: Service,
) -> VideoProjectResponse:
    """为当前小说创建视频项目。"""

    return await service.create_project(user.id, novel_id, body)


@router.get("/novels/{novel_id}/projects", response_model=VideoProjectListResponse)
async def list_projects(
    novel_id: str,
    user: User,
    service: Service,
) -> VideoProjectListResponse:
    """列出当前小说的视频项目。"""

    return await service.list_projects(user.id, novel_id)


@router.get("/projects/{project_id}", response_model=VideoProjectDetailResponse)
async def get_project(
    project_id: str,
    user: User,
    service: Service,
) -> VideoProjectDetailResponse:
    """加载视频制作台。"""

    return await service.get_project(user.id, project_id)


@router.post(
    "/projects/{project_id}/scenes",
    response_model=CreateVideoSceneResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_scene(
    project_id: str,
    body: CreateVideoSceneRequest,
    user: User,
    service: Service,
) -> CreateVideoSceneResponse:
    """冻结原文并提交一个真实的视频规划任务。"""

    return await service.create_scene(user.id, project_id, body)


@router.get("/scenes/{scene_id}", response_model=VideoSceneResponse)
async def get_scene(
    scene_id: str,
    user: User,
    service: Service,
) -> VideoSceneResponse:
    """轮询场景、任务和审核状态。"""

    return await service.get_scene(user.id, scene_id)


@router.post(
    "/scenes/{scene_id}/retry",
    response_model=CreateVideoSceneResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_scene(
    scene_id: str,
    user: User,
    service: Service,
) -> CreateVideoSceneResponse:
    """复用冻结输入重新生成失败场景，不创建新的场景记录。"""

    return await service.retry_scene(user.id, scene_id)


@router.post(
    "/scenes/{scene_id}/revise",
    response_model=CreateVideoSceneResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def revise_scene(
    scene_id: str,
    body: ReviseVideoSceneRequest,
    user: User,
    service: Service,
) -> CreateVideoSceneResponse:
    """保存当前候选快照，并按作者意见重新规划同一个场景。"""

    return await service.revise_scene(user.id, scene_id, body)


@router.post("/scenes/{scene_id}/approve", response_model=ApproveVideoSceneResponse)
async def approve_scene(
    scene_id: str,
    body: ApproveVideoSceneRequest,
    user: User,
    service: Service,
) -> ApproveVideoSceneResponse:
    """用户显式批准候选，正式写入场景方案。"""

    return await service.approve_scene(user.id, scene_id, body)


@router.post(
    "/scenes/{scene_id}/prompt-preview",
    response_model=PromptPreviewResponse,
)
async def preview_prompt(
    scene_id: str,
    body: PromptPreviewRequest,
    user: User,
    service: Service,
) -> PromptPreviewResponse:
    """基于正式场景方案和已锁定素材生成一次性开发预览包。"""

    return await service.preview_prompt(user.id, scene_id, body)


@router.post(
    "/projects/{project_id}/assets",
    response_model=VideoAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_asset(
    project_id: str,
    user: User,
    service: Service,
    file: Annotated[UploadFile, File()],
    name: Annotated[str, Form(min_length=1, max_length=200)],
    modality: Annotated[AssetModality, Form()],
    duty: Annotated[AssetDuty, Form()],
    source_kind: Annotated[
        Literal["user_upload", "authorized_real", "virtual", "model_generated"],
        Form(alias="sourceKind"),
    ] = "user_upload",
) -> VideoAssetResponse:
    """上传并登记一份真实图片、视频或音频素材。"""

    return await service.upload_asset(
        user.id,
        project_id,
        upload=file,
        name=name,
        modality=modality,
        duty=duty,
        source_kind=source_kind,
    )


@router.patch("/assets/{asset_id}/rights", response_model=VideoAssetResponse)
async def confirm_asset(
    asset_id: str,
    body: ConfirmVideoAssetRequest,
    user: User,
    service: Service,
) -> VideoAssetResponse:
    """确认或拒绝素材权利；只有 confirmed 会锁定素材。"""

    return await service.confirm_asset(user.id, asset_id, body.rightsStatus)


@router.get("/assets/{asset_id}/content", response_class=FileResponse)
async def download_asset(
    asset_id: str,
    user: User,
    service: Service,
) -> FileResponse:
    """经过小说归属校验后返回素材内容。"""

    path, mime_type, filename = await service.get_asset_file(user.id, asset_id)
    return FileResponse(path, media_type=mime_type, filename=filename)

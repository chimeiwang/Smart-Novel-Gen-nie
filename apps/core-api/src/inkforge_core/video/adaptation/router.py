"""项目级视觉设定公共接口；旧 ChapterAdaptation 路由已退场。"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .schemas import (
    ApproveVisualCanonRequest,
    CreateVisualCanonCandidateRequest,
    VisualCanonLibraryResponse,
    VisualCanonResponse,
)
from .visual_canon_service import VideoVisualCanonService

router = APIRouter(prefix="/video", tags=["视觉设定"])


def get_video_visual_canon_service(request: Request) -> VideoVisualCanonService:
    service = cast(
        VideoVisualCanonService | None,
        getattr(request.app.state, "video_visual_canon_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="VIDEO_SERVICE_UNAVAILABLE",
            message="视觉设定服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[VideoVisualCanonService, Depends(get_video_visual_canon_service)]


@router.get(
    "/projects/{project_id}/visual-canons",
    response_model=VisualCanonLibraryResponse,
)
async def list_visual_canons(
    project_id: str,
    user: User,
    service: Service,
) -> VisualCanonLibraryResponse:
    return await service.list_canons(user.id, project_id)


@router.post(
    "/projects/{project_id}/visual-canons",
    response_model=VisualCanonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def set_visual_canon_candidate(
    project_id: str,
    body: CreateVisualCanonCandidateRequest,
    user: User,
    service: Service,
) -> VisualCanonResponse:
    return await service.set_candidate(user.id, project_id, body)


@router.post(
    "/visual-canons/{canon_id}/approve",
    response_model=VisualCanonResponse,
)
async def approve_visual_canon(
    canon_id: str,
    body: ApproveVisualCanonRequest,
    user: User,
    service: Service,
) -> VisualCanonResponse:
    return await service.approve(user.id, canon_id, body)

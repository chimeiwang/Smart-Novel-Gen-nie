from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, status

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    CreateNovelRequest,
    CreateNovelResponse,
    DashboardResponse,
    NovelResponse,
    WorkspaceResponse,
)
from .service import NovelService

router = APIRouter(tags=["小说"])


def get_novel_service(request: Request) -> NovelService:
    service = cast(NovelService | None, getattr(request.app.state, "novel_service", None))
    if service is None:
        raise ApiError(
            status_code=503, code="NOVEL_SERVICE_UNAVAILABLE", message="小说服务暂时不可用"
        )
    return service


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[NovelService, Depends(get_novel_service)],
) -> DashboardResponse:
    return await service.dashboard(user.id)


@router.get("/novels", response_model=list[NovelResponse])
async def list_novels(
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[NovelService, Depends(get_novel_service)],
) -> list[NovelResponse]:
    return await service.list_novels(user.id)


@router.post("/novels", response_model=CreateNovelResponse, status_code=status.HTTP_201_CREATED)
async def create_novel(
    body: CreateNovelRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[NovelService, Depends(get_novel_service)],
) -> CreateNovelResponse:
    return await service.create_novel(user.id, body)


@router.get("/novels/{novel_id}", response_model=NovelResponse)
async def get_novel(
    novel_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[NovelService, Depends(get_novel_service)],
) -> NovelResponse:
    return await service.get_novel(user.id, novel_id)


@router.get("/novels/{novel_id}/workspace", response_model=WorkspaceResponse)
async def get_workspace(
    novel_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[NovelService, Depends(get_novel_service)],
    chapter_id: Annotated[str | None, Query(alias="chapterId")] = None,
) -> WorkspaceResponse:
    return await service.get_workspace(user.id, novel_id, chapter_id)

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from ..novels.schemas import WorkspaceChapter
from .schemas import (
    ChapterListResponse,
    ChapterMutationResponse,
    ChapterProgressRequest,
    ChapterStatusRequest,
    ChapterStatusResponse,
    CreateChapterResponse,
    UpdateChapterRequest,
)
from .service import ChapterService

router = APIRouter(tags=["章节"])


def get_chapter_service(request: Request) -> ChapterService:
    service = cast(ChapterService | None, getattr(request.app.state, "chapter_service", None))
    if service is None:
        raise ApiError(
            status_code=503, code="CHAPTER_SERVICE_UNAVAILABLE", message="章节服务暂时不可用"
        )
    return service


@router.get("/novels/{novel_id}/chapters", response_model=ChapterListResponse)
async def list_chapters(
    novel_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[ChapterService, Depends(get_chapter_service)],
) -> ChapterListResponse:
    return ChapterListResponse(chapters=await service.list_chapters(user.id, novel_id))


@router.post(
    "/novels/{novel_id}/chapters",
    response_model=CreateChapterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chapter(
    novel_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[ChapterService, Depends(get_chapter_service)],
) -> CreateChapterResponse:
    chapter = await service.create_chapter(user.id, novel_id)
    return CreateChapterResponse(chapter=chapter)


@router.get("/chapters/{chapter_id}", response_model=WorkspaceChapter)
async def get_chapter(
    chapter_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[ChapterService, Depends(get_chapter_service)],
) -> WorkspaceChapter:
    return await service.get_chapter(user.id, chapter_id)


@router.patch("/chapters/{chapter_id}", response_model=ChapterMutationResponse)
async def update_chapter(
    chapter_id: str,
    body: UpdateChapterRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[ChapterService, Depends(get_chapter_service)],
) -> ChapterMutationResponse:
    return await service.update_chapter(user.id, chapter_id, body)


@router.patch("/chapters/{chapter_id}/status", response_model=ChapterStatusResponse)
async def update_chapter_status(
    chapter_id: str,
    body: ChapterStatusRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[ChapterService, Depends(get_chapter_service)],
) -> ChapterStatusResponse:
    return await service.set_status(user.id, chapter_id, body)


@router.put("/chapters/{chapter_id}/progress", response_model=ChapterMutationResponse)
async def update_chapter_progress(
    chapter_id: str,
    body: ChapterProgressRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[ChapterService, Depends(get_chapter_service)],
) -> ChapterMutationResponse:
    return await service.update_progress(user.id, chapter_id, body)

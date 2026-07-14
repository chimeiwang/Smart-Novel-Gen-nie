from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    ApplyStyleRequest,
    CreateStyleRequest,
    PortraitAcceptedResponse,
    PortraitSection,
    PortraitTaskResponse,
    StyleReferenceResponse,
    StyleResponse,
    UpdatePortraitSectionRequest,
)
from .service import StyleService

router = APIRouter(tags=["文风画像"])


def get_style_service(request: Request) -> StyleService:
    service = cast(StyleService | None, getattr(request.app.state, "style_service", None))
    if service is None:
        raise ApiError(
            status_code=503,
            code="STYLE_SERVICE_UNAVAILABLE",
            message="文风服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[StyleService, Depends(get_style_service)]


@router.get("/styles", response_model=list[StyleResponse])
async def list_styles(user: User, service: Service) -> list[StyleResponse]:
    return await service.list_styles(user.id)


@router.post("/styles", response_model=StyleResponse, status_code=status.HTTP_201_CREATED)
async def create_style(body: CreateStyleRequest, user: User, service: Service) -> StyleResponse:
    return await service.create_style(user.id, body)


@router.delete("/styles/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_style(style_id: str, user: User, service: Service) -> Response:
    await service.delete_style(user.id, style_id)
    return Response(status_code=204)


@router.post(
    "/styles/{style_id}/references",
    response_model=StyleReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference(
    style_id: str,
    user: User,
    service: Service,
    file: Annotated[UploadFile, File()],
) -> StyleReferenceResponse:
    return await service.upload_reference(user.id, style_id, file)


@router.delete(
    "/styles/{style_id}/references/{reference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_reference(
    style_id: str,
    reference_id: str,
    user: User,
    service: Service,
) -> Response:
    await service.delete_reference(user.id, style_id, reference_id)
    return Response(status_code=204)


@router.post(
    "/styles/{style_id}/portrait",
    response_model=PortraitAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_portrait(style_id: str, user: User, service: Service) -> PortraitAcceptedResponse:
    return await service.create_portrait(user.id, style_id)


@router.post(
    "/styles/{style_id}/sections/{section}/portrait",
    response_model=PortraitAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_section_portrait(
    style_id: str,
    section: PortraitSection,
    user: User,
    service: Service,
) -> PortraitAcceptedResponse:
    return await service.create_portrait(user.id, style_id, section)


@router.get("/portrait-tasks/{task_id}", response_model=PortraitTaskResponse)
async def get_portrait_task(task_id: str, user: User, service: Service) -> PortraitTaskResponse:
    return await service.get_portrait_task(user.id, task_id)


@router.patch(
    "/styles/{style_id}/sections/{section}",
    response_model=StyleResponse,
)
async def update_section(
    style_id: str,
    section: PortraitSection,
    body: UpdatePortraitSectionRequest,
    user: User,
    service: Service,
) -> StyleResponse:
    return await service.update_section(user.id, style_id, section, body)


@router.patch(
    "/novels/{novel_id}/applied-style",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def apply_style(
    novel_id: str,
    body: ApplyStyleRequest,
    user: User,
    service: Service,
) -> Response:
    await service.apply_style(user.id, novel_id, body)
    return Response(status_code=204)

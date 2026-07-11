from __future__ import annotations

# mypy: disable-error-code="no-untyped-def"
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    CreateForeshadowingRequest,
    CreateOutlineNodeRequest,
    OutlineContentRequest,
    PlotProgressRequest,
    UpdateForeshadowingRequest,
    UpdateOutlineNodeRequest,
)
from .service import OutlineService

router = APIRouter(tags=["大纲"])


def get_outline_service(request: Request) -> OutlineService:
    service = cast(OutlineService | None, getattr(request.app.state, "outline_service", None))
    if service is None:
        raise ApiError(
            status_code=503, code="OUTLINE_SERVICE_UNAVAILABLE", message="大纲服务暂时不可用"
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[OutlineService, Depends(get_outline_service)]


@router.put("/novels/{novel_id}/outline")
async def save_outline(novel_id: str, body: OutlineContentRequest, user: User, service: Service):
    return await service.save_outline(user.id, novel_id, body)


@router.put("/novels/{novel_id}/plot-progress")
async def save_plot(novel_id: str, body: PlotProgressRequest, user: User, service: Service):
    return await service.save_plot(user.id, novel_id, body)


@router.get("/novels/{novel_id}/outline-nodes")
async def list_nodes(novel_id: str, user: User, service: Service):
    return await service.list_nodes(user.id, novel_id)


@router.post("/novels/{novel_id}/outline-nodes", status_code=201)
async def create_node(novel_id: str, body: CreateOutlineNodeRequest, user: User, service: Service):
    return await service.create_node(user.id, novel_id, body)


@router.patch("/novels/{novel_id}/outline-nodes/{node_id}")
async def update_node(
    novel_id: str, node_id: str, body: UpdateOutlineNodeRequest, user: User, service: Service
):
    return await service.update_node(user.id, novel_id, node_id, body)


@router.delete("/novels/{novel_id}/outline-nodes/{node_id}", status_code=204)
async def delete_node(novel_id: str, node_id: str, user: User, service: Service):
    await service.delete_node(user.id, novel_id, node_id)
    return Response(status_code=204)


@router.get("/novels/{novel_id}/foreshadowings")
async def list_foreshadowings(novel_id: str, user: User, service: Service):
    return await service.list_foreshadowings(user.id, novel_id)


@router.post("/novels/{novel_id}/foreshadowings", status_code=201)
async def create_foreshadowing(
    novel_id: str, body: CreateForeshadowingRequest, user: User, service: Service
):
    return await service.create_foreshadowing(user.id, novel_id, body)


@router.patch("/novels/{novel_id}/foreshadowings/{foreshadowing_id}")
async def update_foreshadowing(
    novel_id: str,
    foreshadowing_id: str,
    body: UpdateForeshadowingRequest,
    user: User,
    service: Service,
):
    return await service.update_foreshadowing(user.id, novel_id, foreshadowing_id, body)


@router.delete("/novels/{novel_id}/foreshadowings/{foreshadowing_id}", status_code=204)
async def delete_foreshadowing(novel_id: str, foreshadowing_id: str, user: User, service: Service):
    await service.delete_foreshadowing(user.id, novel_id, foreshadowing_id)
    return Response(status_code=204)

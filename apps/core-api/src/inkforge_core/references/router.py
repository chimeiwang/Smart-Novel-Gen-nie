from __future__ import annotations

# mypy: disable-error-code="no-untyped-def"
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, Response

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    CreateReferenceRequest,
    RagSearchRequest,
    RagSearchResult,
    ReferenceMaterialResponse,
    ReindexAcceptedResponse,
    UpdateReferenceRequest,
)
from .service import ReferenceService

router = APIRouter(tags=["参考资料"])


def get_reference_service(request: Request) -> ReferenceService:
    service = cast(ReferenceService | None, getattr(request.app.state, "reference_service", None))
    if service is None:
        raise ApiError(
            status_code=503,
            code="REFERENCE_SERVICE_UNAVAILABLE",
            message="参考资料服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[ReferenceService, Depends(get_reference_service)]


@router.get("/novels/{novel_id}/references", response_model=list[ReferenceMaterialResponse])
async def list_references(novel_id: str, user: User, service: Service):
    return await service.list_references(user.id, novel_id)


@router.post(
    "/novels/{novel_id}/references", response_model=ReferenceMaterialResponse, status_code=201
)
async def create_reference(
    novel_id: str, body: CreateReferenceRequest, user: User, service: Service
):
    return await service.create_reference(user.id, novel_id, body)


@router.patch(
    "/novels/{novel_id}/references/{reference_id}", response_model=ReferenceMaterialResponse
)
async def update_reference(
    novel_id: str,
    reference_id: str,
    body: UpdateReferenceRequest,
    user: User,
    service: Service,
):
    return await service.update(user.id, novel_id, reference_id, body)


@router.delete("/novels/{novel_id}/references/{reference_id}", status_code=204)
async def delete_reference(novel_id: str, reference_id: str, user: User, service: Service):
    await service.delete(user.id, novel_id, reference_id)
    return Response(status_code=204)


@router.post(
    "/novels/{novel_id}/references/{reference_id}/reindex",
    response_model=ReindexAcceptedResponse,
    status_code=202,
)
async def reindex_reference(novel_id: str, reference_id: str, user: User, service: Service):
    await service.reindex(user.id, novel_id, reference_id)
    return ReindexAcceptedResponse(accepted=True)


@router.post("/novels/{novel_id}/references/search", response_model=list[RagSearchResult])
async def search_references(novel_id: str, body: RagSearchRequest, user: User, service: Service):
    return await service.search(user.id, novel_id, body.embedding, body.topK)

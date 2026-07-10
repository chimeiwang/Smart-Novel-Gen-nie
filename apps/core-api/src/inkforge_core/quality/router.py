from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from ..novels.schemas import QualityCheckDto
from .schemas import RunQualityCheckRequest, RunQualityCheckResponse, UpdateQualityCheckRequest
from .service import QualityService

router = APIRouter(tags=["质量检查"])


def get_quality_service(request: Request) -> QualityService:
    service = cast(QualityService | None, getattr(request.app.state, "quality_service", None))
    if service is None:
        raise ApiError(
            status_code=503, code="QUALITY_SERVICE_UNAVAILABLE", message="质量检查服务暂时不可用"
        )
    return service


@router.get("/quality-checks/{check_id}", response_model=QualityCheckDto)
async def get_quality_check(
    check_id: str,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[QualityService, Depends(get_quality_service)],
) -> QualityCheckDto:
    return await service.get_check(user.id, check_id)


@router.patch("/quality-checks/{check_id}", response_model=QualityCheckDto)
async def update_quality_check(
    check_id: str,
    body: UpdateQualityCheckRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[QualityService, Depends(get_quality_service)],
) -> QualityCheckDto:
    return await service.update_status(user.id, check_id, body)


@router.post(
    "/quality-checks/{check_id}/run",
    response_model=RunQualityCheckResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_quality_check(
    check_id: str,
    body: RunQualityCheckRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
    service: Annotated[QualityService, Depends(get_quality_service)],
) -> RunQualityCheckResponse:
    return await service.run(user.id, check_id, body)

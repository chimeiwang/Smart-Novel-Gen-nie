from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .schemas import (
    DocumentType,
    ManualVersionRequest,
    VersionActionRequest,
    VersionDetailResponse,
    VersionDiffResponse,
    VersionListItem,
    VersionPreviewRequest,
    VersionPreviewResponse,
)
from .service import ShortMediumVersionService

router = APIRouter(tags=["中短篇版本"])


def get_short_medium_version_service(request: Request) -> ShortMediumVersionService:
    service = cast(
        ShortMediumVersionService | None,
        getattr(request.app.state, "short_medium_version_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="SHORT_MEDIUM_VERSION_SERVICE_UNAVAILABLE",
            message="中短篇版本服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[
    ShortMediumVersionService, Depends(get_short_medium_version_service)
]


@router.get(
    "/novels/{novel_id}/versions",
    response_model=list[VersionListItem],
)
async def list_versions(
    novel_id: str,
    user: User,
    service: Service,
    document_type: Annotated[DocumentType, Query(alias="documentType")],
    chapter_id: Annotated[str | None, Query(alias="chapterId")] = None,
) -> list[VersionListItem]:
    return await service.list_versions(
        user.id, novel_id, document_type, chapter_id
    )


@router.get(
    "/novels/{novel_id}/versions/{version_id}",
    response_model=VersionDetailResponse,
)
async def get_version(
    novel_id: str,
    version_id: str,
    user: User,
    service: Service,
) -> VersionDetailResponse:
    return await service.get_version(user.id, novel_id, version_id)


@router.get(
    "/novels/{novel_id}/version-diff",
    response_model=VersionDiffResponse,
)
async def get_version_diff(
    novel_id: str,
    user: User,
    service: Service,
    from_version_id: Annotated[str, Query(alias="fromVersionId")],
    to_version_id: Annotated[str, Query(alias="toVersionId")],
) -> VersionDiffResponse:
    return await service.diff_versions(
        user.id, novel_id, from_version_id, to_version_id
    )


@router.post(
    "/novels/{novel_id}/versions/preview",
    response_model=VersionPreviewResponse,
)
async def preview_version(
    novel_id: str,
    body: VersionPreviewRequest,
    user: User,
    service: Service,
) -> VersionPreviewResponse:
    return await service.preview(user.id, novel_id, body)


@router.post(
    "/novels/{novel_id}/versions",
    response_model=VersionDetailResponse,
)
async def submit_manual_version(
    novel_id: str,
    body: ManualVersionRequest,
    user: User,
    service: Service,
) -> VersionDetailResponse:
    return await service.submit_manual(user.id, novel_id, body)


@router.post(
    "/novels/{novel_id}/versions/{version_id}/adopt",
    response_model=VersionDetailResponse,
)
async def adopt_candidate_version(
    novel_id: str,
    version_id: str,
    body: VersionActionRequest,
    user: User,
    service: Service,
) -> VersionDetailResponse:
    return await service.adopt(user.id, novel_id, version_id, body)


@router.post(
    "/novels/{novel_id}/versions/{version_id}/restore",
    response_model=VersionDetailResponse,
)
async def restore_historical_version(
    novel_id: str,
    version_id: str,
    body: VersionActionRequest,
    user: User,
    service: Service,
) -> VersionDetailResponse:
    return await service.restore(user.id, novel_id, version_id, body)


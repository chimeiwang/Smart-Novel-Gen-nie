"""独立分集后期与交付的 Java Core 公共 OpenAPI 来源。"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .post_production_schemas import (
    CreateVideoEpisodeEditVersionRequest,
    CreateVideoEpisodeMixVersionRequest,
    RetryVideoEpisodeExportRequest,
    StartVideoEpisodeExportRequest,
    VideoEpisodeDeliveryResponse,
    VideoEpisodeEditVersionListResponse,
    VideoEpisodeEditVersionResponse,
    VideoEpisodeExportTaskResponse,
    VideoEpisodeMixVersionListResponse,
    VideoEpisodeMixVersionResponse,
)

router = APIRouter(prefix="/video", tags=["VideoEpisodePostProduction"])
User = Annotated[AuthUser, Depends(get_current_user)]


def _java_runtime_only() -> NoReturn:
    raise ApiError(
        status_code=503,
        code="JAVA_CORE_REQUIRED",
        message="独立分集后期与交付由 Java Core 提供服务",
    )


@router.post(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions",
    response_model=VideoEpisodeEditVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_video_episode_edit_version(
    episode_id: str,
    baseline_id: str,
    body: CreateVideoEpisodeEditVersionRequest,
    user: User,
) -> VideoEpisodeEditVersionResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions",
    response_model=VideoEpisodeEditVersionListResponse,
)
async def list_video_episode_edit_versions(
    episode_id: str,
    baseline_id: str,
    user: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    beforeVersionNo: Annotated[int | None, Query(ge=1)] = None,
) -> VideoEpisodeEditVersionListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/edit-versions/{version_id}",
    response_model=VideoEpisodeEditVersionResponse,
)
async def get_video_episode_edit_version(
    episode_id: str,
    baseline_id: str,
    version_id: str,
    user: User,
) -> VideoEpisodeEditVersionResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions",
    response_model=VideoEpisodeMixVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_video_episode_mix_version(
    episode_id: str,
    baseline_id: str,
    body: CreateVideoEpisodeMixVersionRequest,
    user: User,
) -> VideoEpisodeMixVersionResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions",
    response_model=VideoEpisodeMixVersionListResponse,
)
async def list_video_episode_mix_versions(
    episode_id: str,
    baseline_id: str,
    user: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    beforeVersionNo: Annotated[int | None, Query(ge=1)] = None,
) -> VideoEpisodeMixVersionListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/mix-versions/{version_id}",
    response_model=VideoEpisodeMixVersionResponse,
)
async def get_video_episode_mix_version(
    episode_id: str,
    baseline_id: str,
    version_id: str,
    user: User,
) -> VideoEpisodeMixVersionResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks",
    response_model=VideoEpisodeExportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_video_episode_export(
    episode_id: str,
    baseline_id: str,
    body: StartVideoEpisodeExportRequest,
    user: User,
) -> VideoEpisodeExportTaskResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}",
    response_model=VideoEpisodeExportTaskResponse,
)
async def get_video_episode_export_task(
    episode_id: str,
    baseline_id: str,
    task_id: str,
    user: User,
) -> VideoEpisodeExportTaskResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/export-tasks/{task_id}/retry",
    response_model=VideoEpisodeExportTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_video_episode_export(
    episode_id: str,
    baseline_id: str,
    task_id: str,
    body: RetryVideoEpisodeExportRequest,
    user: User,
) -> VideoEpisodeExportTaskResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/exports/{export_id}",
    response_model=VideoEpisodeDeliveryResponse,
)
async def get_video_episode_delivery(
    episode_id: str,
    baseline_id: str,
    export_id: str,
    user: User,
) -> VideoEpisodeDeliveryResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}/exports/{export_id}/content",
    response_class=FileResponse,
)
async def get_video_episode_delivery_content(
    episode_id: str,
    baseline_id: str,
    export_id: str,
    user: User,
) -> FileResponse:
    _java_runtime_only()

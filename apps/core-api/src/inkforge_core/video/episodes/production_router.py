"""Java Core 视频分镜与制作基线公共 OpenAPI 的唯一来源。"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Query

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .production_schemas import (
    AdoptVideoStoryboardCandidateRequest,
    ApproveVideoStoryboardConfirmationRequest,
    CreateVideoProductionBaselineRequest,
    CreateVideoTakeAdoptionRequest,
    PrepareVideoStoryboardConfirmationRequest,
    SaveVideoStoryboardDraftRequest,
    StartVideoStoryboardRunRequest,
    VideoProductionBaselineListResponse,
    VideoProductionBaselineResponse,
    VideoProductionCapabilityResponse,
    VideoStoryboardCandidateResponse,
    VideoStoryboardConfirmationResponse,
    VideoStoryboardDraftResponse,
    VideoStoryboardRunListResponse,
    VideoStoryboardRunResponse,
    VideoStoryboardVersionListResponse,
    VideoStoryboardVersionResponse,
    VideoTakeAdoptionResponse,
    VideoTakeCandidateListResponse,
)

router = APIRouter(prefix="/video", tags=["VideoProduction"])
User = Annotated[AuthUser, Depends(get_current_user)]


def _java_runtime_only() -> NoReturn:
    raise ApiError(
        status_code=503, code="JAVA_CORE_REQUIRED", message="独立剧集制作由 Java Core 提供服务"
    )


@router.get("/production-capabilities", response_model=VideoProductionCapabilityResponse)
async def get_video_production_capabilities(user: User) -> VideoProductionCapabilityResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/storyboard/draft",
    response_model=VideoStoryboardDraftResponse,
)
async def get_video_storyboard_draft(
    episode_id: str, user: User
) -> VideoStoryboardDraftResponse:
    _java_runtime_only()


@router.put(
    "/episodes/{episode_id}/storyboard/draft",
    response_model=VideoStoryboardDraftResponse,
)
async def save_video_storyboard_draft(
    episode_id: str, body: SaveVideoStoryboardDraftRequest, user: User
) -> VideoStoryboardDraftResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/storyboard/runs",
    response_model=VideoStoryboardRunResponse,
    status_code=202,
)
async def start_video_storyboard_run(
    episode_id: str, body: StartVideoStoryboardRunRequest, user: User
) -> VideoStoryboardRunResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/storyboard/runs",
    response_model=VideoStoryboardRunListResponse,
)
async def list_video_storyboard_runs(
    episode_id: str,
    user: User,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    beforeRunId: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
) -> VideoStoryboardRunListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/storyboard/runs/{run_id}",
    response_model=VideoStoryboardRunResponse,
)
async def get_video_storyboard_run(
    episode_id: str, run_id: str, user: User
) -> VideoStoryboardRunResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/storyboard/candidates/{artifact_id}",
    response_model=VideoStoryboardCandidateResponse,
)
async def get_video_storyboard_candidate(
    episode_id: str, artifact_id: str, user: User
) -> VideoStoryboardCandidateResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/storyboard/candidates/{artifact_id}/adopt",
    response_model=VideoStoryboardDraftResponse,
)
async def adopt_video_storyboard_candidate(
    episode_id: str,
    artifact_id: str,
    body: AdoptVideoStoryboardCandidateRequest,
    user: User,
) -> VideoStoryboardDraftResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/storyboard/confirmations",
    response_model=VideoStoryboardConfirmationResponse,
    status_code=201,
)
async def prepare_video_storyboard_confirmation(
    episode_id: str, body: PrepareVideoStoryboardConfirmationRequest, user: User
) -> VideoStoryboardConfirmationResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/storyboard/confirmations/{artifact_id}",
    response_model=VideoStoryboardConfirmationResponse,
)
async def get_video_storyboard_confirmation(
    episode_id: str, artifact_id: str, user: User
) -> VideoStoryboardConfirmationResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/storyboard/confirmations/{artifact_id}/approve",
    response_model=VideoStoryboardVersionResponse,
    status_code=201,
)
async def approve_video_storyboard_confirmation(
    episode_id: str,
    artifact_id: str,
    body: ApproveVideoStoryboardConfirmationRequest,
    user: User,
) -> VideoStoryboardVersionResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/storyboard/versions",
    response_model=VideoStoryboardVersionListResponse,
)
async def list_video_storyboard_versions(
    episode_id: str,
    user: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    beforeVersionNo: Annotated[int | None, Query(ge=1)] = None,
) -> VideoStoryboardVersionListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/storyboard/versions/{version_id}",
    response_model=VideoStoryboardVersionResponse,
)
async def get_video_storyboard_version(
    episode_id: str, version_id: str, user: User
) -> VideoStoryboardVersionResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/take-adoptions",
    response_model=VideoTakeAdoptionResponse,
    status_code=201,
)
async def create_video_take_adoption(
    episode_id: str, body: CreateVideoTakeAdoptionRequest, user: User
) -> VideoTakeAdoptionResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/takes",
    response_model=VideoTakeCandidateListResponse,
)
async def list_video_take_candidates(
    episode_id: str,
    user: User,
    targetShotVersionId: Annotated[str, Query(min_length=1, max_length=128)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    beforeTakeId: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
) -> VideoTakeCandidateListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/take-adoptions/{adoption_id}",
    response_model=VideoTakeAdoptionResponse,
)
async def get_video_take_adoption(
    episode_id: str, adoption_id: str, user: User
) -> VideoTakeAdoptionResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/production-baselines",
    response_model=VideoProductionBaselineResponse,
    status_code=201,
)
async def create_video_production_baseline(
    episode_id: str, body: CreateVideoProductionBaselineRequest, user: User
) -> VideoProductionBaselineResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines",
    response_model=VideoProductionBaselineListResponse,
)
async def list_video_production_baselines(
    episode_id: str,
    user: User,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    beforeVersionNo: Annotated[int | None, Query(ge=1)] = None,
) -> VideoProductionBaselineListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/production-baselines/{baseline_id}",
    response_model=VideoProductionBaselineResponse,
)
async def get_video_production_baseline(
    episode_id: str, baseline_id: str, user: User
) -> VideoProductionBaselineResponse:
    _java_runtime_only()

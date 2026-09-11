"""Java Core 独立剧集公共接口的 OpenAPI 唯一来源；Python 不建立第二份运行实现。"""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .schemas import (
    AdoptVideoEpisodeScriptCandidateRequest,
    ApproveVideoEpisodeScriptConfirmationRequest,
    CreateVideoEpisodeRequest,
    CreateVideoEpisodeSourceSetRequest,
    PrepareVideoEpisodeScriptConfirmationRequest,
    ReorderVideoEpisodesRequest,
    SaveVideoEpisodeScriptDraftRequest,
    StartVideoEpisodeScriptRunRequest,
    UpdateVideoEpisodeRequest,
    VideoEpisodeCommandResponse,
    VideoEpisodeDetailResponse,
    VideoEpisodeListResponse,
    VideoEpisodeResponse,
    VideoEpisodeScriptConfirmationResponse,
    VideoEpisodeScriptDraftResponse,
    VideoEpisodeScriptRunResponse,
    VideoEpisodeScriptVersionListResponse,
    VideoEpisodeScriptVersionResponse,
    VideoEpisodeSourceSetListResponse,
    VideoEpisodeSourceSetResponse,
)

router = APIRouter(prefix="/video", tags=["VideoEpisodes"])
User = Annotated[AuthUser, Depends(get_current_user)]


def _java_runtime_only() -> NoReturn:
    raise ApiError(
        status_code=503, code="JAVA_CORE_REQUIRED", message="独立剧集由 Java Core 提供服务"
    )


@router.post(
    "/projects/{project_id}/episodes", response_model=VideoEpisodeResponse, status_code=201
)
async def create_video_episode(
    project_id: str,
    body: CreateVideoEpisodeRequest,
    user: User,
) -> VideoEpisodeResponse:
    _java_runtime_only()


@router.get(
    "/projects/{project_id}/episodes", response_model=VideoEpisodeListResponse, status_code=200
)
async def list_video_episodes(
    project_id: str,
    user: User,
) -> VideoEpisodeListResponse:
    _java_runtime_only()


@router.post(
    "/projects/{project_id}/episodes/reorder",
    response_model=VideoEpisodeListResponse,
    status_code=200,
)
async def reorder_video_episodes(
    project_id: str,
    body: ReorderVideoEpisodesRequest,
    user: User,
) -> VideoEpisodeListResponse:
    _java_runtime_only()


@router.get("/episodes/{episode_id}", response_model=VideoEpisodeDetailResponse, status_code=200)
async def get_video_episode(
    episode_id: str,
    user: User,
) -> VideoEpisodeDetailResponse:
    _java_runtime_only()


@router.patch("/episodes/{episode_id}", response_model=VideoEpisodeResponse, status_code=200)
async def update_video_episode(
    episode_id: str,
    body: UpdateVideoEpisodeRequest,
    user: User,
) -> VideoEpisodeResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/source-sets",
    response_model=VideoEpisodeSourceSetResponse,
    status_code=201,
)
async def create_video_episode_source_set(
    episode_id: str,
    body: CreateVideoEpisodeSourceSetRequest,
    user: User,
) -> VideoEpisodeSourceSetResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/source-sets",
    response_model=VideoEpisodeSourceSetListResponse,
    status_code=200,
)
async def list_video_episode_source_sets(
    episode_id: str,
    user: User,
) -> VideoEpisodeSourceSetListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/source-sets/{version_id}",
    response_model=VideoEpisodeSourceSetResponse,
    status_code=200,
)
async def get_video_episode_source_set(
    episode_id: str,
    version_id: str,
    user: User,
) -> VideoEpisodeSourceSetResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/script/draft",
    response_model=VideoEpisodeScriptDraftResponse,
    status_code=200,
)
async def get_video_episode_script_draft(
    episode_id: str,
    user: User,
) -> VideoEpisodeScriptDraftResponse:
    _java_runtime_only()


@router.put(
    "/episodes/{episode_id}/script/draft",
    response_model=VideoEpisodeScriptDraftResponse,
    status_code=200,
)
async def save_video_episode_script_draft(
    episode_id: str,
    body: SaveVideoEpisodeScriptDraftRequest,
    user: User,
) -> VideoEpisodeScriptDraftResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/script/runs",
    response_model=VideoEpisodeScriptRunResponse,
    status_code=202,
)
async def start_video_episode_script_run(
    episode_id: str,
    body: StartVideoEpisodeScriptRunRequest,
    user: User,
) -> VideoEpisodeScriptRunResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/script/runs/{run_id}",
    response_model=VideoEpisodeScriptRunResponse,
    status_code=200,
)
async def get_video_episode_script_run(
    episode_id: str,
    run_id: str,
    user: User,
) -> VideoEpisodeScriptRunResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/script/candidates/{artifact_id}/adopt",
    response_model=VideoEpisodeScriptDraftResponse,
    status_code=200,
)
async def adopt_video_episode_script_candidate(
    episode_id: str,
    artifact_id: str,
    body: AdoptVideoEpisodeScriptCandidateRequest,
    user: User,
) -> VideoEpisodeScriptDraftResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/script/confirmations",
    response_model=VideoEpisodeScriptConfirmationResponse,
    status_code=201,
)
async def prepare_video_episode_script_confirmation(
    episode_id: str,
    body: PrepareVideoEpisodeScriptConfirmationRequest,
    user: User,
) -> VideoEpisodeScriptConfirmationResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/script/confirmations/{artifact_id}",
    response_model=VideoEpisodeScriptConfirmationResponse,
    status_code=200,
)
async def get_video_episode_script_confirmation(
    episode_id: str,
    artifact_id: str,
    user: User,
) -> VideoEpisodeScriptConfirmationResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/script/confirmations/{artifact_id}/approve",
    response_model=VideoEpisodeScriptVersionResponse,
    status_code=201,
)
async def approve_video_episode_script_confirmation(
    episode_id: str,
    artifact_id: str,
    body: ApproveVideoEpisodeScriptConfirmationRequest,
    user: User,
) -> VideoEpisodeScriptVersionResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/script/versions",
    response_model=VideoEpisodeScriptVersionListResponse,
    status_code=200,
)
async def list_video_episode_script_versions(
    episode_id: str,
    user: User,
) -> VideoEpisodeScriptVersionListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/script/versions/{version_id}",
    response_model=VideoEpisodeScriptVersionResponse,
    status_code=200,
)
async def get_video_episode_script_version(
    episode_id: str,
    version_id: str,
    user: User,
) -> VideoEpisodeScriptVersionResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/commands/{client_request_id}",
    response_model=VideoEpisodeCommandResponse,
    status_code=200,
)
async def get_video_episode_command(
    episode_id: str,
    client_request_id: str,
    user: User,
) -> VideoEpisodeCommandResponse:
    _java_runtime_only()


@router.get(
    "/projects/{project_id}/episode-commands/{client_request_id}",
    response_model=VideoEpisodeCommandResponse,
)
async def get_video_project_episode_command(
    project_id: str,
    client_request_id: str,
    user: User,
) -> VideoEpisodeCommandResponse:
    _java_runtime_only()

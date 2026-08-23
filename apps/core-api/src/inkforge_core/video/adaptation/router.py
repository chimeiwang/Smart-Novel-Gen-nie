"""浏览器可访问的章节影视化 v2 公共接口。"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .schemas import (
    ApproveVisualCanonRequest,
    ChapterAdaptationListResponse,
    ChapterAdaptationResponse,
    ChapterAdaptationTaskAcceptedResponse,
    ConfirmAdaptationPlanRequest,
    CreateChapterAdaptationRequest,
    CreateVisualCanonCandidateRequest,
    DiscardAdaptationCandidateRequest,
    SaveEpisodePlanRequest,
    SaveShotPromptRequest,
    SaveShotVisualReferencesRequest,
    ShotVisualReferenceSetResponse,
    StartPromptRunRequest,
    StartShotPlanRunRequest,
    VisualCanonLibraryResponse,
    VisualCanonResponse,
)
from .service import VideoAdaptationService

router = APIRouter(prefix="/video", tags=["章节影视化"])


def get_video_adaptation_service(request: Request) -> VideoAdaptationService:
    service = cast(
        VideoAdaptationService | None,
        getattr(request.app.state, "video_adaptation_service", None),
    )
    if service is None:
        raise ApiError(
            status_code=503,
            code="VIDEO_SERVICE_UNAVAILABLE",
            message="章节影视化服务暂时不可用",
        )
    return service


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[VideoAdaptationService, Depends(get_video_adaptation_service)]


@router.post(
    "/projects/{project_id}/chapter-adaptations",
    response_model=ChapterAdaptationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_adaptation(
    project_id: str,
    body: CreateChapterAdaptationRequest,
    user: User,
    service: Service,
) -> ChapterAdaptationResponse:
    return await service.create_adaptation(user.id, project_id, body)


@router.get(
    "/projects/{project_id}/chapter-adaptations",
    response_model=ChapterAdaptationListResponse,
)
async def list_adaptations(
    project_id: str,
    user: User,
    service: Service,
) -> ChapterAdaptationListResponse:
    return await service.list_adaptations(user.id, project_id)


@router.get(
    "/projects/{project_id}/visual-canons",
    response_model=VisualCanonLibraryResponse,
)
async def list_visual_canons(
    project_id: str,
    user: User,
    service: Service,
) -> VisualCanonLibraryResponse:
    return await service.list_visual_canons(user.id, project_id)


@router.post(
    "/projects/{project_id}/visual-canons",
    response_model=VisualCanonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def set_visual_canon_candidate(
    project_id: str,
    body: CreateVisualCanonCandidateRequest,
    user: User,
    service: Service,
) -> VisualCanonResponse:
    return await service.set_visual_canon_candidate(user.id, project_id, body)


@router.post(
    "/visual-canons/{canon_id}/approve",
    response_model=VisualCanonResponse,
)
async def approve_visual_canon(
    canon_id: str,
    body: ApproveVisualCanonRequest,
    user: User,
    service: Service,
) -> VisualCanonResponse:
    return await service.approve_visual_canon(user.id, canon_id, body)


@router.get(
    "/chapter-adaptations/{adaptation_id}",
    response_model=ChapterAdaptationResponse,
)
async def get_adaptation(
    adaptation_id: str,
    user: User,
    service: Service,
) -> ChapterAdaptationResponse:
    return await service.get_adaptation(user.id, adaptation_id)


@router.post(
    "/chapter-adaptations/{adaptation_id}/shot-plan-runs",
    response_model=ChapterAdaptationTaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_shot_plan(
    adaptation_id: str,
    body: StartShotPlanRunRequest,
    user: User,
    service: Service,
) -> ChapterAdaptationTaskAcceptedResponse:
    return await service.start_plan(user.id, adaptation_id, body)


@router.post(
    "/chapter-adaptations/{adaptation_id}/shot-plan/confirm",
    response_model=ChapterAdaptationResponse,
)
async def confirm_shot_plan(
    adaptation_id: str,
    body: ConfirmAdaptationPlanRequest,
    user: User,
    service: Service,
) -> ChapterAdaptationResponse:
    return await service.confirm_plan(user.id, adaptation_id, body)


@router.post(
    "/chapter-adaptations/{adaptation_id}/candidate/discard",
    response_model=ChapterAdaptationResponse,
)
async def discard_candidate(
    adaptation_id: str,
    body: DiscardAdaptationCandidateRequest,
    user: User,
    service: Service,
) -> ChapterAdaptationResponse:
    return await service.discard_candidate(user.id, adaptation_id, body)


@router.put(
    "/chapter-adaptations/{adaptation_id}/episode-plan",
    response_model=ChapterAdaptationResponse,
)
async def save_episode_plan(
    adaptation_id: str,
    body: SaveEpisodePlanRequest,
    user: User,
    service: Service,
) -> ChapterAdaptationResponse:
    return await service.save_episode_plan(user.id, adaptation_id, body)


@router.post(
    "/chapter-adaptations/{adaptation_id}/prompt-runs",
    response_model=ChapterAdaptationTaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_prompt_run(
    adaptation_id: str,
    body: StartPromptRunRequest,
    user: User,
    service: Service,
) -> ChapterAdaptationTaskAcceptedResponse:
    return await service.start_prompts(user.id, adaptation_id, body)


@router.put(
    "/chapter-adaptations/{adaptation_id}/shots/{shot_id}/prompt",
    response_model=ChapterAdaptationResponse,
)
async def save_shot_prompt(
    adaptation_id: str,
    shot_id: str,
    body: SaveShotPromptRequest,
    user: User,
    service: Service,
) -> ChapterAdaptationResponse:
    return await service.save_prompt(user.id, adaptation_id, shot_id, body)


@router.put(
    "/chapter-adaptations/{adaptation_id}/shots/{shot_id}/visual-references",
    response_model=ShotVisualReferenceSetResponse,
)
async def save_shot_visual_references(
    adaptation_id: str,
    shot_id: str,
    body: SaveShotVisualReferencesRequest,
    user: User,
    service: Service,
) -> ShotVisualReferenceSetResponse:
    return await service.save_shot_visual_references(
        user.id,
        adaptation_id,
        shot_id,
        body,
    )

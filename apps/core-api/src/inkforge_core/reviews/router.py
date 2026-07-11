from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .repository import ReviewRepository
from .schemas import (
    ArtifactDecisionResponse,
    ReviewArtifactDecisionRequest,
    ReviewArtifactResponse,
)
from .service import ReviewService

router = APIRouter(tags=["待审核草案"])


def get_review_service(request: Request) -> ReviewService:
    service = cast(ReviewService | None, getattr(request.app.state, "review_service", None))
    if service is None:
        raise ApiError(
            status_code=503,
            code="REVIEW_SERVICE_UNAVAILABLE",
            message="草案审核服务暂时不可用",
        )
    return service


def get_review_repository(request: Request) -> ReviewRepository:
    repository = cast(
        ReviewRepository | None,
        getattr(request.app.state, "review_repository", None),
    )
    if repository is None:
        raise ApiError(
            status_code=503,
            code="REVIEW_SERVICE_UNAVAILABLE",
            message="草案审核服务暂时不可用",
        )
    return repository


User = Annotated[AuthUser, Depends(get_current_user)]
Service = Annotated[ReviewService, Depends(get_review_service)]
Repository = Annotated[ReviewRepository, Depends(get_review_repository)]


@router.get("/review-artifacts/{artifact_id}", response_model=ReviewArtifactResponse)
async def get_review_artifact(
    artifact_id: str, user: User, repository: Repository
) -> ReviewArtifactResponse:
    return await repository.get_response(user.id, artifact_id)


@router.get(
    "/writing/tasks/{task_id}/artifact",
    response_model=ReviewArtifactResponse | None,
)
async def get_task_review_artifact(
    task_id: str, user: User, repository: Repository
) -> ReviewArtifactResponse | None:
    return await repository.get_task_artifact(user.id, task_id)


@router.post(
    "/review-artifacts/{artifact_id}/decision",
    response_model=ArtifactDecisionResponse,
)
async def decide_review_artifact(
    artifact_id: str,
    body: ReviewArtifactDecisionRequest,
    user: User,
    service: Service,
) -> ArtifactDecisionResponse:
    refs = (
        [item.model_dump(exclude_none=True) for item in body.selectedUpdateRefs]
        if body.selectedUpdateRefs is not None
        else None
    )
    return await service.decide(
        user.id,
        artifact_id,
        body.decision,
        edited_content=body.editedContent,
        selected_update_refs=refs,
    )

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request, status

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .decision_orchestrator import ReviewDecisionOrchestrator
from .repository import ReviewRepository
from .schemas import (
    ArtifactDecisionAcceptedResponse,
    ReviewArtifactDecisionRequest,
    ReviewArtifactResponse,
)

router = APIRouter(tags=["待审核草案"])


def get_review_decision_orchestrator(request: Request) -> ReviewDecisionOrchestrator:
    orchestrator = cast(
        ReviewDecisionOrchestrator | None,
        getattr(request.app.state, "review_decision_orchestrator", None),
    )
    if orchestrator is None:
        raise ApiError(
            status_code=503,
            code="REVIEW_SERVICE_UNAVAILABLE",
            message="草案审核服务暂时不可用",
        )
    return orchestrator


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
DecisionOrchestrator = Annotated[
    ReviewDecisionOrchestrator, Depends(get_review_decision_orchestrator)
]
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
    response_model=ArtifactDecisionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def decide_review_artifact(
    artifact_id: str,
    body: ReviewArtifactDecisionRequest,
    user: User,
    orchestrator: DecisionOrchestrator,
) -> ArtifactDecisionAcceptedResponse:
    return await orchestrator.decide(user.id, artifact_id, body)

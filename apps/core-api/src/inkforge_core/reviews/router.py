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
    RestoreArtifactRevisionRequest,
    ReviewArtifactDecisionRequest,
    ReviewArtifactResponse,
    ReviewArtifactRevisionDetail,
    ReviewArtifactRevisionSummary,
    SaveShortStoryOutlineRequest,
    ShortStoryArtifactsResponse,
    ShortStoryVersionDetail,
    ShortStoryVersionListItem,
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


@router.get(
    "/novels/{novel_id}/short-story/artifacts",
    response_model=ShortStoryArtifactsResponse,
)
async def get_short_story_artifacts(
    novel_id: str,
    user: User,
    repository: Repository,
) -> ShortStoryArtifactsResponse:
    return await repository.get_short_story_artifacts(user.id, novel_id)


@router.get(
    "/novels/{novel_id}/short-story/versions",
    response_model=list[ShortStoryVersionListItem],
)
async def list_short_story_versions(
    novel_id: str,
    user: User,
    repository: Repository,
) -> list[ShortStoryVersionListItem]:
    return await repository.list_short_story_versions(user.id, novel_id)


@router.get(
    "/novels/{novel_id}/short-story/versions/{kind}/{revision}",
    response_model=ShortStoryVersionDetail,
)
async def get_short_story_version(
    novel_id: str,
    kind: str,
    revision: int,
    user: User,
    repository: Repository,
) -> ShortStoryVersionDetail:
    return await repository.get_short_story_version(user.id, novel_id, kind, revision)


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


@router.get(
    "/review-artifacts/{artifact_id}/revisions",
    response_model=list[ReviewArtifactRevisionSummary],
)
async def list_review_artifact_revisions(
    artifact_id: str, user: User, repository: Repository
) -> list[ReviewArtifactRevisionSummary]:
    return await repository.list_revisions(user.id, artifact_id)


@router.get(
    "/review-artifacts/{artifact_id}/revisions/{revision}",
    response_model=ReviewArtifactRevisionDetail,
)
async def get_review_artifact_revision(
    artifact_id: str,
    revision: int,
    user: User,
    repository: Repository,
) -> ReviewArtifactRevisionDetail:
    return await repository.get_revision(user.id, artifact_id, revision)


@router.post(
    "/review-artifacts/{artifact_id}/revisions/{revision}/restore",
    response_model=ReviewArtifactResponse,
)
async def restore_review_artifact_revision(
    artifact_id: str,
    revision: int,
    body: RestoreArtifactRevisionRequest,
    user: User,
    repository: Repository,
) -> ReviewArtifactResponse:
    return await repository.restore_revision(
        user.id,
        artifact_id,
        revision,
        expected_revision=body.expectedRevision,
    )


@router.put(
    "/review-artifacts/{artifact_id}/outline",
    response_model=ReviewArtifactResponse,
)
async def save_short_story_outline(
    artifact_id: str,
    body: SaveShortStoryOutlineRequest,
    user: User,
    repository: Repository,
) -> ReviewArtifactResponse:
    return await repository.save_short_story_outline(user.id, artifact_id, body)


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

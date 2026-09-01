from __future__ import annotations

import hashlib
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from ..auth.dependencies import get_current_user
from ..auth.repository import AuthUser
from ..errors import ApiError
from .decision_orchestrator import ReviewDecisionOrchestrator
from .repository import ReviewRepository
from .schemas import (
    ArtifactDecisionPublicResponse,
    ReviewArtifactDecisionRequest,
    ReviewArtifactListResponse,
    ReviewArtifactResponse,
    ReviewArtifactSummaryListResponse,
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


@router.get("/review-artifacts", response_model=ReviewArtifactListResponse)
async def list_review_artifacts(
    user: User,
    repository: Repository,
    novelId: str = Query(min_length=1, max_length=256),
    chapterId: str | None = Query(default=None, min_length=1, max_length=256),
    taskId: str | None = Query(default=None, min_length=1, max_length=256),
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    cursor: str | None = Query(default=None, min_length=1, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
) -> ReviewArtifactListResponse:
    items, next_cursor = await repository.list_artifacts(
        user.id,
        novel_id=novelId,
        chapter_id=chapterId,
        task_id=taskId,
        status=status,
        kind=kind,
        cursor=cursor,
        limit=limit,
    )
    return ReviewArtifactListResponse(items=items, nextCursor=next_cursor)


@router.get(
    "/review-artifact-summaries",
    response_model=ReviewArtifactSummaryListResponse,
)
async def list_review_artifact_summaries(
    user: User,
    repository: Repository,
    novelId: str = Query(min_length=1, max_length=256),
    chapterId: str | None = Query(default=None, min_length=1, max_length=256),
    taskId: str | None = Query(default=None, min_length=1, max_length=256),
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    cursor: str | None = Query(default=None, min_length=1, max_length=512),
    limit: int = Query(default=50, ge=1, le=100),
) -> ReviewArtifactSummaryListResponse:
    items, next_cursor = await repository.list_artifact_summaries(
        user.id,
        novel_id=novelId,
        chapter_id=chapterId,
        task_id=taskId,
        status=status,
        kind=kind,
        cursor=cursor,
        limit=limit,
    )
    return ReviewArtifactSummaryListResponse(items=items, nextCursor=next_cursor)


@router.get(
    "/review-artifacts/{artifact_id}",
    response_model=ReviewArtifactResponse,
    responses={
        200: {
            "headers": {
                "ETag": {
                    "schema": {"type": "string"},
                    "description": "artifactId、精确 revision 与权威状态共同生成的强 ETag",
                }
            }
        },
        304: {"description": "精确 revision 详情与 If-None-Match 一致"},
    },
)
async def get_review_artifact(
    artifact_id: str,
    response: Response,
    user: User,
    repository: Repository,
    revision: int | None = Query(default=None, ge=1),
    if_none_match: str | None = Header(default=None, alias="If-None-Match"),
) -> ReviewArtifactResponse | Response:
    artifact = await repository.get_response(user.id, artifact_id, revision)
    etag = _artifact_etag(artifact)
    if _etag_matches(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return artifact


def _artifact_etag(artifact: ReviewArtifactResponse) -> str:
    identity = (
        f"{artifact.id}:{artifact.revision}:"
        f"{artifact.status}:{artifact.updatedAt.isoformat()}"
    )
    return f'"{hashlib.sha256(identity.encode()).hexdigest()}"'


def _etag_matches(candidate: str | None, expected: str) -> bool:
    if candidate is None:
        return False
    return any(
        value == "*" or value.removeprefix("W/") == expected
        for value in (item.strip() for item in candidate.split(","))
    )


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
    response_model=ArtifactDecisionPublicResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def decide_review_artifact(
    artifact_id: str,
    body: ReviewArtifactDecisionRequest,
    user: User,
    orchestrator: DecisionOrchestrator,
) -> ArtifactDecisionPublicResponse:
    return await orchestrator.decide(user.id, artifact_id, body)

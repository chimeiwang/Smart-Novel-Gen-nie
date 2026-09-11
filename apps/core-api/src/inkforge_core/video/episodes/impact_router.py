"""Java Core 跨集影响复核公共 OpenAPI 的唯一来源。"""

from __future__ import annotations

from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, Query

from ...auth.dependencies import get_current_user
from ...auth.repository import AuthUser
from ...errors import ApiError
from .impact_schemas import (
    DecideVideoImpactReviewRequest,
    VideoImpactReviewListResponse,
    VideoImpactReviewResponse,
)

router = APIRouter(prefix="/video", tags=["VideoEpisodeImpact"])
User = Annotated[AuthUser, Depends(get_current_user)]


def _java_runtime_only() -> NoReturn:
    raise ApiError(
        status_code=503,
        code="JAVA_CORE_REQUIRED",
        message="独立剧集影响复核由 Java Core 提供服务",
    )


@router.get(
    "/episodes/{episode_id}/impact-reviews",
    response_model=VideoImpactReviewListResponse,
)
async def list_video_impact_reviews(
    episode_id: str,
    user: User,
    status: Annotated[Literal["pending", "resolved"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    beforeReviewId: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
) -> VideoImpactReviewListResponse:
    _java_runtime_only()


@router.get(
    "/episodes/{episode_id}/impact-reviews/{review_id}",
    response_model=VideoImpactReviewResponse,
)
async def get_video_impact_review(
    episode_id: str,
    review_id: str,
    user: User,
) -> VideoImpactReviewResponse:
    _java_runtime_only()


@router.post(
    "/episodes/{episode_id}/impact-reviews/{review_id}/decisions",
    response_model=VideoImpactReviewResponse,
)
async def decide_video_impact_review(
    episode_id: str,
    review_id: str,
    body: DecideVideoImpactReviewRequest,
    user: User,
) -> VideoImpactReviewResponse:
    _java_runtime_only()

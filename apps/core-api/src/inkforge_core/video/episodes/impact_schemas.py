"""独立剧集跨版本影响复核的公共 API 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .schemas import ClientRequestId, Identifier, VideoEpisodeApiModel


class VideoImpactStateSnapshot(VideoEpisodeApiModel):
    key: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2_000)
    narrativeTime: str = Field(max_length=400)
    entityIds: list[Identifier] = Field(default_factory=list, max_length=100)


class VideoImpactReviewItem(VideoEpisodeApiModel):
    itemId: Identifier
    dependencyId: Identifier
    kind: Literal["direct_dependency_changed"]
    changeType: Literal["changed", "removed"]
    producerStateKey: str = Field(min_length=1, max_length=160)
    beforeState: VideoImpactStateSnapshot
    afterState: VideoImpactStateSnapshot | None
    consumerSceneId: Identifier
    consumerLineId: Identifier | None
    narrativeTime: str = Field(min_length=1, max_length=400)
    description: str = Field(min_length=1, max_length=2_000)
    beforeStateHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    afterStateHash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    itemHash: str = Field(pattern=r"^[0-9a-f]{64}$")


class VideoImpactReviewReport(VideoEpisodeApiModel):
    schemaVersion: Literal["video-impact-review/1.0"]
    kind: Literal["explicit_dependency_changed"]
    requiresAuthorReview: Literal[True]
    producerEpisodeId: Identifier
    beforeScriptVersionId: Identifier
    afterScriptVersionId: Identifier
    targetEpisodeId: Identifier
    targetScriptVersionId: Identifier
    producerProductionRevision: int = Field(ge=1)
    targetProductionRevision: int = Field(ge=1)
    producerBaselineId: Identifier | None
    targetBaselineId: Identifier | None
    items: list[VideoImpactReviewItem] = Field(min_length=1, max_length=500)


class VideoImpactDecision(VideoEpisodeApiModel):
    itemId: Identifier
    action: Literal["keep_existing", "revise_target", "not_applicable", "defer"]
    note: str = Field(default="", max_length=4_000)

    @model_validator(mode="after")
    def validate_evidence_note(self) -> VideoImpactDecision:
        if self.action != "defer" and not self.note.strip():
            raise ValueError("完成影响项必须记录作者判断依据或修改安排")
        return self


class DecideVideoImpactReviewRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    decisions: list[VideoImpactDecision] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_items(self) -> DecideVideoImpactReviewRequest:
        item_ids = [decision.itemId for decision in self.decisions]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("同一影响项不能重复决定")
        return self


class VideoImpactReviewSummaryResponse(VideoEpisodeApiModel):
    id: str
    projectId: str
    producerEpisodeId: str
    beforeScriptVersionId: str
    afterScriptVersionId: str
    targetEpisodeId: str
    targetScriptVersionId: str
    producerProductionRevision: int
    targetProductionRevision: int
    producerBaselineId: str | None
    targetBaselineId: str | None
    revision: int
    status: Literal["pending", "resolved"]
    itemCount: int = Field(ge=1)
    decisionCount: int = Field(ge=0)
    isStale: bool
    staleReasons: list[str]
    createdAt: datetime
    updatedAt: datetime


class VideoImpactReviewResponse(VideoImpactReviewSummaryResponse):
    report: VideoImpactReviewReport
    decisions: list[VideoImpactDecision]


class VideoImpactReviewListResponse(VideoEpisodeApiModel):
    reviews: list[VideoImpactReviewSummaryResponse]
    nextBeforeReviewId: str | None

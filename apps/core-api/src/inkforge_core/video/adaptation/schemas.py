"""浏览器可见的章节影视化 v2 API 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterPacingPreset,
    FormalChapterAdaptationPlan,
    SeedanceShotPromptSpec,
)
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ClientRequestId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=16, max_length=128),
]


class VideoAdaptationApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateChapterAdaptationRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    chapterId: str = Field(min_length=1)
    expectedChapterUpdatedAt: datetime


class StartShotPlanRunRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    pacingPreset: ChapterPacingPreset = "short_drama"
    targetEpisodeSeconds: Literal[60, 90, 120] = 90


class ConfirmAdaptationPlanRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    expectedArtifactRevision: int = Field(ge=1)
    expectedAdaptationRevision: int = Field(ge=1)
    plan: ChapterAdaptationPlanCandidate


class DiscardAdaptationCandidateRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    expectedArtifactRevision: int = Field(ge=1)
    expectedAdaptationRevision: int = Field(ge=1)


class SaveEpisodePlanRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    expectedAdaptationRevision: int = Field(ge=1)
    shotPlanVersionId: str = Field(min_length=1)
    breakAfterShotIds: list[str] = Field(default_factory=list, max_length=119)


class StartPromptRunRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    expectedAdaptationRevision: int = Field(ge=1)
    shotPlanVersionId: str = Field(min_length=1)
    shotIds: list[str] = Field(default_factory=list, max_length=120)

    @model_validator(mode="after")
    def validate_unique_shots(self) -> StartPromptRunRequest:
        if len(set(self.shotIds)) != len(self.shotIds):
            raise ValueError("逐镜提示词目标不能重复")
        return self


class SaveShotPromptRequest(VideoAdaptationApiModel):
    expectedPromptRevision: int = Field(ge=1)
    candidateTaskId: str | None = Field(default=None, min_length=1)
    currentPrompt: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
    ]


class ChapterAdaptationTaskResponse(VideoAdaptationApiModel):
    id: str
    jobId: str
    kind: Literal["shot_plan", "shot_prompt"]
    workflow: str
    status: str
    checkpointStage: str
    lastErrorCode: str | None
    lastErrorMessage: str | None
    createdAt: datetime
    updatedAt: datetime


class ChapterAdaptationReviewSummary(VideoAdaptationApiModel):
    id: str
    status: str
    revision: int
    title: str | None
    summary: str | None


class EpisodePlanResponse(VideoAdaptationApiModel):
    id: str
    versionNo: int
    shotPlanVersionId: str
    breakAfterShotIds: list[str]


class ShotPromptVersionResponse(VideoAdaptationApiModel):
    id: str
    shotId: str
    shotKey: str
    versionNo: int
    generatedText: str | None
    currentText: str
    promptEdited: bool
    headRevision: int
    createdAt: datetime


class ShotPromptCandidateResponse(VideoAdaptationApiModel):
    taskId: str
    shotId: str
    shotKey: str
    spec: SeedanceShotPromptSpec
    compiledPrompt: str


class ChapterAdaptationResponse(VideoAdaptationApiModel):
    id: str
    projectId: str
    novelId: str
    chapterId: str | None
    chapterTitle: str
    chapterUpdatedAt: datetime
    sourceText: str
    sourceHash: str
    lifecycleStatus: str
    headRevision: int
    state: Literal["empty", "generating", "awaiting_review", "approved", "failed"]
    currentPlan: FormalChapterAdaptationPlan | None
    candidatePlan: ChapterAdaptationPlanCandidate | None
    episodePlan: EpisodePlanResponse | None
    promptVersions: list[ShotPromptVersionResponse]
    promptCandidates: list[ShotPromptCandidateResponse]
    reviewArtifact: ChapterAdaptationReviewSummary | None
    latestTask: ChapterAdaptationTaskResponse | None
    createdAt: datetime


class ChapterAdaptationListResponse(VideoAdaptationApiModel):
    adaptations: list[ChapterAdaptationResponse]


class ChapterAdaptationTaskAcceptedResponse(VideoAdaptationApiModel):
    adaptation: ChapterAdaptationResponse
    task: ChapterAdaptationTaskResponse

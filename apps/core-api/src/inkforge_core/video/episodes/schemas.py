"""独立分集、来源、剧本工作稿及人工确认的公共 API 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from inkforge_contracts.video_episode import (
    VideoEpisodeDependencyInput,
    VideoEpisodeScriptDocument,
    VideoEpisodeScriptReview,
    VideoEpisodeScriptReviewFinding,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

ClientRequestId = Annotated[str, Field(min_length=16, max_length=128)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]


class VideoEpisodeApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateVideoEpisodeRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    title: str = Field(min_length=1, max_length=240)
    creativeIntent: str = Field(default="", max_length=4_000)
    targetDurationSeconds: int | None = Field(default=None, ge=1, le=86_400)


class UpdateVideoEpisodeRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    creativeIntent: str | None = Field(default=None, max_length=4_000)
    targetDurationSeconds: int | None = Field(default=None, ge=1, le=86_400)


class ReorderVideoEpisodesRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedProjectRevision: int = Field(ge=1)
    episodeIds: list[Identifier] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def validate_order(self) -> ReorderVideoEpisodesRequest:
        if len(self.episodeIds) != len(set(self.episodeIds)):
            raise ValueError("分集排序不能包含重复身份")
        return self


class VideoEpisodeResponse(VideoEpisodeApiModel):
    id: str
    projectId: str
    novelId: str
    title: str
    creativeIntent: str
    targetDurationSeconds: int | None
    order: int
    revision: int
    currentSourceSetVersionId: str | None
    currentScriptVersionId: str | None
    currentStoryboardVersionId: str | None
    currentProductionBaselineId: str | None
    productionRevision: int
    latestDeliveryVersionId: str | None
    deliveryRevision: int = Field(ge=1)
    createdAt: datetime
    updatedAt: datetime


class VideoEpisodeListResponse(VideoEpisodeApiModel):
    projectId: str
    projectRevision: int
    episodes: list[VideoEpisodeResponse]


class VideoEpisodeSourceRange(VideoEpisodeApiModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> VideoEpisodeSourceRange:
        if self.end <= self.start:
            raise ValueError("取材范围必须是非空 Unicode 码点半开区间")
        return self


class VideoEpisodeSourceSelection(VideoEpisodeApiModel):
    chapterId: Identifier
    expectedUpdatedAt: datetime
    sourceHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ranges: list[VideoEpisodeSourceRange] = Field(min_length=1, max_length=100)


class CreateVideoEpisodeSourceSetRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    basedOnVersionId: Identifier | None = None
    sources: list[VideoEpisodeSourceSelection] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_sources(self) -> CreateVideoEpisodeSourceSetRequest:
        chapter_ids = [source.chapterId for source in self.sources]
        if len(chapter_ids) != len(set(chapter_ids)):
            raise ValueError("同一章节的多段取材应合并到该章节 ranges 中")
        return self


class VideoEpisodeSourceSnapshotResponse(VideoEpisodeApiModel):
    id: str
    chapterId: str
    chapterTitle: str
    chapterUpdatedAt: datetime
    sourceText: str
    sourceHash: str
    ranges: list[VideoEpisodeSourceRange]
    sourceStatus: Literal["current", "updated", "missing", "unknown"] = "unknown"
    currentChapterUpdatedAt: datetime | None = None
    currentChapterContentHash: str | None = None


class VideoEpisodeSourceSetResponse(VideoEpisodeApiModel):
    id: str
    episodeId: str
    versionNo: int
    basedOnVersionId: str | None
    contentHash: str
    sources: list[VideoEpisodeSourceSnapshotResponse]
    createdAt: datetime


class VideoEpisodeSourceSetListResponse(VideoEpisodeApiModel):
    sourceSets: list[VideoEpisodeSourceSetResponse]


class SaveVideoEpisodeScriptDraftRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    sourceSetVersionId: Identifier | None
    baseScriptVersionId: Identifier | None
    document: VideoEpisodeScriptDocument


class VideoEpisodeScriptDraftResponse(VideoEpisodeApiModel):
    episodeId: str
    revision: int
    sourceSetVersionId: str | None
    baseScriptVersionId: str | None
    document: VideoEpisodeScriptDocument
    adoptedArtifactId: str | None
    nodeIdMappings: dict[str, str] = Field(default_factory=dict)
    updatedAt: datetime


class VideoEpisodeScriptCandidateResponse(VideoEpisodeApiModel):
    artifactId: str
    workflowRunId: str
    episodeId: str
    revision: int
    status: Literal["draft", "awaiting_user", "applied", "rejected"]
    title: str
    summary: str | None
    expectedDraftRevision: int
    sourceSetVersionId: str | None
    baseScriptVersionId: str | None
    document: VideoEpisodeScriptDocument
    reviewFindings: list[VideoEpisodeScriptReviewFinding] = Field(default_factory=list)
    review: VideoEpisodeScriptReview | None = None
    createdAt: datetime


class StartVideoEpisodeScriptRunRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedDraftRevision: int = Field(ge=1)
    operation: Literal["episode_script_generate", "episode_script_revise"]
    selectedSceneIds: list[Identifier] = Field(default_factory=list, max_length=60)
    instruction: str = Field(min_length=1, max_length=8_000)

    @model_validator(mode="after")
    def validate_scope(self) -> StartVideoEpisodeScriptRunRequest:
        if len(self.selectedSceneIds) != len(set(self.selectedSceneIds)):
            raise ValueError("剧本修订范围不能重复")
        if self.operation == "episode_script_generate" and self.selectedSceneIds:
            raise ValueError("起草操作不能携带局部修订范围")
        if self.operation == "episode_script_revise" and not self.selectedSceneIds:
            raise ValueError("修订必须明确选择至少一个稳定场次")
        return self


class VideoEpisodeScriptRunResponse(VideoEpisodeApiModel):
    runId: str
    episodeId: str
    status: str
    artifactId: str | None
    errorCode: str | None
    errorMessage: str | None
    createdAt: datetime
    updatedAt: datetime


class AdoptVideoEpisodeScriptCandidateRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedArtifactRevision: int = Field(ge=1)
    expectedDraftRevision: int = Field(ge=1)


class PrepareVideoEpisodeScriptConfirmationRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedDraftRevision: int = Field(ge=1)
    expectedEpisodeRevision: int = Field(ge=1)


class VideoEpisodeScriptConfirmationResponse(VideoEpisodeApiModel):
    artifactId: str
    artifactRevision: int
    episodeId: str
    episodeRevision: int
    draftRevision: int
    sourceSetVersionId: str | None
    document: VideoEpisodeScriptDocument
    confirmationHash: str
    createdAt: datetime


class ApproveVideoEpisodeScriptConfirmationRequest(VideoEpisodeApiModel):
    clientRequestId: ClientRequestId
    expectedArtifactRevision: int = Field(ge=1)
    expectedDraftRevision: int = Field(ge=1)
    expectedEpisodeRevision: int = Field(ge=1)
    confirmationHash: str = Field(pattern=r"^[0-9a-f]{64}$")


class VideoEpisodeScriptVersionResponse(VideoEpisodeApiModel):
    id: str
    episodeId: str
    versionNo: int
    basedOnVersionId: str | None
    sourceSetVersionId: str | None
    document: VideoEpisodeScriptDocument
    contentHash: str
    confirmationArtifactId: str
    createdAt: datetime


class VideoEpisodeScriptVersionListResponse(VideoEpisodeApiModel):
    versions: list[VideoEpisodeScriptVersionResponse]


class VideoEpisodeDependencyResponse(VideoEpisodeDependencyInput):
    id: str
    consumerEpisodeId: str
    consumerScriptVersionId: str
    producerStateHash: str


class VideoEpisodeDetailResponse(VideoEpisodeApiModel):
    episode: VideoEpisodeResponse
    sourceSets: list[VideoEpisodeSourceSetResponse]
    scriptDraft: VideoEpisodeScriptDraftResponse
    currentScriptVersion: VideoEpisodeScriptVersionResponse | None
    scriptVersions: list[VideoEpisodeScriptVersionResponse]
    candidateArtifacts: list[VideoEpisodeScriptCandidateResponse]
    latestScriptRun: VideoEpisodeScriptRunResponse | None = None
    dependencies: list[VideoEpisodeDependencyResponse]


class VideoEpisodeCommandResponse(VideoEpisodeApiModel):
    clientRequestId: str
    episodeId: str | None
    operation: str
    resultType: Literal[
        "episode",
        "episode_list",
        "source_set",
        "script_draft",
        "script_confirmation",
        "script_version",
        "script_run",
        "storyboard_draft",
        "storyboard_confirmation",
        "storyboard_version",
        "storyboard_run",
        "take_adoption",
        "production_baseline",
    ]
    resultId: str
    resultRevision: int | None
    createdAt: datetime

"""浏览器可见的章节影视化 v2 API 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from inkforge_contracts.video_adaptation import (
    ChapterAdaptationPlanCandidate,
    ChapterPacingPreset,
    FormalChapterAdaptationPlan,
    SeedanceShotPromptSpec,
    ShotVisualReferenceSnapshot,
    VisualCanonDuty,
    VisualSettingKind,
)
from inkforge_contracts.video_render import (
    RenderResolution,
    VideoShotRenderManifest,
)
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ..schemas import VideoAssetResponse

ClientRequestId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=16, max_length=128),
]
ShotRenderTaskStatus = Literal[
    "pending",
    "submitting",
    "submission_unknown",
    "queued",
    "running",
    "archiving",
    "succeeded",
    "failed",
    "expired",
    "cancelled",
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
    baseShotPlanVersionId: str | None = Field(default=None, min_length=1)
    revisionBrief: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=1_200),
    ] = None

    @model_validator(mode="after")
    def validate_revision(self) -> StartShotPlanRunRequest:
        if self.revisionBrief is not None and self.baseShotPlanVersionId is None:
            raise ValueError("没有正式镜头方案基线时不能提交修订重点")
        return self


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


class CreateVisualCanonCandidateRequest(VideoAdaptationApiModel):
    """把已上传且已确认权利的图片放入一个视觉设定槽的候选位置。"""

    clientRequestId: ClientRequestId
    settingKind: VisualSettingKind
    settingId: str = Field(min_length=1)
    duty: VisualCanonDuty
    variantKey: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    label: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    ]
    candidateAssetId: str = Field(min_length=1)
    includeFeatures: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    ] = Field(default_factory=list, max_length=20)
    excludeFeatures: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    ] = Field(default_factory=list, max_length=20)
    defaultStrength: int = Field(default=70, ge=1, le=100)

    @model_validator(mode="after")
    def validate_candidate(self) -> CreateVisualCanonCandidateRequest:
        expected_kind = {
            "identity": "character",
            "costume": "character",
            "scene": "location",
            "prop": "item",
        }[self.duty]
        if self.settingKind != expected_kind:
            raise ValueError("视觉设定职责与文字设定类型不匹配")
        if len(set(self.includeFeatures)) != len(self.includeFeatures):
            raise ValueError("包含特征不能重复")
        if len(set(self.excludeFeatures)) != len(self.excludeFeatures):
            raise ValueError("排除特征不能重复")
        return self


class ApproveVisualCanonRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    candidateAssetId: str = Field(min_length=1)


class ShotVisualReferenceSelectionRequest(VideoAdaptationApiModel):
    canonVersionId: str = Field(min_length=1)
    strength: int = Field(ge=1, le=100)


class SaveShotVisualReferencesRequest(VideoAdaptationApiModel):
    expectedRevision: int = Field(ge=0)
    references: list[ShotVisualReferenceSelectionRequest] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_unique_versions(self) -> SaveShotVisualReferencesRequest:
        version_ids = [item.canonVersionId for item in self.references]
        if len(set(version_ids)) != len(version_ids):
            raise ValueError("同一镜头不能重复绑定同一视觉设定版本")
        return self


class StartShotRenderRequest(VideoAdaptationApiModel):
    """从镜头当前正式提示词创建一次显式、可能计费的视频任务。"""

    clientRequestId: ClientRequestId
    expectedPromptRevision: int = Field(ge=1)
    durationSeconds: int = Field(ge=2, le=12)
    resolution: RenderResolution = "720p"
    generateAudio: bool = True
    watermark: bool = False


class RetryShotRenderRequest(VideoAdaptationApiModel):
    """精确复制旧任务 manifest；不会自动采用后来修改的提示词或参考图。"""

    clientRequestId: ClientRequestId


class ConfirmShotTakeRequest(VideoAdaptationApiModel):
    clientRequestId: ClientRequestId
    expectedTakeRevision: int = Field(ge=1)


class ChapterAdaptationTaskResponse(VideoAdaptationApiModel):
    id: str
    jobId: str
    kind: Literal["shot_plan", "shot_prompt"]
    baseShotPlanVersionId: str | None
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


class VisualCanonVersionResponse(VideoAdaptationApiModel):
    id: str
    canonId: str
    versionNo: int
    asset: VideoAssetResponse
    settingName: str
    label: str
    includeFeatures: list[str]
    excludeFeatures: list[str]
    defaultStrength: int
    contentHash: str
    createdAt: datetime


class VisualCanonResponse(VideoAdaptationApiModel):
    id: str
    projectId: str
    novelId: str
    settingKind: VisualSettingKind
    settingId: str
    settingName: str
    duty: VisualCanonDuty
    variantKey: str
    label: str
    candidateAsset: VideoAssetResponse | None
    candidateIncludeFeatures: list[str]
    candidateExcludeFeatures: list[str]
    candidateDefaultStrength: int | None
    currentVersionId: str | None
    versions: list[VisualCanonVersionResponse]
    revision: int
    createdAt: datetime
    updatedAt: datetime


class VisualCanonLibraryResponse(VideoAdaptationApiModel):
    canons: list[VisualCanonResponse]


class ShotVisualReferenceSetResponse(VideoAdaptationApiModel):
    shotId: str
    shotKey: str
    revision: int = Field(ge=0)
    references: list[ShotVisualReferenceSnapshot]


class ShotPromptVersionResponse(VideoAdaptationApiModel):
    id: str
    shotId: str
    shotKey: str
    versionNo: int
    generatedText: str | None
    currentText: str
    promptEdited: bool
    visualReferences: list[ShotVisualReferenceSnapshot]
    headRevision: int
    createdAt: datetime


class ShotPromptCandidateResponse(VideoAdaptationApiModel):
    taskId: str
    shotId: str
    shotKey: str
    spec: SeedanceShotPromptSpec
    compiledPrompt: str
    visualReferences: list[ShotVisualReferenceSnapshot]
    qualityWarnings: list[str] = Field(default_factory=list, max_length=12)


class VideoRenderReadinessResponse(VideoAdaptationApiModel):
    configured: bool
    enabled: bool
    referenceTransportConfigured: bool
    model: str
    blockers: list[str] = Field(default_factory=list)


class ShotRenderTaskResponse(VideoAdaptationApiModel):
    id: str
    adaptationId: str
    shotId: str
    shotPlanVersionId: str
    promptVersionId: str
    retryOfTaskId: str | None
    provider: Literal["seedance"]
    model: str
    status: ShotRenderTaskStatus
    inputHash: str
    manifest: VideoShotRenderManifest
    providerTaskId: str | None
    pollCount: int
    attemptCount: int
    lastErrorCode: str | None
    lastErrorMessage: str | None
    createdAt: datetime
    updatedAt: datetime
    submittedAt: datetime | None
    completedAt: datetime | None


class ShotTakeResponse(VideoAdaptationApiModel):
    id: str
    taskId: str
    adaptationId: str
    shotId: str
    shotPlanVersionId: str
    promptVersionId: str
    takeNo: int
    provider: Literal["seedance"]
    model: str
    providerTaskId: str
    inputHash: str
    providerMetadata: dict[str, object]
    asset: VideoAssetResponse
    createdAt: datetime


class ShotTakeHeadResponse(VideoAdaptationApiModel):
    shotId: str
    currentTakeId: str | None
    revision: int
    updatedAt: datetime


class ChapterRenderWorkspaceResponse(VideoAdaptationApiModel):
    adaptationId: str
    readiness: VideoRenderReadinessResponse
    tasks: list[ShotRenderTaskResponse]
    takes: list[ShotTakeResponse]
    takeHeads: list[ShotTakeHeadResponse]


class ShotTakeDecisionResponse(VideoAdaptationApiModel):
    commandId: str
    status: Literal["succeeded", "conflict", "rejected"]
    shotId: str
    takeId: str
    currentTakeId: str | None
    resultingRevision: int | None
    errorCode: str | None


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
    visualReferenceSets: list[ShotVisualReferenceSetResponse]
    reviewArtifact: ChapterAdaptationReviewSummary | None
    latestTask: ChapterAdaptationTaskResponse | None
    createdAt: datetime


class ChapterAdaptationListResponse(VideoAdaptationApiModel):
    adaptations: list[ChapterAdaptationResponse]


class ChapterAdaptationTaskAcceptedResponse(VideoAdaptationApiModel):
    adaptation: ChapterAdaptationResponse
    task: ChapterAdaptationTaskResponse

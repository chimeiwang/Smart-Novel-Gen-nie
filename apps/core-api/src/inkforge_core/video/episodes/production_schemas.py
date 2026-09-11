"""独立分集的分镜、素材采用和制作基线公共契约。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from inkforge_contracts.video_storyboard import (
    VideoStoryboardReview,
    VideoStoryboardReviewFinding,
)
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .schemas import ClientRequestId, Identifier

Sha256 = str


class VideoProductionApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoProductionCapabilityResponse(VideoProductionApiModel):
    provider: Literal["seedance"]
    model: str
    generationMode: Literal["reference"]
    executionMode: Literal["simulated", "live"]
    feeConfirmationRequired: bool
    videoPreviewEnabled: bool
    providerConfigured: bool
    providerEnabled: bool
    allowedDurationSeconds: list[int]
    allowedResolution: Literal["720p"]
    allowedOutputFormat: Literal["mp4"]
    maxImageReferences: Literal[20]


class VideoShotLineageInput(VideoProductionApiModel):
    sourceShotId: Identifier
    relation: Literal["replacement", "copy", "split", "merge"]


class VideoShotReferenceInput(VideoProductionApiModel):
    canonVersionId: Identifier
    strength: int | None = Field(default=None, ge=1, le=100)
    ordinal: int | None = Field(default=None, ge=1, le=20)
    canonContentHash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    assetId: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    mimeType: Literal["image/jpeg", "image/png", "image/webp"] | None = None
    duty: Literal["identity", "costume", "scene", "prop"] | None = None
    rightsStatus: Literal["confirmed"] | None = None
    lockedAt: AwareDatetime | None = None


class VideoShotProductionIntent(VideoProductionApiModel):
    provider: Literal["seedance"] = "seedance"
    model: str = Field(min_length=1, max_length=200)
    generationMode: Literal["reference"] = "reference"
    executionMode: Literal["simulated", "live"]
    feeConfirmed: bool
    prompt: str = Field(min_length=1, max_length=2_500)
    ratio: Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
    durationSeconds: int = Field(ge=4, le=12)
    resolution: Literal["720p"] = "720p"
    generateAudio: bool = True
    watermark: bool = False
    outputFormat: Literal["mp4"] = "mp4"
    references: list[VideoShotReferenceInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_fee_and_references(self) -> VideoShotProductionIntent:
        if self.executionMode == "live" and not self.feeConfirmed:
            raise ValueError("真实生成必须明确确认可能产生的供应商费用")
        if self.executionMode == "simulated" and self.feeConfirmed:
            raise ValueError("模拟生成不产生供应商费用，不能保存付费确认")
        versions = [item.canonVersionId for item in self.references]
        if len(versions) != len(set(versions)):
            raise ValueError("同一视觉版本不能重复引用")
        return self


class VideoStoryboardShot(VideoProductionApiModel):
    id: Identifier | None = None
    tempKey: Identifier | None = None
    lineage: list[VideoShotLineageInput] = Field(default_factory=list, max_length=20)
    scriptSceneId: Identifier
    scriptLineIds: list[Identifier] = Field(default_factory=list, max_length=100)
    title: str = Field(min_length=1, max_length=240)
    action: str = Field(min_length=1, max_length=4_000)
    framing: Literal[
        "extreme_wide", "wide", "medium", "close_up", "detail", "over_shoulder", "pov"
    ]
    cameraMovement: Literal[
        "static", "pan", "tilt", "dolly", "truck", "crane", "handheld", "orbit", "zoom"
    ]
    durationMs: int = Field(ge=4_000, le=12_000)
    productionIntent: VideoShotProductionIntent

    @model_validator(mode="after")
    def validate_identity_and_lineage(self) -> VideoStoryboardShot:
        if (self.id is None) == (self.tempKey is None):
            raise ValueError("镜头必须提供已有 id 或新建 tempKey")
        relations = {item.relation for item in self.lineage}
        sources = [item.sourceShotId for item in self.lineage]
        if len(sources) != len(set(sources)):
            raise ValueError("镜头沿袭来源不能重复")
        if len(relations) > 1:
            raise ValueError("一个新镜头不能混用多种沿袭关系")
        if "merge" in relations and len(sources) < 2:
            raise ValueError("合并镜头必须包含至少两个有序来源")
        if relations and "merge" not in relations and len(sources) != 1:
            raise ValueError("替换、复制和拆分镜头必须各有一个来源")
        if self.durationMs != self.productionIntent.durationSeconds * 1_000:
            raise ValueError("镜头预计时长必须与首批生成秒数一致")
        if len(self.scriptLineIds) != len(set(self.scriptLineIds)):
            raise ValueError("镜头绑定的台词身份不能重复")
        return self


class VideoStoryboardDocument(VideoProductionApiModel):
    schemaVersion: Literal["video-episode-storyboard/1.0"] = "video-episode-storyboard/1.0"
    shots: list[VideoStoryboardShot] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def validate_shot_keys(self) -> VideoStoryboardDocument:
        identities = [shot.id or f"temp:{shot.tempKey}" for shot in self.shots]
        if len(identities) != len(set(identities)):
            raise ValueError("同一分镜不能重复使用镜头身份")
        return self


class SaveVideoStoryboardDraftRequest(VideoProductionApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    scriptVersionId: Identifier
    baseStoryboardVersionId: Identifier | None = None
    document: VideoStoryboardDocument


class VideoStoryboardDraftResponse(VideoProductionApiModel):
    episodeId: str
    revision: int
    scriptVersionId: str | None
    baseStoryboardVersionId: str | None
    document: VideoStoryboardDocument
    shotIdMappings: dict[str, str] = Field(default_factory=dict)
    updatedAt: datetime


class StartVideoStoryboardRunRequest(VideoProductionApiModel):
    clientRequestId: ClientRequestId
    expectedDraftRevision: int = Field(ge=1)
    scriptVersionId: Identifier
    operation: Literal["episode_storyboard_generate", "episode_storyboard_revise"]
    selectedShotIds: list[Identifier] = Field(default_factory=list, max_length=300)
    instruction: str = Field(min_length=1, max_length=8_000)

    @model_validator(mode="after")
    def validate_scope(self) -> StartVideoStoryboardRunRequest:
        if len(self.selectedShotIds) != len(set(self.selectedShotIds)):
            raise ValueError("分镜修订范围不能重复")
        if self.operation == "episode_storyboard_generate" and self.selectedShotIds:
            raise ValueError("分镜起草不能携带局部修订范围")
        if self.operation == "episode_storyboard_revise" and not self.selectedShotIds:
            raise ValueError("分镜修订必须明确选择至少一个稳定镜头")
        return self


class VideoStoryboardRunResponse(VideoProductionApiModel):
    runId: str
    episodeId: str
    status: str
    artifactId: str | None
    errorCode: str | None
    errorMessage: str | None
    createdAt: datetime
    updatedAt: datetime


class VideoStoryboardRunListResponse(VideoProductionApiModel):
    runs: list[VideoStoryboardRunResponse]
    nextBeforeRunId: str | None


class VideoStoryboardCandidateResponse(VideoProductionApiModel):
    artifactId: str
    workflowRunId: str
    episodeId: str
    revision: int
    status: Literal["draft", "awaiting_user", "applied", "rejected"]
    title: str
    summary: str | None
    expectedDraftRevision: int
    scriptVersionId: str
    baseStoryboardVersionId: str | None
    document: VideoStoryboardDocument
    reviewFindings: list[VideoStoryboardReviewFinding] = Field(default_factory=list)
    review: VideoStoryboardReview | None = None
    createdAt: datetime


class AdoptVideoStoryboardCandidateRequest(VideoProductionApiModel):
    clientRequestId: ClientRequestId
    expectedArtifactRevision: int = Field(ge=1)
    expectedDraftRevision: int = Field(ge=1)


class PrepareVideoStoryboardConfirmationRequest(VideoProductionApiModel):
    clientRequestId: ClientRequestId
    expectedDraftRevision: int = Field(ge=1)
    expectedEpisodeRevision: int = Field(ge=1)


class VideoStoryboardConfirmationResponse(VideoProductionApiModel):
    artifactId: str
    artifactRevision: int
    episodeId: str
    episodeRevision: int
    draftRevision: int
    scriptVersionId: str
    baseStoryboardVersionId: str | None
    document: VideoStoryboardDocument
    confirmationHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    createdAt: datetime


class ApproveVideoStoryboardConfirmationRequest(VideoProductionApiModel):
    clientRequestId: ClientRequestId
    expectedArtifactRevision: int = Field(ge=1)
    expectedDraftRevision: int = Field(ge=1)
    expectedEpisodeRevision: int = Field(ge=1)
    confirmationHash: str = Field(pattern=r"^[0-9a-f]{64}$")


class VideoShotVersionResponse(VideoProductionApiModel):
    id: str
    shotId: str
    storyboardVersionId: str
    ordinal: int
    versionNo: int
    scriptSceneId: str
    scriptLineIds: list[str]
    content: VideoStoryboardShot
    contentHash: str
    createdAt: datetime


class VideoStoryboardVersionSummary(VideoProductionApiModel):
    id: str
    episodeId: str
    versionNo: int
    basedOnVersionId: str | None
    scriptVersionId: str
    shotCount: int
    contentHash: str
    createdAt: datetime


class VideoStoryboardVersionResponse(VideoStoryboardVersionSummary):
    document: VideoStoryboardDocument
    shots: list[VideoShotVersionResponse]
    confirmationArtifactId: str


class VideoStoryboardVersionListResponse(VideoProductionApiModel):
    versions: list[VideoStoryboardVersionSummary]
    nextBeforeVersionNo: int | None


class VideoTakeAdoptionComparison(VideoProductionApiModel):
    sourceBaselineId: Identifier
    targetShotVersionId: Identifier
    directInputsUnchanged: bool
    referenceHashesChecked: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_hashes(self) -> VideoTakeAdoptionComparison:
        invalid_hash = any(
            len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)
            for value in self.referenceHashesChecked
        )
        if invalid_hash:
            raise ValueError("参考素材哈希必须是小写 SHA-256")
        return self


class CreateVideoTakeAdoptionRequest(VideoProductionApiModel):
    clientRequestId: ClientRequestId
    expectedProductionRevision: int = Field(ge=1)
    targetShotVersionId: Identifier
    sourceTakeId: Identifier
    sourceBaselineId: Identifier
    comparison: VideoTakeAdoptionComparison

    @model_validator(mode="after")
    def validate_comparison_scope(self) -> CreateVideoTakeAdoptionRequest:
        if self.comparison.sourceBaselineId != self.sourceBaselineId:
            raise ValueError("核对依据的源基线与采用请求不一致")
        if self.comparison.targetShotVersionId != self.targetShotVersionId:
            raise ValueError("核对依据的目标镜头版本与采用请求不一致")
        return self


class VideoTakeAdoptionResponse(VideoProductionApiModel):
    id: str
    episodeId: str
    targetShotId: str
    targetShotVersionId: str
    sourceTakeId: str
    sourceBaselineId: str
    comparison: VideoTakeAdoptionComparison
    decisionHash: str
    createdAt: datetime


class VideoTakeCandidateSummary(VideoProductionApiModel):
    id: str
    takeNo: int = Field(ge=1)
    sourceBaselineId: str
    sourceShotId: str
    sourceShotVersionId: str
    promptVersionId: str
    assetId: str
    lastFrameAssetId: str | None
    provider: Literal["seedance"]
    model: str
    inputHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    durationMs: int = Field(ge=1)
    byteSize: int = Field(ge=1)
    mimeType: Literal["video/mp4"]
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    adopted: bool
    adoptionId: str | None
    createdAt: datetime

    @model_validator(mode="after")
    def validate_adoption(self) -> VideoTakeCandidateSummary:
        if self.adopted != (self.adoptionId is not None):
            raise ValueError("Take 候选采用状态与采用记录不一致")
        return self


class VideoTakeCandidateListResponse(VideoProductionApiModel):
    episodeId: str
    targetShotVersionId: str
    takes: list[VideoTakeCandidateSummary]
    nextBeforeTakeId: str | None


class VideoProductionBaselineAdoptionInput(VideoProductionApiModel):
    shotVersionId: Identifier
    adoptionId: Identifier


class VideoProductionKeyframeInput(VideoProductionApiModel):
    shotVersionId: Identifier
    role: Literal["initial_state", "transition_anchor", "end_state"]
    assetId: Identifier


class CreateVideoProductionBaselineRequest(VideoProductionApiModel):
    clientRequestId: ClientRequestId
    expectedEpisodeRevision: int = Field(ge=1)
    expectedProductionRevision: int = Field(ge=1)
    basedOnBaselineId: Identifier | None = None
    scriptVersionId: Identifier
    storyboardVersionId: Identifier
    shotAdoptions: list[VideoProductionBaselineAdoptionInput] = Field(
        default_factory=list, max_length=300
    )
    keyframes: list[VideoProductionKeyframeInput] = Field(
        default_factory=list, max_length=900
    )

    @model_validator(mode="after")
    def validate_adoptions(self) -> CreateVideoProductionBaselineRequest:
        versions = [item.shotVersionId for item in self.shotAdoptions]
        if len(versions) != len(set(versions)):
            raise ValueError("每个镜头版本最多选择一条采用记录")
        keyframe_keys = [(item.shotVersionId, item.role) for item in self.keyframes]
        if len(keyframe_keys) != len(set(keyframe_keys)):
            raise ValueError("每个镜头的同一关键帧角色最多选择一份素材")
        return self


class VideoProductionKeyframeSnapshot(VideoProductionApiModel):
    ordinal: int = Field(ge=1, le=3)
    keyframeVersionId: str
    role: Literal["initial_state", "transition_anchor", "end_state"]
    assetId: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mimeType: Literal["image/jpeg", "image/png", "image/webp"]
    duty: Literal["identity", "costume", "scene", "prop", "storyboard", "keyframe"]
    rightsStatus: Literal["confirmed"] | None = None
    lockedAt: AwareDatetime | None = None
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")


class VideoProductionShotInputSnapshot(VideoProductionApiModel):
    schemaVersion: Literal[
        "video-production-shot-input/1.0",
        "video-production-shot-input/1.1",
        "video-production-shot-input/1.2",
    ]
    shotId: str
    shotVersionId: str
    shotVersionNo: int
    shotContentHash: str
    scriptSceneId: str
    scriptLineIds: list[str]
    provider: Literal["seedance"]
    model: str
    generationMode: Literal["reference"]
    executionMode: Literal["simulated", "live"]
    feeConfirmed: bool
    promptVersionId: str
    prompt: str
    ratio: Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
    durationSeconds: int = Field(ge=4, le=12)
    resolution: Literal["720p"]
    generateAudio: bool
    watermark: bool
    outputFormat: Literal["mp4"]
    references: list[VideoShotReferenceInput] = Field(min_length=1, max_length=20)
    keyframes: list[VideoProductionKeyframeSnapshot] = Field(
        default_factory=list, max_length=3
    )

    @model_validator(mode="after")
    def validate_frozen_images(self) -> VideoProductionShotInputSnapshot:
        if (
            self.executionMode == "live"
            and self.schemaVersion != "video-production-shot-input/1.2"
        ):
            raise ValueError("真实生成必须使用冻结权利事实的 1.2 制作基线")
        if self.schemaVersion == "video-production-shot-input/1.0" and self.keyframes:
            raise ValueError("1.0 制作输入不能携带关键帧")
        roles = [item.role for item in self.keyframes]
        if len(roles) != len(set(roles)):
            raise ValueError("同一制作输入不能重复关键帧角色")
        if len(self.references) + len(self.keyframes) > 20:
            raise ValueError("视觉参考与关键帧合计不能超过 20 张")
        if self.schemaVersion == "video-production-shot-input/1.2":
            for reference in self.references:
                if (
                    reference.canonContentHash is None
                    or reference.assetId is None
                    or reference.sha256 is None
                    or reference.mimeType is None
                    or reference.duty is None
                    or reference.rightsStatus != "confirmed"
                    or reference.lockedAt is None
                    or reference.lockedAt.utcoffset() != timedelta(0)
                ):
                    raise ValueError("1.2 制作输入必须冻结完整视觉素材和 UTC 权利事实")
            for keyframe in self.keyframes:
                if (
                    keyframe.rightsStatus != "confirmed"
                    or keyframe.lockedAt is None
                    or keyframe.lockedAt.utcoffset() != timedelta(0)
                ):
                    raise ValueError("1.2 制作输入必须冻结完整关键帧 UTC 权利事实")
        return self


class VideoProductionBaselineShotResponse(VideoProductionApiModel):
    ordinal: int
    shotId: str
    shotVersionId: str
    adoptionId: str | None
    status: Literal["pending", "adopted"]
    inputSnapshot: VideoProductionShotInputSnapshot
    inputHash: str


class VideoProductionBaselineManifestShot(VideoProductionApiModel):
    ordinal: int
    shotId: str
    shotVersionId: str
    adoptionId: str | None
    inputHash: str


class VideoProductionBaselineManifest(VideoProductionApiModel):
    schemaVersion: Literal["video-production-baseline/1.0"]
    episodeId: str
    scriptVersionId: str
    storyboardVersionId: str
    shots: list[VideoProductionBaselineManifestShot]


class VideoProductionBaselineSummary(VideoProductionApiModel):
    id: str
    episodeId: str
    versionNo: int
    basedOnBaselineId: str | None
    scriptVersionId: str
    storyboardVersionId: str
    shotCount: int
    contentHash: str
    createdAt: datetime


class VideoProductionBaselineResponse(VideoProductionBaselineSummary):
    manifest: VideoProductionBaselineManifest
    shots: list[VideoProductionBaselineShotResponse]
    productionRevision: int


class VideoProductionBaselineListResponse(VideoProductionApiModel):
    baselines: list[VideoProductionBaselineSummary]
    nextBeforeVersionNo: int | None

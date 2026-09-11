"""独立分集基础粗剪、声音字幕与交付公共契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import ClientRequestId, Identifier

EditTransition = Literal["cut", "fade_black"]
AudioTrackKind = Literal["dialogue", "narration", "ambience", "sfx", "music"]
ExportTaskStatus = Literal["pending", "rendering", "succeeded", "failed"]


class VideoEpisodePostApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoEpisodeEditClipInput(VideoEpisodePostApiModel):
    tempKey: Identifier
    adoptionId: Identifier
    takeId: Identifier
    sourceInMs: int = Field(ge=0)
    sourceOutMs: int = Field(gt=0)
    sourceAudioMode: Literal["keep", "mute"]
    transitionAfter: EditTransition = "cut"
    transitionDurationMs: int = Field(default=0, ge=0, le=2_000)

    @model_validator(mode="after")
    def validate_range_and_transition(self) -> VideoEpisodeEditClipInput:
        duration = self.sourceOutMs - self.sourceInMs
        if duration < 500:
            raise ValueError("粗剪片段时长不能少于 500 毫秒")
        if self.transitionAfter == "cut" and self.transitionDurationMs != 0:
            raise ValueError("硬切不能携带转场时长")
        if self.transitionAfter == "fade_black" and self.transitionDurationMs == 0:
            raise ValueError("淡黑转场必须设置时长")
        if self.transitionDurationMs * 2 > duration:
            raise ValueError("转场时长不能超过片段时长的一半")
        return self


class VideoEpisodeShotOmissionInput(VideoEpisodePostApiModel):
    shotVersionId: Identifier
    reason: str = Field(min_length=1, max_length=1_000)


class CreateVideoEpisodeEditVersionRequest(VideoEpisodePostApiModel):
    clientRequestId: ClientRequestId
    expectedHeadRevision: int = Field(ge=1)
    basedOnVersionId: Identifier | None = None
    clips: list[VideoEpisodeEditClipInput] = Field(min_length=1, max_length=500)
    omissions: list[VideoEpisodeShotOmissionInput] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def validate_unique_request_keys(self) -> CreateVideoEpisodeEditVersionRequest:
        temp_keys = [item.tempKey for item in self.clips]
        if len(temp_keys) != len(set(temp_keys)):
            raise ValueError("粗剪片段临时身份不能重复")
        omitted = [item.shotVersionId for item in self.omissions]
        if len(omitted) != len(set(omitted)):
            raise ValueError("同一镜头版本不能重复省略")
        return self


class VideoEpisodePostAssetResponse(VideoEpisodePostApiModel):
    id: str
    name: str
    modality: Literal["video", "audio"]
    mimeType: str
    durationMs: int
    byteSize: int
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VideoEpisodeEditClipResponse(VideoEpisodePostApiModel):
    clipId: str
    ordinal: int
    adoptionId: str
    takeId: str
    shotId: str
    shotVersionId: str
    sourceInMs: int
    sourceOutMs: int
    timelineStartMs: int
    outputDurationMs: int
    sourceAudioMode: Literal["keep", "mute"]
    transitionAfter: EditTransition
    transitionDurationMs: int
    asset: VideoEpisodePostAssetResponse


class VideoEpisodeShotOmissionResponse(VideoEpisodePostApiModel):
    shotId: str
    shotVersionId: str
    reason: str


class VideoEpisodeEditVersionSummary(VideoEpisodePostApiModel):
    id: str
    episodeId: str
    productionBaselineId: str
    versionNo: int
    basedOnVersionId: str | None
    clipCount: int
    omissionCount: int
    totalDurationMs: int
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    createdAt: datetime


class VideoEpisodeEditVersionResponse(VideoEpisodeEditVersionSummary):
    clips: list[VideoEpisodeEditClipResponse]
    omissions: list[VideoEpisodeShotOmissionResponse]
    headRevision: int


class VideoEpisodeEditVersionListResponse(VideoEpisodePostApiModel):
    episodeId: str
    productionBaselineId: str
    headRevision: int
    currentVersionId: str | None
    versions: list[VideoEpisodeEditVersionSummary]
    nextBeforeVersionNo: int | None


class VideoEpisodeAudioClipInput(VideoEpisodePostApiModel):
    trackKind: AudioTrackKind
    assetId: Identifier
    shotVersionId: Identifier | None = None
    timelineStartMs: int = Field(ge=0)
    sourceInMs: int = Field(default=0, ge=0)
    sourceOutMs: int = Field(gt=0)
    gainMillibels: int = Field(default=0, ge=-6_000, le=1_200)
    fadeInMs: int = Field(default=0, ge=0, le=10_000)
    fadeOutMs: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_audio_range(self) -> VideoEpisodeAudioClipInput:
        duration = self.sourceOutMs - self.sourceInMs
        if duration <= 0:
            raise ValueError("音频 sourceOutMs 必须大于 sourceInMs")
        if self.fadeInMs + self.fadeOutMs > duration:
            raise ValueError("音频淡入淡出总时长不能超过片段时长")
        return self


class VideoEpisodeSubtitleCueInput(VideoEpisodePostApiModel):
    shotVersionId: Identifier
    scriptLineId: Identifier
    startMs: int = Field(ge=0)
    endMs: int = Field(gt=0)
    speaker: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_cue_range(self) -> VideoEpisodeSubtitleCueInput:
        if self.endMs <= self.startMs:
            raise ValueError("字幕 endMs 必须大于 startMs")
        return self


class CreateVideoEpisodeMixVersionRequest(VideoEpisodePostApiModel):
    clientRequestId: ClientRequestId
    expectedHeadRevision: int = Field(ge=1)
    basedOnVersionId: Identifier | None = None
    editVersionId: Identifier
    audioClips: list[VideoEpisodeAudioClipInput] = Field(default_factory=list, max_length=1_000)
    subtitleCues: list[VideoEpisodeSubtitleCueInput] = Field(
        default_factory=list, max_length=2_000
    )


class VideoEpisodeAudioClipResponse(VideoEpisodeAudioClipInput):
    ordinal: int
    shotId: str | None
    asset: VideoEpisodePostAssetResponse


class VideoEpisodeSubtitleCueResponse(VideoEpisodeSubtitleCueInput):
    ordinal: int
    shotId: str


class VideoEpisodeMixVersionSummary(VideoEpisodePostApiModel):
    id: str
    episodeId: str
    productionBaselineId: str
    editVersionId: str
    versionNo: int
    basedOnVersionId: str | None
    audioClipCount: int
    subtitleCueCount: int
    contentHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    createdAt: datetime


class VideoEpisodeMixVersionResponse(VideoEpisodeMixVersionSummary):
    audioClips: list[VideoEpisodeAudioClipResponse]
    subtitleCues: list[VideoEpisodeSubtitleCueResponse]
    headRevision: int


class VideoEpisodeMixVersionListResponse(VideoEpisodePostApiModel):
    episodeId: str
    productionBaselineId: str
    headRevision: int
    currentVersionId: str | None
    versions: list[VideoEpisodeMixVersionSummary]
    nextBeforeVersionNo: int | None


class StartVideoEpisodeExportRequest(VideoEpisodePostApiModel):
    clientRequestId: ClientRequestId
    editVersionId: Identifier
    mixVersionId: Identifier
    resolution: Literal["720p", "1080p"] = "720p"
    framesPerSecond: Literal[24, 25, 30] = 24
    burnSubtitles: bool = True


class RetryVideoEpisodeExportRequest(VideoEpisodePostApiModel):
    clientRequestId: ClientRequestId


class VideoEpisodeDeliveryAssetResponse(VideoEpisodePostAssetResponse):
    modality: Literal["video"]
    contentUrl: str


class VideoEpisodeDeliveryResponse(VideoEpisodePostApiModel):
    id: str
    taskId: str
    episodeId: str
    productionBaselineId: str
    versionNo: int
    editVersionId: str
    mixVersionId: str
    inputHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    createdAt: datetime
    asset: VideoEpisodeDeliveryAssetResponse


class VideoEpisodeExportTaskResponse(VideoEpisodePostApiModel):
    id: str
    episodeId: str
    productionBaselineId: str
    editVersionId: str
    mixVersionId: str
    retryOfTaskId: str | None
    status: ExportTaskStatus
    clientRequestId: str
    inputHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution: Literal["720p", "1080p"]
    framesPerSecond: Literal[24, 25, 30]
    burnSubtitles: bool
    attemptCount: int = Field(ge=0)
    lastErrorCode: str | None
    lastErrorMessage: str | None
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None
    completedAt: datetime | None
    export: VideoEpisodeDeliveryResponse | None

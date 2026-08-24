"""章节影视化 P1–P3 后期制作公共 API 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

KeyframeRole = Literal["initial_state", "transition_anchor", "end_state"]
KeyframeSourceKind = Literal["asset", "take_frame", "cleared"]
EditTransition = Literal["cut", "fade_black"]
AudioTrackKind = Literal["dialogue", "narration", "ambience", "sfx", "music"]
ExportTaskStatus = Literal["pending", "rendering", "succeeded", "failed"]

ClientRequestId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=16, max_length=128),
]


class PostProductionApiModel(BaseModel):
    """后期制作公共契约默认拒绝未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class PostProductionReadinessResponse(PostProductionApiModel):
    ffmpegAvailable: bool
    ffprobeAvailable: bool
    blockers: list[str]


class PostProductionAssetResponse(PostProductionApiModel):
    id: str
    name: str
    modality: Literal["image", "video", "audio"]
    duty: str
    mimeType: str
    durationMs: int | None
    sha256: str
    contentUrl: str


class SaveShotKeyframeVersionRequest(PostProductionApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    role: KeyframeRole
    assetId: str | None = Field(default=None, min_length=1)
    sourceTakeId: str | None = Field(default=None, min_length=1)
    sourceTimeMs: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_source(self) -> SaveShotKeyframeVersionRequest:
        """清除版本不能携带来源；Take 抽帧来源必须同时携带时间和素材。"""

        source_values = (self.sourceTakeId, self.sourceTimeMs)
        if self.assetId is None and any(value is not None for value in source_values):
            raise ValueError("清除关键帧时不能携带 Take 来源")
        if (self.sourceTakeId is None) != (self.sourceTimeMs is None):
            raise ValueError("sourceTakeId 与 sourceTimeMs 必须同时提供")
        return self


class ExtractTakeFrameRequest(PostProductionApiModel):
    clientRequestId: ClientRequestId
    timestampMs: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=200)


class ShotKeyframeVersionResponse(PostProductionApiModel):
    id: str
    shotId: str
    shotPlanVersionId: str
    role: KeyframeRole
    versionNo: int
    basedOnVersionId: str | None
    asset: PostProductionAssetResponse | None
    sourceKind: KeyframeSourceKind
    sourceTakeId: str | None
    sourceTimeMs: int | None
    contentHash: str
    createdAt: datetime


class ShotKeyframeHeadResponse(PostProductionApiModel):
    shotId: str
    role: KeyframeRole
    revision: int
    currentVersion: ShotKeyframeVersionResponse | None
    history: list[ShotKeyframeVersionResponse] = Field(default_factory=list)


class ContinuityIssueResponse(PostProductionApiModel):
    code: str
    severity: Literal["info", "warning", "blocking"]
    message: str
    shotIds: list[str] = Field(min_length=1)
    duty: str | None = None


class PostProductionTakeResponse(PostProductionApiModel):
    id: str
    shotId: str
    takeNo: int
    durationMs: int | None
    createdAt: datetime
    asset: PostProductionAssetResponse


class EpisodeShotResponse(PostProductionApiModel):
    shotId: str
    shotKey: str
    ordinal: int
    title: str
    timelineDurationMs: int
    speechMode: Literal["none", "sync", "offscreen", "voiceover"]
    spokenText: str | None
    takes: list[PostProductionTakeResponse]
    confirmedTakeId: str | None


class EpisodeEditClipInput(PostProductionApiModel):
    shotId: str = Field(min_length=1)
    takeId: str | None = Field(default=None, min_length=1)
    sourceInMs: int | None = Field(default=None, ge=0)
    sourceOutMs: int | None = Field(default=None, gt=0)
    outputDurationMs: int = Field(ge=500, le=120_000)
    transitionAfter: EditTransition = "cut"
    transitionDurationMs: int = Field(default=0, ge=0, le=2_000)

    @model_validator(mode="after")
    def validate_trim(self) -> EpisodeEditClipInput:
        """占位不能伪造源入出点，真实 Take 必须给出完整合法范围。"""

        if self.takeId is None:
            if self.sourceInMs is not None or self.sourceOutMs is not None:
                raise ValueError("占位镜头不能设置源入点或出点")
        elif self.sourceInMs is None or self.sourceOutMs is None:
            raise ValueError("选择 Take 后必须设置源入点和出点")
        elif self.sourceOutMs <= self.sourceInMs:
            raise ValueError("sourceOutMs 必须大于 sourceInMs")
        if self.transitionAfter == "cut" and self.transitionDurationMs != 0:
            raise ValueError("硬切的 transitionDurationMs 必须为 0")
        if self.transitionAfter == "fade_black" and self.transitionDurationMs == 0:
            raise ValueError("淡黑转场必须设置时长")
        if self.transitionDurationMs * 2 > self.outputDurationMs:
            raise ValueError("转场时长不能超过镜头输出时长的一半")
        return self


class SaveEpisodeEditVersionRequest(PostProductionApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    basedOnVersionId: str | None = Field(default=None, min_length=1)
    clips: list[EpisodeEditClipInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_unique_shots(self) -> SaveEpisodeEditVersionRequest:
        shot_ids = [clip.shotId for clip in self.clips]
        if len(set(shot_ids)) != len(shot_ids):
            raise ValueError("同一粗剪版本中镜头不能重复")
        return self


class EpisodeEditClipResponse(EpisodeEditClipInput):
    ordinal: int
    timelineStartMs: int


class EpisodeEditVersionSummaryResponse(PostProductionApiModel):
    id: str
    episodeNo: int
    versionNo: int
    basedOnVersionId: str | None
    totalDurationMs: int
    contentHash: str
    createdAt: datetime


class EpisodeEditVersionResponse(EpisodeEditVersionSummaryResponse):
    adaptationId: str
    episodePlanVersionId: str
    shotPlanVersionId: str
    clips: list[EpisodeEditClipResponse]


class EpisodeEditHeadResponse(PostProductionApiModel):
    episodePlanVersionId: str
    episodeNo: int
    revision: int
    currentVersion: EpisodeEditVersionResponse | None


class EpisodeAudioClipInput(PostProductionApiModel):
    trackKind: AudioTrackKind
    assetId: str = Field(min_length=1)
    shotId: str | None = Field(default=None, min_length=1)
    timelineStartMs: int = Field(ge=0)
    sourceInMs: int = Field(default=0, ge=0)
    sourceOutMs: int = Field(gt=0)
    gainMillibels: int = Field(default=0, ge=-6_000, le=1_200)
    fadeInMs: int = Field(default=0, ge=0, le=10_000)
    fadeOutMs: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def validate_audio_range(self) -> EpisodeAudioClipInput:
        duration = self.sourceOutMs - self.sourceInMs
        if duration <= 0:
            raise ValueError("音频 sourceOutMs 必须大于 sourceInMs")
        if self.fadeInMs + self.fadeOutMs > duration:
            raise ValueError("音频淡入淡出总时长不能超过片段时长")
        return self


class EpisodeSubtitleCueInput(PostProductionApiModel):
    shotId: str | None = Field(default=None, min_length=1)
    startMs: int = Field(ge=0)
    endMs: int = Field(gt=0)
    speaker: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_cue_range(self) -> EpisodeSubtitleCueInput:
        if self.endMs <= self.startMs:
            raise ValueError("字幕 endMs 必须大于 startMs")
        return self


class SaveEpisodeMixVersionRequest(PostProductionApiModel):
    clientRequestId: ClientRequestId
    expectedRevision: int = Field(ge=1)
    basedOnVersionId: str | None = Field(default=None, min_length=1)
    editVersionId: str = Field(min_length=1)
    audioClips: list[EpisodeAudioClipInput] = Field(default_factory=list, max_length=1_000)
    subtitleCues: list[EpisodeSubtitleCueInput] = Field(
        default_factory=list,
        max_length=2_000,
    )


class EpisodeAudioClipResponse(EpisodeAudioClipInput):
    ordinal: int
    asset: PostProductionAssetResponse


class EpisodeSubtitleCueResponse(EpisodeSubtitleCueInput):
    ordinal: int


class EpisodeMixVersionSummaryResponse(PostProductionApiModel):
    id: str
    episodeNo: int
    versionNo: int
    basedOnVersionId: str | None
    editVersionId: str
    contentHash: str
    createdAt: datetime


class EpisodeMixVersionResponse(EpisodeMixVersionSummaryResponse):
    adaptationId: str
    episodePlanVersionId: str
    shotPlanVersionId: str
    audioClips: list[EpisodeAudioClipResponse]
    subtitleCues: list[EpisodeSubtitleCueResponse]


class EpisodeMixHeadResponse(PostProductionApiModel):
    episodePlanVersionId: str
    episodeNo: int
    revision: int
    staleAgainstCurrentEdit: bool
    currentVersion: EpisodeMixVersionResponse | None


class StartEpisodeExportRequest(PostProductionApiModel):
    clientRequestId: ClientRequestId
    editVersionId: str = Field(min_length=1)
    mixVersionId: str = Field(min_length=1)
    resolution: Literal["720p", "1080p"] = "720p"
    framesPerSecond: Literal[24, 25, 30] = 24
    burnSubtitles: bool = True


class RetryEpisodeExportRequest(PostProductionApiModel):
    clientRequestId: ClientRequestId


class EpisodeExportResponse(PostProductionApiModel):
    id: str
    episodeNo: int
    versionNo: int
    editVersionId: str
    mixVersionId: str
    inputHash: str
    createdAt: datetime
    asset: PostProductionAssetResponse


class EpisodeExportTaskResponse(PostProductionApiModel):
    id: str
    adaptationId: str
    episodeNo: int
    editVersionId: str
    mixVersionId: str
    retryOfTaskId: str | None
    status: ExportTaskStatus
    clientRequestId: str
    inputHash: str
    resolution: Literal["720p", "1080p"]
    framesPerSecond: Literal[24, 25, 30]
    burnSubtitles: bool
    attemptCount: int
    lastErrorCode: str | None
    lastErrorMessage: str | None
    createdAt: datetime
    updatedAt: datetime
    startedAt: datetime | None
    completedAt: datetime | None
    export: EpisodeExportResponse | None


class EpisodePostProductionResponse(PostProductionApiModel):
    episodeNo: int
    shots: list[EpisodeShotResponse]
    defaultClips: list[EpisodeEditClipResponse]
    suggestedSubtitleCues: list[EpisodeSubtitleCueInput]
    editHead: EpisodeEditHeadResponse
    editHistory: list[EpisodeEditVersionSummaryResponse]
    mixHead: EpisodeMixHeadResponse
    mixHistory: list[EpisodeMixVersionSummaryResponse]
    exportTasks: list[EpisodeExportTaskResponse]


class ShotPostProductionResponse(PostProductionApiModel):
    shotId: str
    shotKey: str
    title: str
    heads: list[ShotKeyframeHeadResponse]


class ChapterPostProductionWorkspaceResponse(PostProductionApiModel):
    adaptationId: str
    projectId: str
    novelId: str
    shotPlanVersionId: str
    episodePlanVersionId: str
    readiness: PostProductionReadinessResponse
    keyframeAssets: list[PostProductionAssetResponse]
    audioAssets: list[PostProductionAssetResponse]
    shots: list[ShotPostProductionResponse]
    continuityIssues: list[ContinuityIssueResponse]
    episodes: list[EpisodePostProductionResponse]

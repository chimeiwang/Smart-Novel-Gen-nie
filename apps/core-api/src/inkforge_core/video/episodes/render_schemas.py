"""独立剧集逐镜生成公共 OpenAPI 契约；运行实现仅位于 Java Core。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    model_validator,
)

from .production_schemas import VideoProductionKeyframeSnapshot

ClientRequestId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=16, max_length=128),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
VideoEpisodeRenderTaskStatus = Literal[
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


class VideoEpisodeRenderApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartVideoEpisodeShotRenderRequest(VideoEpisodeRenderApiModel):
    """生成参数来自制作基线；请求只能确认本次业务身份与费用事实。"""

    clientRequestId: ClientRequestId
    feeConfirmed: bool = Field(default=False, strict=True)


class RetryVideoEpisodeShotRenderRequest(VideoEpisodeRenderApiModel):
    """精确复制旧任务冻结输入；不能借重试读取新的制作基线。"""

    clientRequestId: ClientRequestId
    feeConfirmed: bool = Field(default=False, strict=True)


class VideoEpisodeRenderReference(VideoEpisodeRenderApiModel):
    ordinal: int = Field(ge=1, le=20)
    canonVersionId: str = Field(min_length=1)
    canonContentHash: Sha256
    assetId: str = Field(min_length=1)
    sha256: Sha256
    mimeType: Literal["image/jpeg", "image/png", "image/webp"]
    duty: Literal["identity", "costume", "scene", "prop"]
    rightsStatus: Literal["confirmed"] | None = None
    lockedAt: AwareDatetime | None = None
    strength: int = Field(ge=1, le=100)


class VideoEpisodeProductionShotInput(VideoEpisodeRenderApiModel):
    """制作基线逐镜冻结输入；渲染任务不得从可变 Head 重新拼装。"""

    schemaVersion: Literal[
        "video-production-shot-input/1.0",
        "video-production-shot-input/1.1",
        "video-production-shot-input/1.2",
    ]
    shotId: str = Field(min_length=1)
    shotVersionId: str = Field(min_length=1)
    shotVersionNo: int = Field(ge=1)
    shotContentHash: Sha256
    scriptSceneId: str = Field(min_length=1)
    scriptLineIds: list[str] = Field(default_factory=list, max_length=500)
    provider: Literal["seedance"]
    model: str = Field(min_length=1, max_length=200)
    generationMode: Literal["reference"]
    executionMode: Literal["simulated", "live"]
    feeConfirmed: bool = Field(strict=True)
    promptVersionId: str = Field(min_length=1)
    prompt: str = Field(min_length=1, max_length=2_500)
    ratio: Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
    durationSeconds: int = Field(ge=4, le=12, strict=True)
    resolution: Literal["720p"]
    generateAudio: bool = Field(strict=True)
    watermark: bool = Field(strict=True)
    outputFormat: Literal["mp4"]
    references: list[VideoEpisodeRenderReference] = Field(min_length=1, max_length=20)
    keyframes: list[VideoProductionKeyframeSnapshot] = Field(
        default_factory=list, max_length=3
    )

    @model_validator(mode="after")
    def validate_generation_facts(self) -> Self:
        if self.executionMode == "simulated" and self.feeConfirmed:
            raise ValueError("模拟生成不能确认供应商费用")
        if self.executionMode == "live" and not self.feeConfirmed:
            raise ValueError("真实生成必须冻结费用确认")
        if (
            self.executionMode == "live"
            and self.schemaVersion != "video-production-shot-input/1.2"
        ):
            raise ValueError("真实生成必须使用冻结权利事实的 1.2 制作基线")
        ordinals = [reference.ordinal for reference in self.references]
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise ValueError("参考素材必须按冻结顺序从 1 连续编号")
        if len({reference.canonVersionId for reference in self.references}) != len(
            self.references
        ):
            raise ValueError("同一冻结输入不能重复引用视觉设定版本")
        if self.schemaVersion == "video-production-shot-input/1.0" and self.keyframes:
            raise ValueError("1.0 制作输入不能携带关键帧")
        roles = [keyframe.role for keyframe in self.keyframes]
        if len(roles) != len(set(roles)):
            raise ValueError("同一冻结输入不能重复关键帧角色")
        if len(self.references) + len(self.keyframes) > 20:
            raise ValueError("视觉参考与关键帧合计不能超过 20 张")
        if self.schemaVersion == "video-production-shot-input/1.2":
            for reference in self.references:
                if (
                    reference.rightsStatus != "confirmed"
                    or reference.lockedAt is None
                    or reference.lockedAt.utcoffset() != timedelta(0)
                ):
                    raise ValueError("1.2 制作输入必须冻结视觉素材 UTC 权利事实")
            for keyframe in self.keyframes:
                if (
                    keyframe.rightsStatus != "confirmed"
                    or keyframe.lockedAt is None
                    or keyframe.lockedAt.utcoffset() != timedelta(0)
                ):
                    raise ValueError("1.2 制作输入必须冻结关键帧 UTC 权利事实")
        return self


class VideoEpisodeRenderTaskResponse(VideoEpisodeRenderApiModel):
    id: str
    episodeId: str
    productionBaselineId: str
    shotId: str
    shotVersionId: str
    promptVersionId: str
    retryOfTaskId: str | None
    provider: Literal["seedance"]
    model: str
    status: VideoEpisodeRenderTaskStatus
    inputHash: Sha256
    inputSnapshot: VideoEpisodeProductionShotInput
    providerTaskId: str | None
    pollCount: int = Field(ge=0)
    attemptCount: int = Field(ge=0)
    lastErrorCode: str | None
    lastErrorMessage: str | None
    takeId: str | None
    mediaKind: Literal["provider_media", "simulated_placeholder"] | None
    createdAt: datetime
    updatedAt: datetime
    submittedAt: datetime | None
    completedAt: datetime | None


class VideoEpisodeTakeArchivedFrame(VideoEpisodeRenderApiModel):
    assetId: str
    sha256: Sha256
    mimeType: Literal["image/jpeg", "image/png", "image/webp"]
    byteSize: int = Field(gt=0)


class VideoEpisodeTakeProviderMetadata(VideoEpisodeRenderApiModel):
    mediaKind: Literal["provider_media", "simulated_placeholder"]
    executionMode: Literal["simulated", "live"]
    simulated: bool
    durationSeconds: float | None = Field(default=None, gt=0)
    framesPerSecond: int | None = Field(default=None, gt=0)
    generateAudio: bool | None = None
    ratio: str | None = None
    resolution: str | None = None
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    lastFrame: VideoEpisodeTakeArchivedFrame | None = None

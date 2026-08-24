"""逐镜视频生成的冻结清单与 Core -> Agent Seedance 短调用契约。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

AspectRatio = Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
RenderResolution = Literal["480p", "720p", "1080p"]
SeedanceProviderStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "expired",
    "cancelled",
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class VideoRenderContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShotRenderReferenceManifest(VideoRenderContractModel):
    """持久化到任务中的视觉参考事实，不含任何短时 URL。"""

    ordinal: int = Field(ge=1, le=20)
    canonVersionId: str = Field(min_length=1)
    assetId: str = Field(min_length=1)
    sha256: Sha256
    mimeType: str = Field(min_length=1, max_length=160)
    duty: Literal["identity", "costume", "scene", "prop"]
    strength: int = Field(ge=1, le=100)


class ShotRenderKeyframeManifest(VideoRenderContractModel):
    """进入一次渲染清单的已确认关键帧事实。"""

    ordinal: int = Field(ge=1, le=3)
    keyframeVersionId: str = Field(min_length=1)
    role: Literal["initial_state", "transition_anchor", "end_state"]
    assetId: str = Field(min_length=1)
    sha256: Sha256
    mimeType: str = Field(min_length=1, max_length=160)
    duty: Literal["storyboard", "keyframe"]


class VideoShotRenderManifest(VideoRenderContractModel):
    """Core 创建任务时冻结的完整、可哈希供应商中立输入。"""

    schemaVersion: Literal[
        "video-shot-render-manifest/1.0",
        "video-shot-render-manifest/1.1",
    ] = "video-shot-render-manifest/1.1"
    adaptationId: str = Field(min_length=1)
    projectId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    shotId: str = Field(min_length=1)
    shotKey: str = Field(min_length=1, max_length=80)
    shotPlanVersionId: str = Field(min_length=1)
    promptVersionId: str = Field(min_length=1)
    promptContentHash: Sha256
    promptText: str = Field(min_length=1, max_length=2_000)
    providerPromptText: str | None = Field(default=None, min_length=1, max_length=2_500)
    sourceTimelineDurationMs: int = Field(ge=500, le=15_000)
    provider: Literal["seedance"] = "seedance"
    model: str = Field(min_length=1, max_length=200)
    ratio: AspectRatio
    durationSeconds: int = Field(ge=2, le=12)
    resolution: RenderResolution = "720p"
    generateAudio: bool = True
    watermark: bool = False
    references: list[ShotRenderReferenceManifest] = Field(
        default_factory=list,
        max_length=20,
    )
    keyframes: list[ShotRenderKeyframeManifest] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_v11_keyframes(self) -> VideoShotRenderManifest:
        """1.0 清单保持可读；1.1 关键帧必须冻结最终供应商提示词。"""

        if self.schemaVersion == "video-shot-render-manifest/1.0":
            if self.providerPromptText is not None or self.keyframes:
                raise ValueError("1.0 清单不能携带 P1 关键帧字段")
            return self
        if self.keyframes and self.providerPromptText is None:
            raise ValueError("带关键帧的 1.1 清单必须冻结 providerPromptText")
        roles = [item.role for item in self.keyframes]
        if len(set(roles)) != len(roles):
            raise ValueError("同一渲染清单中的关键帧角色不能重复")
        if len(self.references) + len(self.keyframes) > 20:
            raise ValueError("Seedance 单次渲染最多使用 20 份图片输入")
        return self


class SeedanceRuntimeReference(VideoRenderContractModel):
    """仅存在于受签名内部请求中的短时参考图地址。"""

    ordinal: int = Field(ge=1, le=20)
    assetId: str = Field(min_length=1)
    mimeType: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=1, max_length=4_096)
    usageRole: Literal[
        "visual_reference",
        "initial_state",
        "transition_anchor",
        "end_state",
    ] = "visual_reference"


class SeedanceRenderSubmitRequest(VideoRenderContractModel):
    """Core 从冻结清单投影出的单次 Seedance 创建请求。"""

    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    inputHash: Sha256
    model: str = Field(min_length=1, max_length=200)
    promptText: str = Field(min_length=1, max_length=2_000)
    ratio: AspectRatio
    durationSeconds: int = Field(ge=2, le=12)
    resolution: RenderResolution
    generateAudio: bool
    watermark: bool
    references: list[SeedanceRuntimeReference] = Field(
        default_factory=list,
        max_length=20,
    )


class SeedanceRenderSubmitResponse(VideoRenderContractModel):
    taskId: str
    providerTaskId: str = Field(min_length=1)


class SeedanceRenderQueryRequest(VideoRenderContractModel):
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    providerTaskId: str = Field(min_length=1)
    pollCount: int = Field(ge=1)


class SeedanceRenderOutput(VideoRenderContractModel):
    videoUrl: str = Field(min_length=1, max_length=8_192)
    durationSeconds: float | None = Field(default=None, gt=0)
    resolution: str | None = Field(default=None, max_length=80)
    ratio: str | None = Field(default=None, max_length=80)
    framesPerSecond: int | None = Field(default=None, gt=0)
    generateAudio: bool | None = None
    usage: dict[str, JsonValue] = Field(default_factory=dict)


class SeedanceRenderError(VideoRenderContractModel):
    code: str = Field(min_length=1, max_length=240)
    message: str = Field(min_length=1, max_length=2_000)


class SeedanceRenderQueryResponse(VideoRenderContractModel):
    taskId: str
    providerTaskId: str
    status: SeedanceProviderStatus
    output: SeedanceRenderOutput | None = None
    error: SeedanceRenderError | None = None

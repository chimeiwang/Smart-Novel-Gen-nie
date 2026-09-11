"""逐镜视频生成的冻结清单与 Core -> Agent Seedance 短调用契约。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

AspectRatio = Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
RenderResolution = Literal["480p", "720p", "1080p"]
VideoRenderExecutionMode = Literal["simulated", "live"]
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
        "video-shot-render-manifest/1.2",
    ] = "video-shot-render-manifest/1.2"
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
    generationMode: Literal["reference"] | None = None
    executionMode: VideoRenderExecutionMode | None = None
    feeConfirmed: bool | None = Field(default=None, strict=True)
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
    def validate_frozen_generation(self) -> VideoShotRenderManifest:
        """旧清单只读；新清单明确冻结模式、费用确认和首批试制边界。"""

        if self.schemaVersion != "video-shot-render-manifest/1.2":
            if (
                self.generationMode is not None
                or self.executionMode is not None
                or self.feeConfirmed is not None
            ):
                raise ValueError("旧清单不能补写未冻结的生成模式或费用确认")
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
        if self.schemaVersion == "video-shot-render-manifest/1.2":
            if self.generationMode != "reference" or self.executionMode is None:
                raise ValueError("1.2 清单必须冻结 generationMode=reference 和 executionMode")
            if self.feeConfirmed is None:
                raise ValueError("1.2 清单必须冻结 feeConfirmed")
            if self.executionMode == "live" and self.feeConfirmed is not True:
                raise ValueError("真实生成必须明确确认可能产生的供应商费用")
            if self.executionMode == "simulated" and self.feeConfirmed:
                raise ValueError("模拟生成不产生供应商费用，不能保存付费确认")
            if self.durationSeconds < 4 or self.resolution != "720p":
                raise ValueError("首批参考图试制只支持 4～12 秒、720p")
            if not self.references and not self.keyframes:
                raise ValueError("参考图模式至少需要一张已确认图片")
            mime_types = [item.mimeType for item in self.references] + [
                item.mimeType for item in self.keyframes
            ]
            if any(mime not in {"image/jpeg", "image/png", "image/webp"} for mime in mime_types):
                raise ValueError("首批参考素材只支持 JPEG、PNG 或 WebP 图片")
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
    generationMode: Literal["reference"]
    executionMode: VideoRenderExecutionMode
    model: str = Field(min_length=1, max_length=200)
    promptText: str = Field(min_length=1, max_length=2_500)
    ratio: AspectRatio
    durationSeconds: int = Field(ge=4, le=12)
    resolution: Literal["720p"]
    generateAudio: bool
    watermark: bool
    references: list[SeedanceRuntimeReference] = Field(
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_reference_transport(self) -> SeedanceRenderSubmitRequest:
        if [item.ordinal for item in self.references] != list(range(1, len(self.references) + 1)):
            raise ValueError("参考图序号必须按冻结顺序从 1 连续递增")
        if any(
            item.mimeType not in {"image/jpeg", "image/png", "image/webp"}
            for item in self.references
        ):
            raise ValueError("首批参考素材只支持 JPEG、PNG 或 WebP 图片")
        return self


class SeedanceRenderSubmitResponse(VideoRenderContractModel):
    taskId: str
    providerTaskId: str = Field(min_length=1)


class SeedanceRenderQueryRequest(VideoRenderContractModel):
    taskId: str = Field(min_length=1)
    novelId: str = Field(min_length=1)
    providerTaskId: str = Field(min_length=1)
    executionMode: VideoRenderExecutionMode
    pollCount: int = Field(ge=1)


class SeedanceRenderOutput(VideoRenderContractModel):
    videoUrl: str = Field(min_length=1, max_length=8_192)
    lastFrameUrl: str | None = Field(default=None, min_length=1, max_length=8_192)
    mediaKind: Literal["provider_media", "simulated_placeholder"]
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

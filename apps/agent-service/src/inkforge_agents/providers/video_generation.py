"""视频生成供应商的内部中立边界。

Core 的现有内部 HTTP 契约仍保留 Seedance 命名以兼容 Java 调用方；进入 Provider 前统一转换为本模块的
请求与结果。这样任务冻结、模拟执行和恢复语义不依赖某一家供应商的 wire 字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

VideoGenerationExecutionMode = Literal["simulated", "live"]
VideoGenerationMode = Literal["reference"]
VideoGenerationInputProfile = Literal["image_reference_v1", "multimodal_reference_v1"]
VideoGenerationModality = Literal["image", "video", "audio"]
VideoGenerationOutputFormat = Literal["mp4", "mov"]
VideoGenerationRatio = Literal[
    "16:9",
    "4:3",
    "1:1",
    "3:4",
    "9:16",
    "21:9",
    "adaptive",
]
VideoGenerationResolution = Literal["480p", "720p", "1080p"]
VideoGenerationStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "expired",
    "cancelled",
]
VideoGenerationMediaKind = Literal["provider_media", "simulated_placeholder"]
VideoGenerationUsageRole = Literal[
    "visual_reference",
    "motion_reference",
    "voice_reference",
    "initial_state",
    "transition_anchor",
    "end_state",
]


class VideoGenerationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class VideoGenerationIdentity:
    """可冻结到执行档案的 Provider 身份，不含密钥或实际素材地址。"""

    provider: str
    transport_profile: str
    capability_version: str
    supported_profiles: tuple[VideoGenerationInputProfile, ...]
    default_profile: VideoGenerationInputProfile


class VideoGenerationReference(VideoGenerationModel):
    """Core 已授权并按冻结顺序提供的短时媒体引用。"""

    ordinal: int = Field(ge=1, le=50)
    asset_id: str = Field(min_length=1)
    modality: VideoGenerationModality
    mime_type: str = Field(min_length=1, max_length=160)
    transport_url: str = Field(min_length=1, max_length=4_096)
    usage_role: VideoGenerationUsageRole = "visual_reference"
    source_duration_seconds: float | None = Field(default=None, gt=0, le=30, strict=True)

    @model_validator(mode="after")
    def validate_media_duration(self) -> Self:
        expected_prefix = f"{self.modality}/"
        if not self.mime_type.startswith(expected_prefix):
            raise ValueError("参考素材模态与 MIME 类型不一致")
        if self.modality == "image" and self.source_duration_seconds is not None:
            raise ValueError("图片参考不能携带媒体时长")
        if self.modality in {"video", "audio"} and self.source_duration_seconds is None:
            raise ValueError("视频和音频参考必须携带已探测时长")
        return self


class VideoGenerationRequest(VideoGenerationModel):
    """一次已冻结的视频生成输入；供应商适配器只能翻译，不能补取或重编译业务事实。"""

    task_id: str = Field(min_length=1)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_mode: VideoGenerationMode
    input_profile: VideoGenerationInputProfile
    execution_mode: VideoGenerationExecutionMode
    model: str = Field(min_length=1, max_length=200)
    prompt_text: str = Field(min_length=1, max_length=2_500)
    ratio: VideoGenerationRatio
    duration_seconds: int = Field(strict=True)
    resolution: VideoGenerationResolution
    output_format: VideoGenerationOutputFormat
    generate_audio: bool
    watermark: bool
    references: list[VideoGenerationReference] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_reference_order(self) -> Self:
        if [item.ordinal for item in self.references] != list(range(1, len(self.references) + 1)):
            raise ValueError("视频生成参考素材必须按冻结顺序从 1 连续递增")
        if self.duration_seconds != -1 and not 4 <= self.duration_seconds <= 30:
            raise ValueError("视频生成时长必须为 4～30 秒或 -1 自动时长")
        if self.input_profile == "image_reference_v1":
            if not self.references or len(self.references) > 20:
                raise ValueError("首批图片参考必须包含 1～20 张图片")
            if any(item.modality != "image" for item in self.references):
                raise ValueError("首批图片参考不能混入视频或音频")
            if not 4 <= self.duration_seconds <= 12:
                raise ValueError("首批图片参考只支持 4～12 秒")
            if self.resolution != "720p" or self.output_format != "mp4":
                raise ValueError("首批图片参考只支持 720p MP4")
        return self


class VideoGenerationSubmission(VideoGenerationModel):
    """短提交结果；只证明取得了可查询身份，不代表生成成功。"""

    task_id: str = Field(min_length=1)
    provider_task_id: str = Field(min_length=1)
    execution_mode: VideoGenerationExecutionMode
    simulated: bool

    @model_validator(mode="after")
    def validate_execution_origin(self) -> Self:
        if self.simulated != (self.execution_mode == "simulated"):
            raise ValueError("视频生成受理结果的模拟标记与执行方式不一致")
        return self


class VideoGenerationQuery(VideoGenerationModel):
    task_id: str = Field(min_length=1)
    provider_task_id: str = Field(min_length=1)
    execution_mode: VideoGenerationExecutionMode


class VideoGenerationOutput(VideoGenerationModel):
    """完成媒体的中立投影；模拟产物必须显式标记为占位媒体。"""

    video_url: str = Field(min_length=1, max_length=8_192)
    last_frame_url: str | None = Field(default=None, min_length=1, max_length=8_192)
    media_kind: VideoGenerationMediaKind
    duration_seconds: float | None = Field(default=None, gt=0)
    resolution: str | None = Field(default=None, max_length=80)
    ratio: str | None = Field(default=None, max_length=80)
    frames_per_second: int | None = Field(default=None, gt=0)
    generate_audio: bool | None = None
    usage: dict[str, JsonValue] = Field(default_factory=dict)


class VideoGenerationFailure(VideoGenerationModel):
    code: str = Field(min_length=1, max_length=240)
    message: str = Field(min_length=1, max_length=2_000)


class VideoGenerationResult(VideoGenerationModel):
    """一次短查询的规范化结果，不携带供应商完整响应正文。"""

    task_id: str = Field(min_length=1)
    provider_task_id: str = Field(min_length=1)
    execution_mode: VideoGenerationExecutionMode
    status: VideoGenerationStatus
    output: VideoGenerationOutput | None = None
    error: VideoGenerationFailure | None = None

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> Self:
        if self.status == "succeeded":
            if self.output is None or self.error is not None:
                raise ValueError("视频生成成功结果必须且只能携带媒体")
            expected_kind: VideoGenerationMediaKind = (
                "simulated_placeholder"
                if self.execution_mode == "simulated"
                else "provider_media"
            )
            if self.output.media_kind != expected_kind:
                raise ValueError("视频生成媒体来源与冻结执行方式不一致")
        elif self.status in {"failed", "expired", "cancelled"}:
            if self.error is None or self.output is not None:
                raise ValueError("视频生成失败终态必须且只能携带错误")
        elif self.output is not None or self.error is not None:
            raise ValueError("视频生成进行中状态不能提前携带终态结果")
        return self


class VideoGenerationProvider(Protocol):
    """视频生成短调用端口；轮询、归档和 Take 幂等仍由 Core 负责。"""

    @property
    def generation_identity(self) -> VideoGenerationIdentity: ...

    async def submit_generation(
        self, request: VideoGenerationRequest
    ) -> VideoGenerationSubmission: ...

    async def query_generation(self, query: VideoGenerationQuery) -> VideoGenerationResult: ...

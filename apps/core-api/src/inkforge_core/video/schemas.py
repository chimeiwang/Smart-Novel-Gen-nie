"""浏览器可见的视频制作 API 契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from inkforge_contracts.video import (
    AspectRatio,
    AssetDuty,
    AssetModality,
    SeedancePromptPackage,
)
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class VideoApiModel(BaseModel):
    """视频 API 默认拒绝额外字段，避免前后端静默漂移。"""

    model_config = ConfigDict(extra="forbid")


class CreateVideoProjectRequest(VideoApiModel):
    """创建一个独立于写作任务的视频项目。"""

    title: str = Field(min_length=1, max_length=200)
    mode: Literal["concept", "trailer", "highlight"] = "highlight"
    targetAspectRatio: AspectRatio = "16:9"
    targetLanguage: str = Field(default="zh-CN", min_length=2, max_length=32)


class CreateVideoSceneRequest(VideoApiModel):
    """用章节版本和浏览器 UTF-16 选区创建不可变来源快照。"""

    clientRequestId: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=16, max_length=128),
    ]
    chapterId: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=120)
    expectedChapterUpdatedAt: datetime
    selectionStartUtf16: int = Field(ge=0)
    selectionEndUtf16: int = Field(ge=1)
    selectedText: str = Field(min_length=1, max_length=2_000)
    durationSeconds: int = Field(default=15, ge=4, le=15)

    @model_validator(mode="after")
    def validate_selection_order(self) -> CreateVideoSceneRequest:
        """浏览器选区必须是非空的左闭右开范围。"""

        if self.selectionEndUtf16 <= self.selectionStartUtf16:
            raise ValueError("selectionEndUtf16 必须大于 selectionStartUtf16")
        return self


class ReviseVideoSceneRequest(VideoApiModel):
    """用作者的具体意见返工当前待审视频方案。"""

    clientRequestId: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=16, max_length=128),
    ]
    expectedArtifactRevision: int = Field(ge=1)
    userMessage: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
    ]


class ApproveVideoSceneRequest(VideoApiModel):
    """按候选 revision 原子批准视频场景，重复提交保持同一结果。"""

    clientRequestId: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=16, max_length=128),
    ]
    expectedArtifactRevision: int = Field(ge=1)


class PromptPreviewBinding(VideoApiModel):
    """正式方案中一个素材槽位与已锁定素材的本次预览映射。"""

    slotId: str = Field(min_length=1, max_length=240)
    assetId: str = Field(min_length=1)


class PromptPreviewRequest(VideoApiModel):
    """仅用于当次编译的非持久化素材槽位选择。"""

    previewBindings: list[PromptPreviewBinding] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_unique_slots(self) -> PromptPreviewRequest:
        """同一设定槽位在一次预览中只能选择一份素材。"""

        slot_ids = [binding.slotId for binding in self.previewBindings]
        if len(set(slot_ids)) != len(slot_ids):
            raise ValueError("预览素材的 slotId 不能重复")
        return self


class VideoGenerationTaskResponse(VideoApiModel):
    """前端轮询所需的耐久生成任务状态。"""

    id: str
    jobId: str
    kind: str
    status: str
    lastErrorCode: str | None
    lastErrorMessage: str | None
    createdAt: datetime
    updatedAt: datetime


class VideoAssetResponse(VideoApiModel):
    """素材库中可审核、可锁定的真实文件。"""

    id: str
    projectId: str
    name: str
    modality: AssetModality
    duty: AssetDuty
    mimeType: str
    byteSize: int
    durationMs: int | None
    sha256: str
    sourceKind: str
    rightsStatus: str
    lockedAt: datetime | None
    createdAt: datetime
    updatedAt: datetime


class ConfirmVideoAssetRequest(VideoApiModel):
    """用户确认素材权利并锁定，受限或拒绝素材不能锁定。"""

    rightsStatus: Literal["confirmed", "restricted", "rejected"]


class VideoAssetBindingResponse(VideoApiModel):
    """场景与真实素材之间的持久绑定。"""

    id: str
    sceneId: str
    assetId: str
    targetEntity: str
    includeFeatures: list[str]
    excludeFeatures: list[str]
    priority: int
    createdAt: datetime
    updatedAt: datetime


class VideoReviewArtifactSummary(VideoApiModel):
    """视频场景当前待用户确认的 ReviewArtifact。"""

    id: str
    status: str
    revision: int
    title: str | None
    summary: str | None


class VideoSceneResponse(VideoApiModel):
    """视频制作台展示的场景、提示词与审核状态。"""

    id: str
    projectId: str
    chapterId: str | None
    ordinal: int
    title: str
    sourceText: str
    sourceHash: str
    durationSeconds: int
    status: str
    promptText: str | None
    promptCharacterCount: int | None
    plan: dict[str, object] | None
    candidatePlan: dict[str, object] | None
    candidatePackage: SeedancePromptPackage | None
    reviewArtifact: VideoReviewArtifactSummary | None
    latestTask: VideoGenerationTaskResponse | None
    assetBindings: list[VideoAssetBindingResponse]
    revision: int
    createdAt: datetime
    updatedAt: datetime


class VideoProjectResponse(VideoApiModel):
    """视频项目列表项。"""

    id: str
    novelId: str
    title: str
    mode: str
    status: str
    targetAspectRatio: str
    targetLanguage: str
    provider: str
    revision: int
    sceneCount: int = 0
    createdAt: datetime
    updatedAt: datetime


class VideoProjectListResponse(VideoApiModel):
    """项目列表及创建第一个项目前也必须可见的能力状态。"""

    projects: list[VideoProjectResponse]
    previewEnabled: bool
    seedanceConfigured: bool
    seedanceEnabled: bool


class VideoProjectDetailResponse(VideoApiModel):
    """视频制作台一次加载所需的项目与场景。"""

    project: VideoProjectResponse
    scenes: list[VideoSceneResponse]
    assets: list[VideoAssetResponse]
    previewEnabled: bool
    seedanceConfigured: bool
    seedanceEnabled: bool


class CreateVideoSceneResponse(VideoApiModel):
    """场景入队后的初始响应。"""

    scene: VideoSceneResponse
    task: VideoGenerationTaskResponse


class ApproveVideoSceneResponse(VideoApiModel):
    """用户批准后返回正式场景。"""

    scene: VideoSceneResponse


class PromptPreviewResponse(VideoApiModel):
    """不保存绑定、且永远禁止提交供应商的开发预览包。"""

    promptPackage: SeedancePromptPackage
    resolvedSlotIds: list[str]
    missingSlotIds: list[str]

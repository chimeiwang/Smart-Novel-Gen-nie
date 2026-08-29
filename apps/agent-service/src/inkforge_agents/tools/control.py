# ruff: noqa: E501

from __future__ import annotations

from typing import Annotated, Literal, Self

from inkforge_contracts import ConsistencyQualityReport
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    NonNegativeInt,
    field_validator,
    model_validator,
)

from ..artifacts.patch import TextReplacePatch
from .permissions import control_permission
from .registry import ToolDefinition
from .safe_writes import SAFE_STRUCTURED_WRITE_INSTRUCTION

AgentId = Literal["设定", "剧情", "写作", "校验", "编辑"]


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityReportArgs(ConsistencyQualityReport):
    pass


class ProposalUpdatesArgs(StrictArgs):
    summary: str = Field(min_length=1, max_length=1000)
    updates: dict[str, JsonValue] = Field(
        description=SAFE_STRUCTURED_WRITE_INSTRUCTION
    )
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None


class StartBuilderArgs(StrictArgs):
    summary: str = Field(min_length=1, max_length=1000)
    artifactKey: str = Field(min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None


class AppendBatchArgs(StrictArgs):
    artifactKey: str = Field(min_length=1, max_length=200)
    updates: dict[str, JsonValue] = Field(
        description=SAFE_STRUCTURED_WRITE_INSTRUCTION
    )
    summary: str | None = Field(default=None, min_length=1, max_length=1000)


class AppendOutlineTreeArgs(StrictArgs):
    artifactKey: str = Field(min_length=1, max_length=200)
    mode: Literal["replace", "patch"]
    stages: list[dict[str, JsonValue]] = Field(min_length=1)
    summary: str | None = Field(default=None, min_length=1, max_length=1000)


class PutTextBlockArgs(StrictArgs):
    artifactKey: str = Field(min_length=1, max_length=200)
    section: Literal["outlineContent", "worldSetting", "storyBackground"]
    summary: str | None = Field(default=None, min_length=1, max_length=1000)


class PutItemTextBlockArgs(StrictArgs):
    artifactKey: str = Field(min_length=1, max_length=200)
    section: str = Field(min_length=1)
    field: str = Field(min_length=1)
    targetId: str | None = Field(default=None, min_length=1, max_length=200)
    targetKey: str | None = Field(default=None, min_length=1, max_length=200)
    targetName: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_target(self) -> Self:
        if not self.targetId and not self.targetKey and not self.targetName:
            raise ValueError("必须提供一个数组项目定位字段")
        return self


class PutItemTextBlocksArgs(StrictArgs):
    artifactKey: str = Field(min_length=1, max_length=200)
    blocks: list[dict[str, JsonValue]] = Field(min_length=1, max_length=20)


class FinishBuilderArgs(StartBuilderArgs):
    pass


class BeginArtifactArgs(StrictArgs):
    kind: Literal[
        "outline_draft",
        "chapter_draft",
        "lore_draft",
        "revision_brief",
        "beat_plan_draft",
        "chapter_content",
        "beat_plan",
        "freeform_markdown",
    ]
    summary: str = Field(min_length=1, max_length=1000)
    content: str | None = Field(default=None, min_length=1)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None
    # 选区改写沿用 begin_artifact_output，但只允许提交 replacement 和冻结身份。
    operation: Literal["rewrite_chapter_selection", "rewrite_outline_selection"] | None = None
    resourceType: Literal[
        "chapter_content", "outline_content", "outline_node_content"
    ] | None = None
    resourceId: str | None = Field(default=None, min_length=1, max_length=200)
    baseUpdatedAt: str | None = Field(default=None, min_length=1, max_length=100)
    baseContentHash: str | None = Field(default=None, min_length=64, max_length=64)
    selectionStart: NonNegativeInt | None = None
    selectionEnd: NonNegativeInt | None = None
    selectedTextHash: str | None = Field(default=None, min_length=64, max_length=64)
    replacement: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_selection_shape(self) -> Self:
        selection_fields = (
            self.operation,
            self.resourceType,
            self.resourceId,
            self.baseUpdatedAt,
            self.baseContentHash,
            self.selectionStart,
            self.selectionEnd,
            self.selectedTextHash,
            self.replacement,
        )
        if any(value is not None for value in selection_fields) and not all(
            value is not None for value in selection_fields
        ):
            raise ValueError("选区产物必须完整提交 replacement 与冻结身份")
        is_selection = all(value is not None for value in selection_fields)
        if is_selection and self.content is not None:
            raise ValueError("选区产物不得提交完整 content")
        if not is_selection and self.content is None:
            raise ValueError("普通长文本产物必须提交完整 content")
        if self.selectionStart is not None and self.selectionEnd is not None:
            if self.selectionStart >= self.selectionEnd:
                raise ValueError("选区结束位置必须大于开始位置")
        for field_name in ("baseContentHash", "selectedTextHash"):
            value = getattr(self, field_name)
            if value is not None and any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{field_name} 必须是小写 SHA-256")
        return self

    @field_validator("content")
    @classmethod
    def require_non_whitespace_content(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("content 必须包含完整的非空草案正文")
        return value


class ShowArtifactArgs(StrictArgs):
    artifactId: str | None = Field(default=None, min_length=1, max_length=200)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_locator(self) -> Self:
        if not self.artifactId and not self.artifactKey:
            raise ValueError("artifactId 或 artifactKey 至少提供一个")
        return self


class BeatPlanSceneArgs(StrictArgs):
    order: int | None = Field(default=None, strict=True, ge=1)
    goal: str = Field(min_length=1, max_length=1000)
    conflict: str | None = Field(default=None, max_length=1000)
    characters: list[
        Annotated[str, Field(min_length=1, max_length=100)]
    ] = Field(default_factory=list, max_length=50)
    foreshadowingRefs: list[
        Annotated[str, Field(min_length=1, max_length=200)]
    ] | None = Field(default=None, max_length=50)
    estimatedWords: int | None = Field(default=None, strict=True, ge=0)
    acceptanceCriteria: str | None = Field(
        default=None, min_length=1, max_length=1000
    )


class BeatPlanArgs(StrictArgs):
    title: str = Field(min_length=1, max_length=200)
    beatCount: int = Field(strict=True, ge=1, le=50)
    summary: str = Field(min_length=1, max_length=2000)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None
    chapterGoal: str = Field(min_length=1, max_length=1000)
    mainPlotConnection: str | None = Field(default=None, max_length=1000)
    chapterAcceptanceCriteria: str | None = Field(default=None, max_length=1000)
    totalEstimatedWords: int | None = Field(default=None, strict=True, ge=0)
    sceneBeats: list[BeatPlanSceneArgs] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_matching_beat_count(self) -> Self:
        if self.beatCount != len(self.sceneBeats):
            raise ValueError("beatCount 必须等于 sceneBeats 的场景数量")
        return self


class ValidationReportArgs(StrictArgs):
    hasConflicts: bool
    conflicts: list[dict[str, JsonValue]] = Field(max_length=50)


class EvaluationArgs(StrictArgs):
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    verdict: Literal["pass", "revise", "block"]
    summary: str = Field(min_length=1)
    artifactId: str | None = Field(default=None, min_length=1, max_length=200)
    requiredChanges: str | None = Field(default=None, max_length=2000)
    revisionMode: Literal["patch", "rewrite"] | None = None
    patches: list[TextReplacePatch] | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_revision_combination(self) -> Self:
        if self.verdict in {"pass", "block"}:
            if self.revisionMode is not None or self.patches is not None:
                raise ValueError("通过或阻断结论不得携带 revisionMode 或 patches")
            return self
        if self.revisionMode is None:
            raise ValueError("revise 结论必须声明 revisionMode")
        if self.revisionMode == "patch":
            if self.patches is None or not 1 <= len(self.patches) <= 20:
                raise ValueError("patch 模式必须携带 1 到 20 个 patch")
        elif self.patches is not None:
            raise ValueError("rewrite 模式不得携带 patches")
        return self


def control_tools() -> list[ToolDefinition]:
    specs: list[tuple[str, str, type[BaseModel], str, set[str] | None]] = [
        (
            "submit_evaluation",
            "提交复审结论。",
            EvaluationArgs,
            "control.evaluation",
            {"编辑", "校验"},
        ),
        (
            "submit_quality_report",
            "提交结构化质量评分。",
            QualityReportArgs,
            "control.quality",
            None,
        ),
        (
            "propose_updates",
            "提交短小结构化待审核更新。",
            ProposalUpdatesArgs,
            "control.proposal",
            None,
        ),
        ("start_update_builder", "开始批量更新草稿箱。", StartBuilderArgs, "control.builder", None),
        ("append_update_batch", "追加批量结构化更新。", AppendBatchArgs, "control.builder", None),
        (
            "append_outline_tree",
            "追加结构化大纲树。",
            AppendOutlineTreeArgs,
            "control.builder",
            {"剧情"},
        ),
        (
            "put_update_text_block",
            "写入更新草稿箱长文本区块。",
            PutTextBlockArgs,
            "control.builder",
            None,
        ),
        (
            "put_update_item_text_block",
            "写入单个更新项目长文本。",
            PutItemTextBlockArgs,
            "control.builder",
            None,
        ),
        (
            "put_update_item_text_blocks",
            "批量写入更新项目长文本。",
            PutItemTextBlocksArgs,
            "control.builder",
            None,
        ),
        (
            "finish_update_builder",
            "完成批量更新草稿箱。",
            FinishBuilderArgs,
            "control.builder",
            None,
        ),
        (
            "begin_artifact_output",
            "声明本轮正文是长文本待审核草案。",
            BeginArtifactArgs,
            "control.artifact",
            {"设定", "剧情", "写作"},
        ),
        (
            "show_review_artifact",
            "请求前端展示待审核草案。",
            ShowArtifactArgs,
            "control.artifact",
            None,
        ),
        ("submit_beat_plan", "提交结构化章节计划草案。", BeatPlanArgs, "control.beat", None),
        (
            "submit_validation_report",
            "提交一致性冲突报告。",
            ValidationReportArgs,
            "control.validation",
            None,
        ),
    ]
    return [
        ToolDefinition(
            name=name,
            description=description,
            argumentsModel=model,
            permission=control_permission(capability, agent_ids),
            toolKind="control",
            strict=name == "submit_quality_report",
        )
        for name, description, model, capability, agent_ids in specs
    ]

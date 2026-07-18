# ruff: noqa: E501

from __future__ import annotations

from typing import Any, Literal, Self

from inkforge_contracts import ConsistencyQualityReport
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ..short_story.outline import SubmitShortStoryOutlineArgs
from .permissions import control_permission
from .registry import ToolDefinition

AgentId = Literal["设定", "剧情", "写作", "校验", "编辑"]


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QualityReportArgs(ConsistencyQualityReport):
    pass


class ProposalUpdatesArgs(StrictArgs):
    summary: str = Field(min_length=1, max_length=1000)
    updates: dict[str, JsonValue]
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
    updates: dict[str, JsonValue]
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
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None


class ShowArtifactArgs(StrictArgs):
    artifactId: str | None = Field(default=None, min_length=1, max_length=200)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_locator(self) -> Self:
        if not self.artifactId and not self.artifactKey:
            raise ValueError("artifactId 或 artifactKey 至少提供一个")
        return self


class BeatPlanArgs(StrictArgs):
    title: str = Field(min_length=1, max_length=200)
    beatCount: int = Field(ge=1, le=50)
    summary: str = Field(min_length=1, max_length=2000)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None
    chapterGoal: str | None = Field(default=None, min_length=1, max_length=1000)
    mainPlotConnection: str | None = Field(default=None, max_length=1000)
    chapterAcceptanceCriteria: str | None = Field(default=None, max_length=1000)
    totalEstimatedWords: int | None = Field(default=None, ge=0)
    sceneBeats: list[dict[str, JsonValue]] | None = Field(default=None, min_length=1, max_length=50)


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
    patches: list[dict[str, Any]] | None = Field(default=None, max_length=20)


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
        (
            "submit_short_story_outline",
            "提交中短篇完整大纲或基于稳定分节 ID 的局部修改。",
            SubmitShortStoryOutlineArgs,
            "control.short_outline",
            {"剧情"},
        ),
    ]
    return [
        ToolDefinition(
            name=name,
            description=description,
            argumentsModel=model,
            permission=control_permission(capability, agent_ids),
            toolKind="control",
        )
        for name, description, model, capability, agent_ids in specs
    ]

# ruff: noqa: E501

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any, Literal, Self

from inkforge_contracts import ConsistencyQualityReport
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    NonNegativeInt,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

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
    updates: dict[str, JsonValue] = Field(description=SAFE_STRUCTURED_WRITE_INSTRUCTION)
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
    updates: dict[str, JsonValue] = Field(description=SAFE_STRUCTURED_WRITE_INSTRUCTION)
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
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {"required": [field], "properties": {field: {"type": "string", "minLength": 1}}}
                for field in ("targetId", "targetKey", "targetName")
            ]
        },
    )

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
            raise PydanticCustomError("item_target_required", "必须提供一个数组项目定位字段")
        return self


class PutItemTextBlocksArgs(StrictArgs):
    artifactKey: str = Field(min_length=1, max_length=200)
    blocks: list[dict[str, JsonValue]] = Field(min_length=1, max_length=20)


class FinishBuilderArgs(StartBuilderArgs):
    pass


class BeginArtifactArgs(StrictArgs):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["content"],
                    "properties": {
                        "content": {"type": "string", "minLength": 1},
                        **{
                            field: {"type": "null"}
                            for field in (
                                "operation",
                                "resourceType",
                                "resourceId",
                                "baseUpdatedAt",
                                "baseContentHash",
                                "selectionStart",
                                "selectionEnd",
                                "selectedTextHash",
                                "replacement",
                            )
                        },
                    },
                },
                {
                    "required": [
                        "operation",
                        "resourceType",
                        "resourceId",
                        "baseUpdatedAt",
                        "baseContentHash",
                        "selectionStart",
                        "selectionEnd",
                        "selectedTextHash",
                        "replacement",
                    ],
                    "properties": {
                        "content": {"type": "null"},
                        "operation": {"type": "string"},
                        "resourceType": {"type": "string"},
                        **{
                            field: {"type": "string", "minLength": 1}
                            for field in (
                                "resourceId",
                                "baseUpdatedAt",
                                "baseContentHash",
                                "selectedTextHash",
                                "replacement",
                            )
                        },
                        "selectionStart": {"type": "integer"},
                        "selectionEnd": {"type": "integer"},
                    },
                },
            ]
        },
    )

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
    content: str | None = Field(default=None, min_length=1, json_schema_extra={"pattern": r"\S"})
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None
    # 选区改写沿用 begin_artifact_output，但只允许提交 replacement 和冻结身份。
    operation: Literal["rewrite_chapter_selection", "rewrite_outline_selection"] | None = None
    resourceType: Literal["chapter_content", "outline_content", "outline_node_content"] | None = (
        None
    )
    resourceId: str | None = Field(default=None, min_length=1, max_length=200)
    baseUpdatedAt: str | None = Field(default=None, min_length=1, max_length=100)
    baseContentHash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        json_schema_extra={"pattern": "^[0-9a-f]{64}$"},
    )
    selectionStart: NonNegativeInt | None = None
    selectionEnd: NonNegativeInt | None = None
    selectedTextHash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        json_schema_extra={"pattern": "^[0-9a-f]{64}$"},
    )
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
            raise PydanticCustomError(
                "artifact_selection_incomplete", "选区产物必须完整提交 replacement 与冻结身份"
            )
        is_selection = all(value is not None for value in selection_fields)
        if is_selection and self.content is not None:
            raise PydanticCustomError(
                "artifact_selection_content_conflict", "选区产物不得提交完整 content"
            )
        if not is_selection and self.content is None:
            raise PydanticCustomError(
                "artifact_content_required", "普通长文本产物必须提交完整 content"
            )
        if self.selectionStart is not None and self.selectionEnd is not None:
            if self.selectionStart >= self.selectionEnd:
                raise PydanticCustomError(
                    "artifact_selection_range_invalid", "选区结束位置必须大于开始位置"
                )
        for field_name in ("baseContentHash", "selectedTextHash"):
            value = getattr(self, field_name)
            if value is not None and any(char not in "0123456789abcdef" for char in value):
                raise PydanticCustomError(
                    "artifact_selection_hash_invalid", f"{field_name} 必须是小写 SHA-256"
                )
        return self

    @field_validator("content")
    @classmethod
    def require_non_whitespace_content(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise PydanticCustomError(
                "artifact_content_blank", "content 必须包含完整的非空草案正文"
            )
        return value


def artifact_model_schema_for_operation(operation_kind: str | None) -> dict[str, Any] | None:
    """只收窄模型可见产物形状，不替换已注册工具及其最终参数校验。"""

    ordinary = operation_kind in {"write_chapter", "rewrite_scene"}
    selection = operation_kind in {"rewrite_chapter_selection", "rewrite_outline_selection"}
    if not ordinary and not selection:
        return None

    schema = deepcopy(BeginArtifactArgs.model_json_schema())
    properties = schema["properties"]
    common = {"kind", "summary", "artifactKey", "reviewerAgent", "submitForReview"}
    selection_fields = {
        "operation",
        "resourceType",
        "resourceId",
        "baseUpdatedAt",
        "baseContentHash",
        "selectionStart",
        "selectionEnd",
        "selectedTextHash",
        "replacement",
    }
    allowed = common | (selection_fields if selection else {"content"})
    schema["properties"] = {name: value for name, value in properties.items() if name in allowed}
    schema.pop("anyOf", None)
    schema["required"] = [
        "kind",
        "summary",
        *(sorted(selection_fields) if selection else ["content"]),
    ]
    schema["additionalProperties"] = False

    narrowed = schema["properties"]
    narrowed["kind"] = {
        "const": "outline_draft"
        if operation_kind == "rewrite_outline_selection"
        else "chapter_draft"
    }
    if selection:
        narrowed["operation"] = {"const": operation_kind}
        narrowed["resourceType"] = {
            "enum": (
                ["outline_content", "outline_node_content"]
                if operation_kind == "rewrite_outline_selection"
                else ["chapter_content"]
            )
        }
        for name in selection_fields - {"operation", "resourceType"}:
            narrowed[name] = _non_null_schema(narrowed[name])
    else:
        narrowed["content"] = _non_null_schema(narrowed["content"])
    return schema


def _non_null_schema(value: dict[str, Any]) -> dict[str, Any]:
    branches = value.get("anyOf")
    if not isinstance(branches, list):
        return value
    selected = next(branch for branch in branches if branch.get("type") != "null")
    return {
        **{key: item for key, item in value.items() if key not in {"anyOf", "default"}},
        **selected,
    }


class ShowArtifactArgs(StrictArgs):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {"required": [field], "properties": {field: {"type": "string", "minLength": 1}}}
                for field in ("artifactId", "artifactKey")
            ]
        },
    )

    artifactId: str | None = Field(default=None, min_length=1, max_length=200)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def require_locator(self) -> Self:
        if not self.artifactId and not self.artifactKey:
            raise PydanticCustomError(
                "artifact_locator_required", "artifactId 或 artifactKey 至少提供一个"
            )
        return self


class BeatPlanSceneArgs(StrictArgs):
    order: int | None = Field(default=None, strict=True, ge=1)
    goal: str = Field(min_length=1, max_length=1000)
    conflict: str | None = Field(default=None, max_length=1000)
    characters: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=50
    )
    foreshadowingRefs: list[Annotated[str, Field(min_length=1, max_length=200)]] | None = Field(
        default=None, max_length=50
    )
    estimatedWords: int | None = Field(default=None, strict=True, ge=0)
    acceptanceCriteria: str | None = Field(default=None, min_length=1, max_length=1000)


class BeatPlanFields(StrictArgs):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=2000)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None
    chapterGoal: str = Field(min_length=1, max_length=1000)
    mainPlotConnection: str | None = Field(default=None, max_length=1000)
    chapterAcceptanceCriteria: str | None = Field(default=None, max_length=1000)
    totalEstimatedWords: int | None = Field(default=None, strict=True, ge=0)
    sceneBeats: list[BeatPlanSceneArgs] = Field(min_length=1, max_length=50)


class BeatPlanArgs(BeatPlanFields):
    beatCount: int = Field(strict=True, ge=1, le=50)

    @model_validator(mode="after")
    def require_matching_beat_count(self) -> Self:
        if self.beatCount != len(self.sceneBeats):
            raise ValueError("beatCount 必须等于 sceneBeats 的场景数量")
        return self


class BeatPlanInputArgs(BeatPlanFields):
    """模型只提交场景数组，计数由校验后的数组确定性派生。"""

    @computed_field(return_type=int)  # type: ignore[prop-decorator]
    @property
    def beatCount(self) -> int:
        return len(self.sceneBeats)


class ValidationReportArgs(StrictArgs):
    hasConflicts: bool
    conflicts: list[dict[str, JsonValue]] = Field(max_length=50)


class EvaluationArgs(StrictArgs):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["verdict"],
                    "properties": {
                        "verdict": {"enum": ["pass", "block"]},
                        "revisionMode": {"type": "null"},
                        "patches": {"type": "null"},
                    },
                },
                {
                    "required": ["verdict", "revisionMode", "patches"],
                    "properties": {
                        "verdict": {"const": "revise"},
                        "revisionMode": {"const": "patch"},
                        "patches": {"type": "array", "minItems": 1, "maxItems": 20},
                    },
                },
                {
                    "required": ["verdict", "revisionMode"],
                    "properties": {
                        "verdict": {"const": "revise"},
                        "revisionMode": {"const": "rewrite"},
                        "patches": {"type": "null"},
                    },
                },
            ]
        },
    )

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
                raise PydanticCustomError(
                    "evaluation_revision_combination_invalid",
                    "通过或阻断结论不得携带 revisionMode 或 patches",
                )
            return self
        if self.revisionMode is None:
            raise PydanticCustomError(
                "evaluation_revision_combination_invalid",
                "revise 结论必须声明 revisionMode",
            )
        if self.revisionMode == "patch":
            if self.patches is None or not 1 <= len(self.patches) <= 20:
                raise PydanticCustomError(
                    "evaluation_revision_combination_invalid",
                    "patch 模式必须携带 1 到 20 个 patch",
                )
        elif self.patches is not None:
            raise PydanticCustomError(
                "evaluation_revision_combination_invalid",
                "rewrite 模式不得携带 patches",
            )
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
            modelArgumentsModel=(BeatPlanInputArgs if name == "submit_beat_plan" else None),
            permission=control_permission(capability, agent_ids),
            toolKind="control",
            strict=True if name == "submit_quality_report" else None,
        )
        for name, description, model, capability, agent_ids in specs
    ]

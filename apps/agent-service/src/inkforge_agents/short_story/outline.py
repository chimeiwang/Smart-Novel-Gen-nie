from __future__ import annotations

import hashlib
from typing import Annotated, Any, Literal, Self

from inkforge_contracts import (
    ShortStoryAnchors,
    ShortStoryOutlineDraft,
    ShortStoryOutlineSection,
)
from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator
from pydantic.json_schema import DEFAULT_REF_TEMPLATE, GenerateJsonSchema, JsonSchemaMode


class _StrictSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShortOutlineSectionInput(_StrictSubmission):
    title: str = Field(min_length=1, max_length=200)
    events: str = Field(min_length=1)

    @field_validator("title", "events")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("中短篇大纲分节内容不能为空")
        return normalized


class ShortOutlineFullSubmission(_StrictSubmission):
    mode: Literal["full"] = "full"
    corePremise: str = Field(min_length=1)
    anchors: ShortStoryAnchors
    sections: list[ShortOutlineSectionInput] = Field(min_length=1)
    changeSummary: str = Field(min_length=1, max_length=2000)

    @field_validator("corePremise", "changeSummary")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("中短篇大纲提交文本不能为空")
        return normalized


class ShortOutlineUpdateOperation(_StrictSubmission):
    operation: Literal["update"]
    sectionId: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    events: str | None = Field(default=None, min_length=1)

    @field_validator("sectionId", "title", "events")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("更新分节字段不能为空")
        return normalized

    @model_validator(mode="after")
    def require_changed_field(self) -> Self:
        if self.title is None and self.events is None:
            raise ValueError("update 至少提供 title 或 events")
        return self


class ShortOutlineInsertOperation(_StrictSubmission):
    operation: Literal["insert"]
    beforeSectionId: str | None = Field(default=None, min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    events: str = Field(min_length=1)

    @field_validator("beforeSectionId", "title", "events")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("插入分节字段不能为空")
        return normalized


class ShortOutlineMoveOperation(_StrictSubmission):
    operation: Literal["move"]
    sectionId: str = Field(min_length=1, max_length=128)
    beforeSectionId: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("sectionId", "beforeSectionId")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("移动分节标识不能为空")
        return normalized

    @model_validator(mode="after")
    def reject_self_reference(self) -> Self:
        if self.beforeSectionId == self.sectionId:
            raise ValueError("分节不能移动到自身之前")
        return self


class ShortOutlineDeleteOperation(_StrictSubmission):
    operation: Literal["delete"]
    sectionId: str = Field(min_length=1, max_length=128)

    @field_validator("sectionId")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("删除分节标识不能为空")
        return normalized


ShortOutlineSectionOperation = Annotated[
    ShortOutlineUpdateOperation
    | ShortOutlineInsertOperation
    | ShortOutlineMoveOperation
    | ShortOutlineDeleteOperation,
    Field(discriminator="operation"),
]


class ShortOutlinePatchSubmission(_StrictSubmission):
    mode: Literal["patch"]
    sourceRevision: int = Field(ge=1)
    corePremise: str | None = Field(default=None, min_length=1)
    anchors: ShortStoryAnchors | None = None
    sectionOperations: list[ShortOutlineSectionOperation] = Field(default_factory=list)
    changeSummary: str = Field(min_length=1, max_length=2000)

    @field_validator("corePremise", "changeSummary")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("中短篇大纲修改文本不能为空")
        return normalized

    @model_validator(mode="after")
    def require_candidate_change(self) -> Self:
        if (
            self.corePremise is None
            and self.anchors is None
            and not self.sectionOperations
        ):
            raise ValueError("patch 至少提供一项候选变化")
        return self


ShortOutlineSubmission = Annotated[
    ShortOutlineFullSubmission | ShortOutlinePatchSubmission,
    Field(discriminator="mode"),
]


class SubmitShortStoryOutlineArgs(RootModel[ShortOutlineSubmission]):
    """模型提交中短篇大纲时使用的严格判别联合。"""

    @classmethod
    def model_json_schema(
        cls,
        by_alias: bool = True,
        ref_template: str = DEFAULT_REF_TEMPLATE,
        schema_generator: type[GenerateJsonSchema] = GenerateJsonSchema,
        mode: JsonSchemaMode = "validation",
        *,
        union_format: Literal["any_of", "primitive_type_array"] = "any_of",
    ) -> dict[str, Any]:
        schema = super().model_json_schema(
            by_alias=by_alias,
            ref_template=ref_template,
            schema_generator=schema_generator,
            mode=mode,
            union_format=union_format,
        )
        # OpenAI 兼容接口要求函数参数的顶层必须显式声明为对象。
        return {**schema, "type": "object"}


def build_initial_short_outline(
    submission: ShortOutlineFullSubmission,
    *,
    original_inspiration: str,
    artifact_key: str,
) -> ShortStoryOutlineDraft:
    """用 Core 灵感和服务端分节 ID 构建首版完整大纲。"""

    inspiration = original_inspiration.strip()
    if not inspiration:
        raise ValueError("SHORT_OUTLINE_MERGE_FAILED：Core 原始灵感为空")
    if not artifact_key:
        raise ValueError("SHORT_OUTLINE_MERGE_FAILED：草案稳定标识为空")
    sections = [
        ShortStoryOutlineSection(
            id=_section_id(
                artifact_key,
                "initial",
                str(index),
                section.title,
                section.events,
            ),
            title=section.title,
            events=section.events,
        )
        for index, section in enumerate(submission.sections)
    ]
    return ShortStoryOutlineDraft(
        originalInspiration=inspiration,
        corePremise=submission.corePremise,
        anchors=submission.anchors,
        sections=sections,
        changeSummary=submission.changeSummary,
        anchorChanges=[],
    )


def merge_short_outline_patch(
    submission: ShortOutlinePatchSubmission,
    *,
    current: ShortStoryOutlineDraft,
    artifact_id: str,
    current_revision: int,
) -> ShortStoryOutlineDraft:
    """按模型声明顺序把局部 patch 合并为新的完整权威大纲。"""

    if submission.sourceRevision != current_revision:
        raise ValueError(
            "SHORT_OUTLINE_MERGE_FAILED：sourceRevision 与当前 revision 不一致"
        )
    if not artifact_id:
        raise ValueError("SHORT_OUTLINE_MERGE_FAILED：缺少权威草案标识")

    sections = [section.model_copy(deep=True) for section in current.sections]
    last_inserted_before: dict[str, str] = {}
    for operation_index, operation in enumerate(submission.sectionOperations):
        if isinstance(operation, ShortOutlineUpdateOperation):
            index = _require_section_index(sections, operation.sectionId)
            existing = sections[index]
            sections[index] = ShortStoryOutlineSection(
                id=existing.id,
                title=operation.title if operation.title is not None else existing.title,
                events=operation.events if operation.events is not None else existing.events,
            )
            last_inserted_before.clear()
            continue
        if isinstance(operation, ShortOutlineInsertOperation):
            new_section = ShortStoryOutlineSection(
                id=_section_id(
                    artifact_id,
                    str(current_revision),
                    str(operation_index),
                    operation.title,
                    operation.events,
                ),
                title=operation.title,
                events=operation.events,
            )
            if any(section.id == new_section.id for section in sections):
                raise ValueError("SHORT_OUTLINE_MERGE_FAILED：新分节稳定 ID 冲突")
            if operation.beforeSectionId is None:
                sections.append(new_section)
            else:
                before_index = _require_section_index(
                    sections, operation.beforeSectionId
                )
                previous_insert_id = last_inserted_before.get(operation.beforeSectionId)
                if previous_insert_id is not None:
                    previous_index = _require_section_index(sections, previous_insert_id)
                    if previous_index < before_index:
                        before_index = previous_index + 1
                sections.insert(before_index, new_section)
                last_inserted_before[operation.beforeSectionId] = new_section.id
            continue
        if isinstance(operation, ShortOutlineMoveOperation):
            source_index = _require_section_index(sections, operation.sectionId)
            moving = sections.pop(source_index)
            if operation.beforeSectionId is None:
                sections.append(moving)
            else:
                target_index = _require_section_index(sections, operation.beforeSectionId)
                sections.insert(target_index, moving)
            last_inserted_before.clear()
            continue
        index = _require_section_index(sections, operation.sectionId)
        sections.pop(index)
        if not sections:
            raise ValueError("SHORT_OUTLINE_MERGE_FAILED：大纲至少保留一个分节")
        last_inserted_before.clear()

    anchors = submission.anchors or current.anchors
    merged = ShortStoryOutlineDraft(
        originalInspiration=current.originalInspiration,
        corePremise=submission.corePremise or current.corePremise,
        anchors=anchors,
        sections=sections,
        changeSummary=submission.changeSummary,
        anchorChanges=_anchor_changes(current.anchors, anchors),
    )
    if _semantic_outline(merged) == _semantic_outline(current):
        raise ValueError("SHORT_OUTLINE_MERGE_FAILED：patch 没有产生实际内容变化")
    return merged


def _require_section_index(
    sections: list[ShortStoryOutlineSection], section_id: str
) -> int:
    for index, section in enumerate(sections):
        if section.id == section_id:
            return index
    raise ValueError(f"SHORT_OUTLINE_MERGE_FAILED：未知分节 ID {section_id}")


def _section_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"short-section-{digest}"


def _anchor_changes(
    previous: ShortStoryAnchors, current: ShortStoryAnchors
) -> list[str]:
    changes: list[str] = []
    for field, label in (
        ("mustKeep", "必须保留"),
        ("confirmed", "已经确认"),
        ("avoid", "明确不要"),
    ):
        old_items = getattr(previous, field)
        new_items = getattr(current, field)
        changes.extend(
            f"{label}：新增「{item}」" for item in new_items if item not in old_items
        )
        changes.extend(
            f"{label}：移除「{item}」" for item in old_items if item not in new_items
        )
    return changes


def _semantic_outline(outline: ShortStoryOutlineDraft) -> dict[str, object]:
    return {
        "originalInspiration": outline.originalInspiration,
        "corePremise": outline.corePremise,
        "anchors": outline.anchors.model_dump(mode="json"),
        "sections": [section.model_dump(mode="json") for section in outline.sections],
    }

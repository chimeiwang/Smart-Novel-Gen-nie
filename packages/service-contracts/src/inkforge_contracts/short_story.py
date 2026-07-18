from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ShortStoryContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShortStoryOutlineSection(ShortStoryContract):
    id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    events: str = Field(min_length=1)

    @field_validator("id", "title", "events")
    @classmethod
    def strip_non_empty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("分节字段不能为空")
        return normalized


class ShortStoryAnchors(ShortStoryContract):
    mustKeep: list[str] = Field(default_factory=list)
    confirmed: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)

    @field_validator("mustKeep", "confirmed", "avoid")
    @classmethod
    def normalize_anchor_items(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("创作锚点不能包含空项")
        return normalized


def _render_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- （无）"


def render_short_story_outline(
    *,
    original_inspiration: str,
    core_premise: str,
    anchors: ShortStoryAnchors,
    sections: list[ShortStoryOutlineSection],
) -> str:
    """根据权威结构化字段生成稳定、完整且适合用户通读的大纲。"""

    parts = [
        "# 原始灵感",
        original_inspiration.strip(),
        "# 核心前提",
        core_premise.strip(),
        "# 创作锚点",
        "### 必须保留",
        _render_list(anchors.mustKeep),
        "### 已经确认",
        _render_list(anchors.confirmed),
        "### 明确不要",
        _render_list(anchors.avoid),
        "# 分节大纲",
    ]
    for index, section in enumerate(sections, start=1):
        parts.extend((f"## 第 {index} 节：{section.title}", section.events))
    return "\n\n".join(parts)


class ShortStoryOutlineDraft(ShortStoryContract):
    kind: Literal["outline_draft"] = "outline_draft"
    storyLengthProfile: Literal["short_medium"] = "short_medium"
    originalInspiration: str = Field(min_length=1)
    corePremise: str = Field(min_length=1)
    anchors: ShortStoryAnchors
    sections: list[ShortStoryOutlineSection] = Field(min_length=1)
    content: str = ""
    changeSummary: str = ""
    anchorChanges: list[str] = Field(default_factory=list)

    @field_validator("originalInspiration", "corePremise")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("中短篇大纲必填文本不能为空")
        return normalized

    @field_validator("changeSummary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        return value.strip()

    @field_validator("anchorChanges")
    @classmethod
    def normalize_anchor_changes(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("锚点变更不能包含空项")
        return normalized

    @model_validator(mode="after")
    def validate_sections_and_render_content(self) -> ShortStoryOutlineDraft:
        section_ids = [section.id for section in self.sections]
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("分节 ID 必须唯一")
        self.content = render_short_story_outline(
            original_inspiration=self.originalInspiration,
            core_premise=self.corePremise,
            anchors=self.anchors,
            sections=self.sections,
        )
        return self

    def semantic_content_signature(self) -> str:
        """计算排除版本说明字段后的稳定内容签名。"""

        canonical = json.dumps(
            self.model_dump(
                mode="json",
                exclude={"changeSummary", "anchorChanges"},
            ),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ShortStoryDraftMetadata(ShortStoryContract):
    sourceOutlineArtifactId: str = Field(min_length=1, max_length=256)
    sourceOutlineRevision: int = Field(ge=1)
    sourceOutlineHash: str = Field(min_length=64, max_length=64)
    targetWordCount: int = Field(ge=6000, le=80000)
    actualWordCount: int = Field(ge=0)
    targetChapterId: str = Field(min_length=1, max_length=256)
    baseChapterHash: str = Field(min_length=64, max_length=64)

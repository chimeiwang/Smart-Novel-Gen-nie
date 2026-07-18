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
    generationCommandId: str = Field(min_length=1, max_length=256)
    automaticRewriteCount: int = Field(ge=0, le=1)
    generationReason: Literal["user_request", "automatic_rewrite"]

    @field_validator("generationCommandId")
    @classmethod
    def normalize_generation_command_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("正文生成命令 ID 不能为空")
        return normalized


SHORT_STORY_IGNORED_TEXT_CHARACTERS = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_TEXT_LENGTH_TRANSLATION = str.maketrans("", "", SHORT_STORY_IGNORED_TEXT_CHARACTERS)


def count_short_story_text_length(text: str) -> int:
    """复用 Web countTextLength 语义：忽略 Unicode 空白并按码点计数。"""

    return len(text.translate(_TEXT_LENGTH_TRANSLATION))


def canonical_short_outline_hash(outline: ShortStoryOutlineDraft) -> str:
    """计算包含版本说明在内的权威完整大纲 SHA-256。"""

    canonical = json.dumps(
        outline.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ShortStoryChapterDraft(ShortStoryContract):
    kind: Literal["chapter_draft"] = "chapter_draft"
    storyLengthProfile: Literal["short_medium"] = "short_medium"
    content: str = Field(min_length=1)
    metadata: ShortStoryDraftMetadata

    @model_validator(mode="after")
    def validate_content_word_count(self) -> ShortStoryChapterDraft:
        actual = count_short_story_text_length(self.content)
        if actual == 0:
            raise ValueError("中短篇完整正文不能为空")
        if self.metadata.actualWordCount != actual:
            raise ValueError("正文实际字数与 metadata.actualWordCount 不一致")
        return self

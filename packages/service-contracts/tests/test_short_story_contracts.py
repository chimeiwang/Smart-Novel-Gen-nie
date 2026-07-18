from __future__ import annotations

import pytest
from inkforge_contracts import (
    ShortStoryAnchors,
    ShortStoryDraftMetadata,
    ShortStoryOutlineDraft,
    ShortStoryOutlineSection,
    render_short_story_outline,
)
from pydantic import ValidationError


def _outline(**overrides: object) -> ShortStoryOutlineDraft:
    values: dict[str, object] = {
        "kind": "outline_draft",
        "storyLengthProfile": "short_medium",
        "originalInspiration": "一名守夜人在天亮前收到自己的讣告。",
        "corePremise": "守夜人必须在黎明前找出写讣告的人。",
        "anchors": {
            "mustKeep": ["讣告来自未来"],
            "confirmed": ["结局发生在钟楼"],
            "avoid": ["不能用梦境解释"],
        },
        "sections": [
            {"id": "sec-opening", "title": "讣告", "events": "守夜人收到讣告。"},
            {"id": "sec-ending", "title": "黎明", "events": "他在钟楼作出选择。"},
        ],
        "content": "这段输入会被结构化字段重建。",
        "changeSummary": "首次生成",
        "anchorChanges": [],
    }
    values.update(overrides)
    return ShortStoryOutlineDraft.model_validate(values)


def test_outline_contract_rebuilds_deterministic_human_readable_content() -> None:
    outline = _outline()

    assert outline.content == render_short_story_outline(
        original_inspiration=outline.originalInspiration,
        core_premise=outline.corePremise,
        anchors=outline.anchors,
        sections=outline.sections,
    )
    assert "## 第 1 节：讣告" in outline.content
    assert "守夜人收到讣告。" in outline.content
    assert ShortStoryOutlineDraft.model_validate(outline.model_dump()).content == outline.content


def test_outline_contract_rejects_duplicate_section_ids_and_length_fields() -> None:
    duplicate_sections = [
        {"id": "same", "title": "开头", "events": "发生甲。"},
        {"id": "same", "title": "结尾", "events": "发生乙。"},
    ]
    with pytest.raises(ValidationError, match="分节 ID"):
        _outline(sections=duplicate_sections)

    with pytest.raises(ValidationError):
        ShortStoryOutlineSection.model_validate(
            {"id": "sec-1", "title": "开头", "events": "发生甲。", "targetWordCount": 1000}
        )

    with pytest.raises(ValidationError):
        _outline(fixedSectionCount=8)


def test_short_story_contracts_are_strict_and_validate_metadata() -> None:
    anchors = ShortStoryAnchors(mustKeep=[], confirmed=[], avoid=[])
    assert anchors.model_dump() == {"mustKeep": [], "confirmed": [], "avoid": []}

    metadata = ShortStoryDraftMetadata(
        sourceOutlineArtifactId="artifact-1",
        sourceOutlineRevision=3,
        sourceOutlineHash="a" * 64,
        targetWordCount=6000,
        actualWordCount=6123,
        targetChapterId="chapter-1",
        baseChapterHash="b" * 64,
    )
    assert metadata.sourceOutlineRevision == 3

    with pytest.raises(ValidationError):
        ShortStoryDraftMetadata.model_validate({**metadata.model_dump(), "targetWordCount": 80001})

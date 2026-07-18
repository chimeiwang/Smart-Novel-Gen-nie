from __future__ import annotations

import pytest
from inkforge_agents.short_story.outline import (
    ShortOutlineFullSubmission,
    ShortOutlinePatchSubmission,
    build_initial_short_outline,
    merge_short_outline_patch,
)
from inkforge_contracts import ShortStoryOutlineDraft


def _full() -> ShortOutlineFullSubmission:
    return ShortOutlineFullSubmission.model_validate(
        {
            "mode": "full",
            "corePremise": "一座城市每天会忘记一个人。",
            "anchors": {
                "mustKeep": ["结尾揭示被遗忘者主动选择消失"],
                "confirmed": ["单一主线"],
                "avoid": ["梦境反转"],
            },
            "sections": [
                {"title": "失踪", "events": "记者发现所有人忘了同事。"},
                {"title": "追索", "events": "记者追查城市记忆规则。"},
                {"title": "选择", "events": "记者理解同事的选择并完成告别。"},
            ],
            "changeSummary": "根据原始灵感形成完整大纲。",
        }
    )


def _draft() -> ShortStoryOutlineDraft:
    return build_initial_short_outline(
        _full(),
        original_inspiration="城市每天忘记一个人",
        artifact_key="artifact-stable",
    )


def test_initial_outline_uses_authoritative_inspiration_and_deterministic_ids() -> None:
    first = _draft()
    second = _draft()

    assert first.originalInspiration == "城市每天忘记一个人"
    assert [section.id for section in first.sections] == [
        section.id for section in second.sections
    ]
    assert all(section.id.startswith("short-section-") for section in first.sections)
    assert len(set(section.id for section in first.sections)) == 3
    assert "第 3 节：选择" in first.content
    assert first.anchorChanges == []


def test_patch_updates_inserts_moves_and_deletes_in_declared_order() -> None:
    current = _draft()
    first_id, second_id, third_id = [section.id for section in current.sections]
    patch = ShortOutlinePatchSubmission.model_validate(
        {
            "mode": "patch",
            "sourceRevision": 4,
            "corePremise": "城市每天抹去一名自愿者的存在。",
            "anchors": {
                "mustKeep": ["结尾揭示被遗忘者主动选择消失", "记者必须付出代价"],
                "confirmed": ["单一主线"],
                "avoid": [],
            },
            "sectionOperations": [
                {"operation": "update", "sectionId": second_id, "events": "记者发现遗忘名单。"},
                {
                    "operation": "insert",
                    "beforeSectionId": third_id,
                    "title": "名单",
                    "events": "记者确认同事是自愿者。",
                },
                {
                    "operation": "insert",
                    "beforeSectionId": third_id,
                    "title": "代价",
                    "events": "记者决定保留一份无人能读的记录。",
                },
                {"operation": "move", "sectionId": first_id, "beforeSectionId": None},
                {"operation": "delete", "sectionId": third_id},
            ],
            "changeSummary": "加强中段线索，并把开场事件移到结尾回扣。",
        }
    )

    merged = merge_short_outline_patch(
        patch,
        current=current,
        artifact_id="artifact-1",
        current_revision=4,
    )

    assert [section.title for section in merged.sections] == ["追索", "名单", "代价", "失踪"]
    assert merged.sections[0].id == second_id
    assert merged.sections[-1].id == first_id
    assert merged.sections[0].events == "记者发现遗忘名单。"
    assert merged.originalInspiration == current.originalInspiration
    assert merged.corePremise == "城市每天抹去一名自愿者的存在。"
    assert merged.anchorChanges == [
        "必须保留：新增「记者必须付出代价」",
        "明确不要：移除「梦境反转」",
    ]


def test_inserted_section_ids_are_deterministic_for_same_revision_and_operation() -> None:
    current = _draft()
    patch = ShortOutlinePatchSubmission.model_validate(
        {
            "mode": "patch",
            "sourceRevision": 2,
            "sectionOperations": [
                {"operation": "insert", "title": "新节", "events": "新增事件。"}
            ],
            "changeSummary": "增加收束。",
        }
    )

    first = merge_short_outline_patch(
        patch, current=current, artifact_id="artifact-1", current_revision=2
    )
    second = merge_short_outline_patch(
        patch, current=current, artifact_id="artifact-1", current_revision=2
    )

    assert first.sections[-1].id == second.sections[-1].id
    assert first.sections[-1].id not in {section.id for section in current.sections}


def test_same_anchor_inserts_keep_declared_order_across_interleaved_update() -> None:
    current = _draft()
    anchor_id = current.sections[1].id
    updated_id = current.sections[2].id
    patch = ShortOutlinePatchSubmission.model_validate(
        {
            "mode": "patch",
            "sourceRevision": 5,
            "sectionOperations": [
                {
                    "operation": "insert",
                    "beforeSectionId": anchor_id,
                    "title": "线索甲",
                    "events": "先发现第一条线索。",
                },
                {
                    "operation": "update",
                    "sectionId": updated_id,
                    "events": "更新结局事件。",
                },
                {
                    "operation": "insert",
                    "beforeSectionId": anchor_id,
                    "title": "线索乙",
                    "events": "再发现第二条线索。",
                },
            ],
            "changeSummary": "交错更新时仍保持插入声明顺序。",
        }
    )

    merged = merge_short_outline_patch(
        patch, current=current, artifact_id="artifact-1", current_revision=5
    )

    assert [section.title for section in merged.sections] == [
        "失踪",
        "线索甲",
        "线索乙",
        "追索",
        "选择",
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "mode": "patch",
                "sourceRevision": 3,
                "sectionOperations": [{"operation": "delete", "sectionId": "unknown"}],
                "changeSummary": "删除。",
            },
            "未知分节",
        ),
        (
            {
                "mode": "patch",
                "sourceRevision": 3,
                "sectionOperations": [
                    {
                        "operation": "move",
                        "sectionId": "same",
                        "beforeSectionId": "same",
                    }
                ],
                "changeSummary": "移动。",
            },
            "不能移动到自身之前",
        ),
    ],
)
def test_patch_rejects_unknown_and_self_referential_section_ids(
    payload: dict[str, object], message: str
) -> None:
    current = _draft()
    if payload["sectionOperations"][0].get("sectionId") == "same":  # type: ignore[index,union-attr]
        section_id = current.sections[0].id
        payload["sectionOperations"] = [
            {
                "operation": "move",
                "sectionId": section_id,
                "beforeSectionId": section_id,
            }
        ]
    with pytest.raises(ValueError, match=message):
        patch = ShortOutlinePatchSubmission.model_validate(payload)
        merge_short_outline_patch(
            patch, current=current, artifact_id="artifact-1", current_revision=3
        )


def test_patch_rejects_revision_mismatch_deleting_all_sections_and_semantic_noop() -> None:
    current = _draft()
    mismatch = ShortOutlinePatchSubmission.model_validate(
        {
            "mode": "patch",
            "sourceRevision": 2,
            "sectionOperations": [
                {"operation": "update", "sectionId": current.sections[0].id, "title": "改名"}
            ],
            "changeSummary": "改名。",
        }
    )
    with pytest.raises(ValueError, match="revision"):
        merge_short_outline_patch(
            mismatch, current=current, artifact_id="artifact-1", current_revision=3
        )

    delete_all = ShortOutlinePatchSubmission.model_validate(
        {
            "mode": "patch",
            "sourceRevision": 3,
            "sectionOperations": [
                {"operation": "delete", "sectionId": section.id}
                for section in current.sections
            ],
            "changeSummary": "删除全部。",
        }
    )
    with pytest.raises(ValueError, match="至少保留一个分节"):
        merge_short_outline_patch(
            delete_all, current=current, artifact_id="artifact-1", current_revision=3
        )

    noop = ShortOutlinePatchSubmission.model_validate(
        {
            "mode": "patch",
            "sourceRevision": 3,
            "corePremise": current.corePremise,
            "changeSummary": "仅修改摘要。",
        }
    )
    with pytest.raises(ValueError, match="没有产生实际内容变化"):
        merge_short_outline_patch(
            noop, current=current, artifact_id="artifact-1", current_revision=3
        )

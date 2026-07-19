from typing import Any

import pytest
from inkforge_agents.graph.context import build_operation_context, parse_chapter_target
from inkforge_agents.operations.definitions import OPERATION_DEFINITIONS


def _core_context() -> dict[str, Any]:
    return {
        "workspace": {
            "novel": {
                "id": "novel-1",
                "name": "长夜",
                "summary": "寻找失落王城",
                "storyProgress": "主角进入边境",
            },
            "currentChapterId": "chapter-2",
            "chapters": [
                {"id": "chapter-1", "title": "前夜", "order": 1, "content": "前章正文"},
                {"id": "chapter-2", "title": "入城", "order": 2, "content": "当前正文"},
                {"id": "chapter-3", "title": "追兵", "order": 3, "content": "后章正文"},
            ],
            "characters": [
                {
                    "id": "character-1",
                    "name": "林舟",
                    "identity": "逃亡者",
                    "currentStatus": "active",
                    "statusNote": "负伤",
                    "faction": {"id": "faction-1", "name": "巡夜司"},
                    "background": "角色背景详情",
                    "appearance": "角色外貌详情",
                },
                {
                    "id": "character-2",
                    "name": "无关角色",
                    "identity": "商人",
                    "currentStatus": "active",
                    "statusNote": None,
                    "background": "无关详情",
                },
            ],
            "items": [
                {
                    "id": "item-1",
                    "name": "墨印",
                    "type": "信物",
                    "rarity": "稀有",
                    "owner": {"id": "character-1", "name": "林舟"},
                    "effect": "物品效果详情",
                    "description": "物品描述详情",
                }
            ],
            "locations": [
                {
                    "id": "location-1",
                    "name": "边城",
                    "type": "关隘",
                    "parentId": None,
                    "description": "地点描述详情",
                }
            ],
            "factions": [
                {
                    "id": "faction-1",
                    "name": "巡夜司",
                    "type": "官署",
                    "baseId": "location-1",
                    "description": "势力描述详情",
                }
            ],
            "glossaries": [
                {
                    "id": "term-1",
                    "term": "夜潮",
                    "category": "灾变",
                    "definition": "术语定义详情",
                }
            ],
            "storyBackground": {"id": "background-1", "content": "背景全文"},
            "worldSetting": {"id": "world-1", "content": "世界全文"},
            "outline": {"id": "outline-1", "content": "完整总纲"},
            "outlineNodes": [
                {
                    "id": "group-1",
                    "kind": "chapter_group",
                    "title": "逃亡篇",
                    "content": "完整节点",
                }
            ],
            "plotProgress": {"id": "plot-1", "summary": "进入边境"},
            "references": [{"id": "reference-1", "title": "资料", "content": "完整资料"}],
        },
        "planning": {
            "taskId": "task-1",
            "novelId": "novel-1",
            "chapterId": "chapter-2",
            "chapterOrder": 2,
            "targetWordCount": 4000,
            "chapterGoal": {"narrativeGoal": "突破封锁"},
            "approvedBeatPlan": {
                "chapterGoal": "入城",
                "sceneBeats": [{"goal": "过关", "characters": '["林舟"]'}],
            },
            "chapterGroup": {"id": "group-1", "title": "逃亡篇", "content": "章节组全文"},
            "outlinePath": [{"id": "stage-1", "kind": "stage", "title": "第一幕"}],
            "foreshadowingSummaries": [
                {
                    "id": "foreshadowing-1",
                    "name": "断裂墨印",
                    "status": "active",
                    "plantedAt": "第一章",
                    "expectedPayoff": "第五章",
                    "payoffAt": None,
                    "plantedContent": "伏笔种下详情",
                }
            ],
            "activeArtifact": {"id": "artifact-1", "payload": {"kind": "chapter_draft"}},
            "conversationHistory": [{"role": "user", "content": "旧请求"}],
            "userMessage": "当前请求",
            "graphState": {"runtimeContext": {"runResource": {"runId": "旧运行"}}},
        },
    }


@pytest.mark.parametrize(
    ("operation_kind", "expected", "unexpected"),
    [
        ("answer_question", {"task", "novel", "chapter"}, {"loreIndex", "outline"}),
        ("create_lore", {"task", "novel", "loreIndex"}, {"outline", "beatPlan"}),
        ("create_outline", {"task", "novel", "outline"}, {"currentChapter", "beatPlan"}),
        (
            "write_chapter",
            {
                "task",
                "novel",
                "currentChapter",
                "adjacentChapters",
                "beatPlan",
                "relatedCharacters",
                "outlinePath",
            },
            {"reviewObject", "loreIndex", "outline"},
        ),
        ("review_chapter", {"task", "novel", "currentChapter"}, {"activeArtifact"}),
    ],
)
def test_context_strategy_selects_minimal_projection(
    operation_kind: str,
    expected: set[str],
    unexpected: set[str],
) -> None:
    context = build_operation_context(
        OPERATION_DEFINITIONS[operation_kind],  # type: ignore[index]
        _core_context(),
    )

    assert expected <= context.keys()
    assert unexpected.isdisjoint(context)
    serialized = repr(context)
    for forbidden in ("userMessage", "conversationHistory", "graphState", "activeArtifact"):
        assert forbidden not in serialized
    assert "完整资料" not in serialized
    assert "详情" not in serialized


def test_lore_context_uses_real_workspace_overview_fields() -> None:
    context = build_operation_context(OPERATION_DEFINITIONS["create_lore"], _core_context())
    index = context["loreIndex"]

    assert index["characters"] == [
        {
            "id": "character-1",
            "name": "林舟",
            "identity": "逃亡者",
            "currentStatus": "active",
            "statusNote": "负伤",
            "faction": {"id": "faction-1", "name": "巡夜司"},
        },
        {
            "id": "character-2",
            "name": "无关角色",
            "identity": "商人",
            "currentStatus": "active",
            "statusNote": None,
        },
    ]
    assert index["items"] == [
        {
            "id": "item-1",
            "name": "墨印",
            "type": "信物",
            "rarity": "稀有",
            "owner": {"id": "character-1", "name": "林舟"},
        }
    ]
    assert index["locations"] == [
        {"id": "location-1", "name": "边城", "type": "关隘", "parentId": None}
    ]
    assert index["factions"] == [
        {
            "id": "faction-1",
            "name": "巡夜司",
            "type": "官署",
            "baseId": "location-1",
        }
    ]
    assert index["glossaries"] == [
        {"id": "term-1", "term": "夜潮", "category": "灾变"}
    ]


def test_outline_context_contains_complete_high_level_summaries_without_details() -> None:
    context = build_operation_context(
        OPERATION_DEFINITIONS["create_outline"], _core_context()
    )["outline"]

    assert context["outline"]["content"] == "完整总纲"
    assert context["chapterGroup"]["content"] == "章节组全文"
    assert context["foreshadowingSummaries"] == [
        {
            "id": "foreshadowing-1",
            "name": "断裂墨印",
            "status": "active",
            "plantedAt": "第一章",
            "expectedPayoff": "第五章",
            "payoffAt": None,
        }
    ]
    assert "content" not in context["nodes"][0]
    assert "plantedContent" not in repr(context)


def test_chapter_context_only_includes_characters_named_by_approved_beat_plan() -> None:
    context = build_operation_context(
        OPERATION_DEFINITIONS["write_chapter"], _core_context()
    )

    assert context["relatedCharacters"] == [
        {
            "id": "character-1",
            "name": "林舟",
            "identity": "逃亡者",
            "currentStatus": "active",
            "statusNote": "负伤",
            "faction": {"id": "faction-1", "name": "巡夜司"},
        }
    ]
    assert "无关角色" not in repr(context)


def test_chapter_context_uses_empty_related_index_when_beat_plan_names_are_invalid() -> None:
    source = _core_context()
    source["planning"]["approvedBeatPlan"]["sceneBeats"][0]["characters"] = "林舟"

    context = build_operation_context(OPERATION_DEFINITIONS["write_chapter"], source)

    assert context["relatedCharacters"] == []


def test_chapter_context_preserves_selected_full_text_without_truncation() -> None:
    long_text = "正文" * 100_000
    source = _core_context()
    source["workspace"]["chapters"][1]["content"] = long_text
    context = build_operation_context(OPERATION_DEFINITIONS["write_chapter"], source)

    assert context["currentChapter"]["content"] == long_text


def test_short_outline_context_uses_core_authority_order_without_long_outline_projection() -> None:
    source = _core_context()
    short_context = {
        "directEdit": {"sections": [{"id": "section-2", "events": "直接编辑"}]},
        "revisionRequest": "只修改第二节",
        "anchors": {"mustKeep": ["结局"], "confirmed": [], "avoid": []},
        "currentOutline": {"kind": "outline_draft", "content": "完整大纲"},
        "originalInspiration": "原始灵感",
        "recentConversation": [{"role": "user", "content": "它指第二节"}],
    }
    source["planning"]["shortStoryContext"] = short_context

    context = build_operation_context(
        OPERATION_DEFINITIONS["develop_short_outline"], source
    )

    assert context["shortStory"] == short_context
    assert list(context["shortStory"]) == list(short_context)
    assert "outline" not in context


def test_short_discussion_context_uses_exact_core_version_references() -> None:
    source = _core_context()
    source["planning"]["workflowKind"] = "short_medium"
    short_context = {
        "referencedVersions": [
            {
                "kind": "outline",
                "artifactId": "outline-v1",
                "revision": 1,
                "hash": "a" * 64,
                "content": "大纲第一版完整内容",
            },
            {
                "kind": "outline",
                "artifactId": "outline-v2",
                "revision": 2,
                "hash": "b" * 64,
                "content": "大纲第二版完整内容",
            },
        ],
        "directEdit": None,
        "revisionRequest": "比较大纲 v1 和大纲 v2",
        "anchors": None,
        "currentOutline": None,
        "originalInspiration": "一间替人保管遗失明天的失物招领处",
        "recentConversation": [],
    }
    source["planning"]["shortStoryContext"] = short_context

    context = build_operation_context(
        OPERATION_DEFINITIONS["answer_question"], source
    )

    assert context["shortStory"] == short_context
    assert "chapter" not in context
    assert "大纲第一版完整内容" in repr(context)
    assert "大纲第二版完整内容" in repr(context)


def test_chapter_target_parser_distinguishes_current_and_next_chapter() -> None:
    assert parse_chapter_target("请重写当前章") == "current_chapter"
    assert parse_chapter_target("继续写下一章") == "next_chapter"
    assert parse_chapter_target("写一点内容") is None

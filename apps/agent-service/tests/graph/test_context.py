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
                {"id": "character-1", "name": "林舟", "summary": "逃亡者", "secret": "详情"}
            ],
            "items": [{"id": "item-1", "name": "墨印", "description": "线索"}],
            "locations": [{"id": "location-1", "name": "边城", "description": "关隘"}],
            "factions": [{"id": "faction-1", "name": "巡夜司", "description": "追捕方"}],
            "glossaries": [{"id": "term-1", "name": "夜潮", "description": "灾变"}],
            "storyBackground": {"id": "background-1", "title": "背景", "content": "背景全文"},
            "worldSetting": {"id": "world-1", "title": "世界", "content": "世界全文"},
            "outline": {"id": "outline-1", "title": "总纲", "content": "完整总纲"},
            "outlineNodes": [
                {"id": "group-1", "kind": "chapter_group", "title": "逃亡篇", "content": "完整节点"}
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
            "approvedBeatPlan": {"chapterGoal": "入城", "sceneBeats": [{"goal": "过关"}]},
            "chapterGroup": {"id": "group-1", "title": "逃亡篇", "content": "章节组全文"},
            "outlinePath": [{"id": "stage-1", "kind": "stage", "title": "第一幕"}],
            "activeArtifact": {"id": "artifact-1", "payload": {"kind": "chapter_draft"}},
            "conversationHistory": [{"role": "user", "content": "旧请求"}],
            "userMessage": "当前请求",
            "graphState": {"runtimeContext": {"runResource": {"runId": "旧运行"}}},
        },
    }


@pytest.mark.parametrize(
    ("operation_kind", "expected", "unexpected"),
    [
        ("answer_question", {"task", "novel", "chapter"}, {"loreIndex", "outline", "beatPlan"}),
        ("create_lore", {"task", "novel", "loreIndex"}, {"outline", "beatPlan"}),
        ("create_outline", {"task", "novel", "outline"}, {"currentChapter", "beatPlan"}),
        (
            "write_chapter",
            {"task", "novel", "currentChapter", "adjacentChapters", "beatPlan"},
            {"reviewObject"},
        ),
        ("review_chapter", {"task", "novel", "currentChapter"}, {"activeArtifact", "reviewObject"}),
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


def test_chapter_context_preserves_selected_full_text_without_truncation() -> None:
    long_text = "正文" * 100_000
    source = _core_context()
    source["workspace"]["chapters"][1]["content"] = long_text
    context = build_operation_context(OPERATION_DEFINITIONS["write_chapter"], source)

    assert context["currentChapter"]["content"] == long_text


def test_chapter_target_parser_distinguishes_current_and_next_chapter() -> None:
    assert parse_chapter_target("请重写当前章") == "current_chapter"
    assert parse_chapter_target("继续写下一章") == "next_chapter"
    assert parse_chapter_target("写一点内容") is None

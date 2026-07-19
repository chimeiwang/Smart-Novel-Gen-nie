from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from ..operations.definitions import OperationDefinition

_NOVEL_FIELDS = ("id", "name", "summary", "storyProgress")
_CHAPTER_SUMMARY_FIELDS = ("id", "title", "order", "status", "wordCount", "updatedAt")
_CHARACTER_FIELDS = ("id", "name", "identity", "currentStatus", "statusNote")
_ITEM_FIELDS = ("id", "name", "type", "rarity")
_LOCATION_FIELDS = ("id", "name", "type", "parentId")
_FACTION_FIELDS = ("id", "name", "type", "baseId")
_GLOSSARY_FIELDS = ("id", "term", "category")
_FORESHADOWING_FIELDS = (
    "id",
    "name",
    "status",
    "plantedAt",
    "expectedPayoff",
    "payoffAt",
)
_OUTLINE_NODE_FIELDS = (
    "id",
    "kind",
    "title",
    "status",
    "order",
    "parentId",
    "linkedChapterId",
    "chapterStartOrder",
    "chapterEndOrder",
)


def build_operation_context(
    definition: OperationDefinition,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    workspace = _mapping(source.get("workspace"))
    planning = _mapping(source.get("planning"))
    task = _select(
        planning,
        ("taskId", "novelId", "chapterId", "chapterOrder", "targetWordCount"),
    )
    novel = _select(_mapping(workspace.get("novel")), _NOVEL_FIELDS)
    current, adjacent = _chapter_scope(workspace, planning)
    projection: dict[str, Any] = {
        "task": task,
        "novel": novel,
    }

    if (
        planning.get("workflowKind") == "short_medium"
        and definition.kind == "answer_question"
    ):
        short_story = planning.get("shortStoryContext")
        if not isinstance(short_story, Mapping):
            raise ValueError("中短篇讨论缺少 Core 权威上下文")
        projection["shortStory"] = dict(short_story)
        return projection

    if definition.contextStrategy == "brief":
        projection["chapter"] = _select(current, _CHAPTER_SUMMARY_FIELDS)
        return projection
    if definition.contextStrategy == "lore":
        projection["loreIndex"] = _lore_index(workspace)
        projection["settingIndex"] = _setting_index(workspace)
        return projection
    if definition.contextStrategy == "outline":
        projection["outline"] = _outline_index(workspace, planning)
        return projection
    if definition.contextStrategy == "chapter":
        projection["currentChapter"] = dict(current)
        projection["adjacentChapters"] = [
            _select(item, _CHAPTER_SUMMARY_FIELDS) for item in adjacent
        ]
        projection["chapterGoal"] = planning.get("chapterGoal")
        projection["beatPlan"] = planning.get("approvedBeatPlan")
        projection["outlinePath"] = planning.get("outlinePath", [])
        projection["relatedCharacters"] = _related_characters(workspace, planning)
        return projection
    if definition.contextStrategy == "review":
        projection["currentChapter"] = dict(current)
        projection["chapterGoal"] = planning.get("chapterGoal")
        projection["beatPlan"] = planning.get("approvedBeatPlan")
        return projection
    if definition.contextStrategy in {"short_outline", "short_story"}:
        short_story = planning.get("shortStoryContext")
        if not isinstance(short_story, Mapping):
            raise ValueError("中短篇 Operation 缺少 Core 权威上下文")
        projection["shortStory"] = dict(short_story)
        return projection
    raise ValueError(f"未知 Operation 上下文策略：{definition.contextStrategy}")


def parse_chapter_target(
    message: str,
) -> Literal["current_chapter", "next_chapter"] | None:
    if re.search(r"本章|当前章|这一章|这章|当前段落|这一段|这段", message):
        return "current_chapter"
    if re.search(r"下一章|下章|新一章", message):
        return "next_chapter"
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _select(source: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    return {field: source[field] for field in fields if field in source}


def _chapter_scope(
    workspace: Mapping[str, Any],
    planning: Mapping[str, Any],
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    chapters = [
        item for item in workspace.get("chapters", []) if isinstance(item, Mapping)
    ]
    chapter_id = planning.get("chapterId") or workspace.get("currentChapterId")
    current_index = next(
        (index for index, item in enumerate(chapters) if item.get("id") == chapter_id),
        None,
    )
    if current_index is None:
        current = _mapping(workspace.get("currentChapter"))
        return current, []
    adjacent = [
        chapters[index]
        for index in (current_index - 1, current_index + 1)
        if 0 <= index < len(chapters)
    ]
    return chapters[current_index], adjacent


def _lore_index(workspace: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "characters": [_character_summary(item) for item in _items(workspace, "characters")],
        "items": [_item_summary(item) for item in _items(workspace, "items")],
        "locations": [
            _select(item, _LOCATION_FIELDS) for item in _items(workspace, "locations")
        ],
        "factions": [
            _select(item, _FACTION_FIELDS) for item in _items(workspace, "factions")
        ],
        "glossaries": [
            _select(item, _GLOSSARY_FIELDS) for item in _items(workspace, "glossaries")
        ],
    }


def _items(workspace: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = workspace.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _character_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    result = _select(item, _CHARACTER_FIELDS)
    faction = item.get("faction")
    if isinstance(faction, Mapping):
        result["faction"] = _select(faction, ("id", "name"))
    return result


def _item_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    result = _select(item, _ITEM_FIELDS)
    owner = item.get("owner")
    if isinstance(owner, Mapping):
        result["owner"] = _select(owner, ("id", "name"))
    return result


def _related_characters(
    workspace: Mapping[str, Any],
    planning: Mapping[str, Any],
) -> list[dict[str, Any]]:
    names = _beat_plan_character_names(planning.get("approvedBeatPlan"))
    if not names:
        return []
    return [
        _character_summary(item)
        for item in _items(workspace, "characters")
        if item.get("name") in names
    ]


def _beat_plan_character_names(value: object) -> set[str]:
    plan = _mapping(value)
    scenes = plan.get("sceneBeats")
    if not isinstance(scenes, list):
        return set()
    names: set[str] = set()
    for scene in scenes:
        if not isinstance(scene, Mapping):
            continue
        serialized = scene.get("characters")
        if not isinstance(serialized, str):
            continue
        try:
            parsed = json.loads(serialized)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            names.update(item for item in parsed if isinstance(item, str) and item)
    return names


def _setting_index(workspace: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: _select(_mapping(workspace.get(key)), ("id", "title", "updatedAt"))
        for key in ("storyBackground", "worldSetting", "writingBible")
        if isinstance(workspace.get(key), Mapping)
    }


def _outline_index(
    workspace: Mapping[str, Any],
    planning: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "outline": _select(
            _mapping(workspace.get("outline")), ("id", "content", "updatedAt")
        ),
        "nodes": [
            _select(item, _OUTLINE_NODE_FIELDS)
            for item in workspace.get("outlineNodes", [])
            if isinstance(item, Mapping)
        ],
        "plotProgress": workspace.get("plotProgress"),
        "chapterGroup": _select(
            _mapping(planning.get("chapterGroup")),
            ("id", "title", "chapterStartOrder", "chapterEndOrder", "content"),
        ),
        "outlinePath": planning.get("outlinePath", []),
        "foreshadowingSummaries": [
            _select(item, _FORESHADOWING_FIELDS)
            for item in planning.get("foreshadowingSummaries", [])
            if isinstance(item, Mapping)
        ],
    }

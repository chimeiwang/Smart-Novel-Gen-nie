from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from ..operations.definitions import OperationDefinition

_NOVEL_FIELDS = ("id", "name", "summary", "storyProgress")
_CHAPTER_SUMMARY_FIELDS = ("id", "title", "order", "status", "wordCount", "updatedAt")
_LORE_INDEX_FIELDS = (
    "id",
    "name",
    "term",
    "type",
    "category",
    "summary",
    "currentStatus",
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
        projection["outline"] = _outline_index(workspace, planning)
        projection["loreIndex"] = _lore_index(workspace)
        return projection
    if definition.contextStrategy == "review":
        projection["currentChapter"] = dict(current)
        projection["chapterGoal"] = planning.get("chapterGoal")
        projection["beatPlan"] = planning.get("approvedBeatPlan")
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
    result: dict[str, list[dict[str, Any]]] = {}
    for key in ("characters", "items", "locations", "factions", "glossaries"):
        result[key] = [
            _select(item, _LORE_INDEX_FIELDS)
            for item in workspace.get(key, [])
            if isinstance(item, Mapping)
        ]
    return result


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
        "outline": _select(_mapping(workspace.get("outline")), ("id", "updatedAt")),
        "nodes": [
            _select(item, _OUTLINE_NODE_FIELDS)
            for item in workspace.get("outlineNodes", [])
            if isinstance(item, Mapping)
        ],
        "plotProgress": workspace.get("plotProgress"),
        "chapterGroup": _select(
            _mapping(planning.get("chapterGroup")),
            ("id", "title", "chapterStartOrder", "chapterEndOrder"),
        ),
        "outlinePath": planning.get("outlinePath", []),
    }

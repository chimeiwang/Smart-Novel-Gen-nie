from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Any, Protocol

from pydantic import BaseModel

from ..errors import ApiError
from .tool_gateway import ToolRequest

DRAFT_WARNING = "以下内容是待审核草案，不是正式设定。未经用户确认不得视为已落库事实。"


class ContextPort(Protocol):
    async def build(self, user_id: str, task_id: str) -> dict[str, Any]: ...


class OutlinePort(Protocol):
    async def list_foreshadowings(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...


class ReviewPort(Protocol):
    async def list_task_artifacts(
        self,
        user_id: str,
        novel_id: str,
        task_id: str,
        status: str | None,
        kind: str | None,
    ) -> list[dict[str, Any]]: ...

    async def get_response(self, user_id: str, artifact_id: str) -> Any: ...


class SemanticSearchPort(Protocol):
    async def search(
        self, user_id: str, novel_id: str, embedding: list[float], top_k: int
    ) -> list[dict[str, Any]]: ...


class WritingReadToolService:
    def __init__(
        self,
        context: ContextPort,
        outlines: OutlinePort,
        reviews: ReviewPort,
        semantic_search: SemanticSearchPort | None = None,
    ) -> None:
        self._context = context
        self._outlines = outlines
        self._reviews = reviews
        self._semantic_search = semantic_search

    async def execute(self, request: ToolRequest) -> dict[str, Any]:
        context = await self._context.build(request.user_id, request.task_id)
        workspace = _mapping(context.get("workspace"), "作品工作区")
        planning = _mapping(context.get("planning"), "写作任务上下文")
        if planning.get("novelId") != request.novel_id:
            raise ApiError(
                status_code=403,
                code="WRITING_TASK_FORBIDDEN",
                message="写作任务与当前小说不匹配",
            )

        name = request.tool_name
        arguments = request.arguments
        if name == "get_novel_info":
            return self._novel_info(workspace, planning, arguments)
        if name == "list_available_data":
            return await self._available_data(request, workspace)
        if name == "list_characters_summary":
            return {
                "characters": [_character_summary(item) for item in _items(workspace, "characters")]
            }
        if name == "get_character_detail":
            return {
                "character": _find_named(
                    _items(workspace, "characters"), "name", arguments["character_name"], "角色"
                )
            }
        if name == "get_character_list":
            return {
                "characters": [
                    _pick(
                        item,
                        "id",
                        "name",
                        "aliases",
                        "gender",
                        "identity",
                        "faction",
                        "currentStatus",
                    )
                    for item in _items(workspace, "characters")
                ]
            }
        if name == "list_factions_summary":
            return {
                "factions": [
                    _pick(item, "id", "name", "aliases", "type", "base", "description")
                    for item in _items(workspace, "factions")
                ]
            }
        if name == "get_faction_detail":
            return {
                "faction": _find_named(
                    _items(workspace, "factions"), "name", arguments["faction_name"], "势力"
                )
            }
        if name == "list_locations_summary":
            return {
                "locations": [
                    _pick(item, "id", "name", "aliases", "type", "climate", "description")
                    for item in _items(workspace, "locations")
                ]
            }
        if name == "get_location_detail":
            return {
                "location": _find_named(
                    _items(workspace, "locations"), "name", arguments["location_name"], "地点"
                )
            }
        if name == "list_items_summary":
            return {
                "items": [
                    _pick(
                        item,
                        "id",
                        "name",
                        "aliases",
                        "type",
                        "rarity",
                        "effect",
                        "description",
                        "owner",
                    )
                    for item in _items(workspace, "items")
                ]
            }
        if name == "get_item_detail":
            return {
                "item": _find_named(
                    _items(workspace, "items"), "name", arguments["item_name"], "物品"
                )
            }
        if name == "list_glossaries_summary":
            return {
                "glossaries": [
                    _pick(item, "id", "term", "category", "definition")
                    for item in _items(workspace, "glossaries")
                ]
            }
        if name == "get_glossary_detail":
            return {
                "glossary": _find_named(
                    _items(workspace, "glossaries"), "term", arguments["term"], "术语"
                )
            }
        if name == "search_lore":
            return await self._search_lore(request, workspace, str(arguments["keyword"]))
        if name == "find_similar_lore":
            return self._similar_lore(workspace, arguments)
        if name == "semantic_search_references":
            return await self._semantic_references(request, arguments)
        if name == "get_style_profile":
            return self._style_profile(workspace)
        if name == "list_outline_summary":
            return self._outline_summary(workspace, planning, arguments)
        if name == "get_outline_node":
            return self._outline_node(workspace, arguments)
        if name == "get_plot_progress":
            return {"plotProgress": workspace.get("plotProgress")}
        if name == "list_foreshadowings_summary":
            values = await self._foreshadowings(request)
            return {
                "foreshadowings": [
                    _pick(
                        item,
                        "id",
                        "name",
                        "status",
                        "plantedAt",
                        "plantedContent",
                        "expectedPayoff",
                        "payoffAt",
                    )
                    for item in values
                ]
            }
        if name == "get_foreshadowing_detail":
            values = await self._foreshadowings(request)
            return {
                "foreshadowing": _find_named(
                    values, "name", arguments["foreshadowing_name"], "伏笔"
                )
            }
        if name == "get_recent_chapters":
            return self._recent_chapters(workspace, planning, arguments)
        if name == "list_review_artifacts":
            return await self._list_artifacts(request, arguments)
        if name == "get_review_artifact":
            return await self._artifact(request, str(arguments["artifact_id"]))
        if name == "get_active_review_artifact":
            active = planning.get("activeArtifact")
            active_id = active.get("id") if isinstance(active, Mapping) else None
            if not isinstance(active_id, str) or not active_id:
                return {"warning": DRAFT_WARNING, "artifact": None}
            return await self._artifact(request, active_id)
        raise ApiError(status_code=404, code="TOOL_NOT_FOUND", message="读取工具不存在")

    @staticmethod
    def _novel_info(
        workspace: Mapping[str, Any],
        planning: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        novel = _mapping(workspace.get("novel"), "小说信息")
        chapter_id = planning.get("chapterId")
        chapter = next(
            (item for item in _items(workspace, "chapters") if item.get("id") == chapter_id),
            None,
        )
        result: dict[str, Any] = {
            "novel": dict(novel),
            "chapterTitle": chapter.get("title") if chapter else None,
            "writingBible": workspace.get("writingBible"),
            "sectionsIncluded": bool(arguments.get("include_full_sections")),
        }
        sections = {
            "outlineSummary": _content(workspace.get("outline")),
            "storyBackground": _content(workspace.get("storyBackground")),
            "worldSetting": _content(workspace.get("worldSetting")),
            "storyProgress": novel.get("storyProgress"),
        }
        if result["sectionsIncluded"]:
            result.update(sections)
        else:
            result["availableSections"] = {key: bool(value) for key, value in sections.items()}
        return result

    async def _available_data(
        self, request: ToolRequest, workspace: Mapping[str, Any]
    ) -> dict[str, Any]:
        foreshadowings = await self._foreshadowings(request)
        return {
            "characters": len(_items(workspace, "characters")),
            "factions": len(_items(workspace, "factions")),
            "locations": len(_items(workspace, "locations")),
            "items": len(_items(workspace, "items")),
            "glossaries": len(_items(workspace, "glossaries")),
            "outlineNodes": len(_items(workspace, "outlineNodes")),
            "foreshadowings": len(foreshadowings),
            "references": len(_items(workspace, "references")),
            "hasStyleProfile": self._applied_style(workspace) is not None,
        }

    async def _search_lore(
        self, request: ToolRequest, workspace: Mapping[str, Any], keyword: str
    ) -> dict[str, Any]:
        domains = {
            "characters": _items(workspace, "characters"),
            "factions": _items(workspace, "factions"),
            "locations": _items(workspace, "locations"),
            "items": _items(workspace, "items"),
            "glossaries": _items(workspace, "glossaries"),
            "foreshadowings": await self._foreshadowings(request),
        }
        lowered = keyword.casefold()
        return {
            "keyword": keyword,
            "results": {
                domain: [
                    item
                    for item in values
                    if lowered in json.dumps(item, ensure_ascii=False, default=str).casefold()
                ]
                for domain, values in domains.items()
            },
        }

    @staticmethod
    def _similar_lore(workspace: Mapping[str, Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
        keyword = str(arguments["keyword"])
        threshold = float(arguments.get("threshold", 0.3))
        results: list[dict[str, Any]] = []
        for domain, key in (
            ("characters", "name"),
            ("factions", "name"),
            ("locations", "name"),
            ("items", "name"),
            ("glossaries", "term"),
        ):
            for item in _items(workspace, domain):
                value = item.get(key)
                if not isinstance(value, str):
                    continue
                similarity = SequenceMatcher(None, value.casefold(), keyword.casefold()).ratio()
                if similarity >= threshold:
                    results.append(
                        {"domain": domain, "name": value, "similarity": round(similarity, 4)}
                    )
        results.sort(key=lambda item: float(item["similarity"]), reverse=True)
        return {"keyword": keyword, "threshold": threshold, "results": results}

    async def _semantic_references(
        self, request: ToolRequest, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        if self._semantic_search is None:
            return {
                "enabled": False,
                "message": "RAG embedding 未配置，参考资料语义召回未启用。",
                "results": [],
            }
        embedding = arguments.get("query_embedding")
        if not isinstance(embedding, list):
            return {
                "enabled": False,
                "message": "RAG embedding 未配置，参考资料语义召回未启用。",
                "results": [],
            }
        results = await self._semantic_search.search(
            request.user_id,
            request.novel_id,
            [float(value) for value in embedding],
            int(arguments.get("topK", 5)),
        )
        return {"enabled": True, "count": len(results), "results": results}

    def _style_profile(self, workspace: Mapping[str, Any]) -> dict[str, Any]:
        style = self._applied_style(workspace)
        return {"available": style is not None, "style": style}

    @staticmethod
    def _applied_style(workspace: Mapping[str, Any]) -> dict[str, Any] | None:
        novel = _mapping(workspace.get("novel"), "小说信息")
        applied_id = novel.get("appliedStyleId")
        return next(
            (
                item
                for item in _items(workspace, "styles")
                if item.get("id") == applied_id and item.get("portraitMarkdown")
            ),
            None,
        )

    @staticmethod
    def _outline_summary(
        workspace: Mapping[str, Any],
        planning: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        scope = arguments.get("scope") or "current_chapter"
        if scope == "current_chapter":
            return {
                "scope": scope,
                "outlinePath": planning.get("outlinePath", []),
                "chapterGroup": planning.get("chapterGroup"),
            }
        result: dict[str, Any] = {
            "scope": "tree_index",
            "nodes": [
                _pick(
                    item,
                    "id",
                    "title",
                    "kind",
                    "status",
                    "order",
                    "parentId",
                    "chapterStartOrder",
                    "chapterEndOrder",
                )
                for item in _items(workspace, "outlineNodes")
            ],
            "summaryIncluded": bool(arguments.get("include_full_summary")),
        }
        if result["summaryIncluded"]:
            result["summary"] = _content(workspace.get("outline"))
        return result

    @staticmethod
    def _outline_node(workspace: Mapping[str, Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
        node_id = arguments.get("node_id")
        node_title = arguments.get("node_title")
        matches = [
            item
            for item in _items(workspace, "outlineNodes")
            if (node_id and item.get("id") == node_id)
            or (
                node_title
                and isinstance(item.get("title"), str)
                and str(node_title) in item["title"]
            )
        ]
        if len(matches) > 1:
            return {
                "error": "OUTLINE_NODE_AMBIGUOUS",
                "candidates": [_pick(item, "id", "title", "kind") for item in matches],
            }
        if not matches:
            raise _not_found("大纲节点", str(node_id or node_title))
        node = matches[0]
        return {
            "node": node,
            "parent": next(
                (
                    item
                    for item in _items(workspace, "outlineNodes")
                    if item.get("id") == node.get("parentId")
                ),
                None,
            ),
            "children": [
                item
                for item in _items(workspace, "outlineNodes")
                if item.get("parentId") == node.get("id")
            ],
        }

    @staticmethod
    def _recent_chapters(
        workspace: Mapping[str, Any],
        planning: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        count = int(arguments.get("count", 3))
        boundary = planning.get("chapterOrder")
        chapters = sorted(_items(workspace, "chapters"), key=lambda item: int(item.get("order", 0)))
        selected = [
            item
            for item in chapters
            if not isinstance(boundary, int) or int(item.get("order", 0)) < boundary
        ][-count:]
        return {
            "count": len(selected),
            "chapters": [_pick(item, "id", "title", "order", "content") for item in selected],
            "note": "只按目标章节位置选择最近章节，正文完整返回。",
        }

    async def _foreshadowings(self, request: ToolRequest) -> list[dict[str, Any]]:
        values = await self._outlines.list_foreshadowings(request.novel_id, request.user_id)
        return [_json_safe_mapping(value) for value in values]

    async def _list_artifacts(
        self, request: ToolRequest, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        artifacts = await self._reviews.list_task_artifacts(
            request.user_id,
            request.novel_id,
            request.task_id,
            _optional_text(arguments.get("status")),
            _optional_text(arguments.get("kind")),
        )
        return {"warning": DRAFT_WARNING, "artifacts": artifacts}

    async def _artifact(self, request: ToolRequest, artifact_id: str) -> dict[str, Any]:
        value = await self._reviews.get_response(request.user_id, artifact_id)
        artifact = _serializable_mapping(value, "待审核草案")
        if artifact.get("novelId") != request.novel_id or artifact.get("taskId") != request.task_id:
            raise ApiError(
                status_code=403,
                code="ARTIFACT_TASK_MISMATCH",
                message="待审核草案不属于当前任务",
            )
        return {"warning": DRAFT_WARNING, "artifact": artifact}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label}格式无效")
    return value


def _serializable_mapping(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"{label}格式无效")


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_safe(item) for key, item in value.items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return normalized.isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _items(workspace: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    value = workspace.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError(f"作品工作区字段 {key} 格式无效")
    return value


def _content(value: Any) -> str:
    return str(value.get("content", "")) if isinstance(value, Mapping) else ""


def _pick(item: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: item.get(key) for key in keys}


def _character_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return _pick(
        item,
        "id",
        "name",
        "aliases",
        "identity",
        "faction",
        "personality",
        "coreDesire",
        "behaviorBoundaries",
        "shortTermGoal",
        "currentStatus",
        "statusNote",
    ) | {
        "experienceCount": len(item.get("experiences", []))
        if isinstance(item.get("experiences"), list)
        else 0
    }


def _find_named(values: list[dict[str, Any]], key: str, query: Any, label: str) -> dict[str, Any]:
    text = str(query).casefold()
    for item in values:
        name = item.get(key)
        aliases = item.get("aliases")
        if isinstance(name, str) and (text in name.casefold() or name.casefold() in text):
            return item
        if isinstance(aliases, str) and text in aliases.casefold():
            return item
    raise _not_found(label, str(query))


def _not_found(label: str, query: str) -> ApiError:
    return ApiError(
        status_code=404, code="TOOL_RESOURCE_NOT_FOUND", message=f"未找到{label}：{query}"
    )


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None

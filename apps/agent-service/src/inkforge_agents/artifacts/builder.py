from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_BUILDER_EVENTS = {
    "start_update_builder",
    "append_update_batch",
    "append_outline_tree",
    "put_update_text_block",
    "put_update_item_text_block",
    "put_update_item_text_blocks",
    "finish_update_builder",
}


def resolve_builder_artifact(
    events: list[dict[str, Any]],
    visible_content: str,
) -> dict[str, Any] | None:
    blocks = iter(_artifact_blocks(visible_content))
    builders: dict[str, dict[str, Any]] = {}
    completed: dict[str, Any] | None = None
    for event in events:
        event_type = event.get("type")
        if event_type not in _BUILDER_EVENTS:
            continue
        artifact_key = event.get("artifactKey")
        if not isinstance(artifact_key, str) or not artifact_key:
            continue
        if event_type == "start_update_builder":
            existing = builders.get(artifact_key)
            if existing is not None:
                if event.get("summary"):
                    existing["summary"] = event["summary"]
                if event.get("reviewerAgent") is not None:
                    existing["reviewerAgent"] = event["reviewerAgent"]
                if event.get("submitForReview") is not None:
                    existing["submitForReview"] = event["submitForReview"]
                continue
            builders[artifact_key] = {
                "summary": event.get("summary"),
                "reviewerAgent": event.get("reviewerAgent"),
                "submitForReview": event.get("submitForReview", False),
                "updates": {},
                "outlineBatch": 0,
            }
            continue
        builder = builders.get(artifact_key)
        if builder is None:
            raise ValueError("更新构建器尚未开始")
        if event_type == "append_update_batch":
            incoming = event.get("updates")
            if not isinstance(incoming, dict):
                raise ValueError("更新构建器批次格式无效")
            builder["updates"] = _merge_updates(builder["updates"], incoming)
        elif event_type == "append_outline_tree":
            mode = event.get("mode")
            stages = event.get("stages")
            if mode not in {"replace", "patch"} or not isinstance(stages, list):
                raise ValueError("结构化大纲树批次格式无效")
            tree = _outline_tree_update(
                artifact_key,
                int(builder["outlineBatch"]),
                mode,
                stages,
            )
            builder["updates"] = _merge_updates(builder["updates"], tree)
            builder["outlineBatch"] = int(builder["outlineBatch"]) + 1
        elif event_type == "put_update_text_block":
            section = event.get("section")
            if section not in {"outlineContent", "worldSetting", "storyBackground"}:
                raise ValueError("更新构建器长文本 section 无效")
            builder["updates"] = _merge_updates(
                builder["updates"], {str(section): _next_block(blocks)}
            )
        elif event_type == "put_update_item_text_block":
            _put_item_text(builder["updates"], event, _next_block(blocks))
        elif event_type == "put_update_item_text_blocks":
            items = event.get("blocks")
            if not isinstance(items, list):
                raise ValueError("批量长文本更新格式无效")
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("批量长文本更新项格式无效")
                _put_item_text(builder["updates"], item, _next_block(blocks))
        elif event_type == "finish_update_builder":
            updates = builder["updates"]
            if not isinstance(updates, dict) or not updates:
                raise ValueError("更新构建器没有可提交内容")
            completed = {
                "type": "propose_updates",
                "artifactKey": artifact_key,
                "summary": event.get("summary") or builder.get("summary"),
                "reviewerAgent": event.get("reviewerAgent")
                or builder.get("reviewerAgent"),
                "submitForReview": event.get(
                    "submitForReview", builder.get("submitForReview", False)
                ),
                "updates": deepcopy(updates),
            }
        if event.get("summary"):
            builder["summary"] = event["summary"]
    return completed


def _artifact_blocks(content: str) -> list[str]:
    start = "ARTIFACT_OUTPUT_START"
    end = "ARTIFACT_OUTPUT_END"
    blocks: list[str] = []
    cursor = 0
    while True:
        start_index = content.find(start, cursor)
        end_index = content.find(end, cursor)
        if start_index < 0 and end_index < 0:
            return blocks
        if start_index < 0 or end_index < start_index:
            raise ValueError("长文本草案标记不完整或顺序错误")
        content_start = start_index + len(start)
        content_end = content.find(end, content_start)
        if content_end < 0:
            raise ValueError("长文本草案缺少结束标记")
        blocks.append(content[content_start:content_end].strip("\r\n"))
        cursor = content_end + len(end)


def _next_block(blocks: Any) -> str:
    try:
        value = next(blocks)
    except StopIteration:
        raise ValueError("更新构建器缺少对应的长文本标记块") from None
    if not isinstance(value, str) or not value:
        raise ValueError("更新构建器长文本不能为空")
    return value


def _merge_updates(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if key == "outlineTreeMode" and key in merged and merged[key] != value:
            raise ValueError("结构化大纲树模式冲突")
        if isinstance(value, list):
            existing = merged.get(key)
            if existing is not None and not isinstance(existing, list):
                raise ValueError("更新构建器 section 类型冲突")
            merged[key] = [*(existing or []), *deepcopy(value)]
        else:
            merged[key] = deepcopy(value)
    return merged


def _outline_tree_update(
    artifact_key: str,
    batch_index: int,
    mode: str,
    stages: list[Any],
) -> dict[str, Any]:
    safe_key = re.sub(r"[^A-Za-z0-9_-]+", "-", artifact_key.strip()).strip("-")[:80]
    prefix = f"{safe_key or 'outline-tree'}-b{batch_index}"
    adjustments: list[dict[str, Any]] = []
    for stage_index, stage in enumerate(stages, 1):
        if not isinstance(stage, dict):
            raise ValueError("结构化大纲阶段格式无效")
        stage_key = f"{prefix}-s{stage_index}"
        adjustments.append(_outline_item(stage, "stage", stage_key, None))
        units = stage.get("plotUnits", [])
        if not isinstance(units, list):
            raise ValueError("结构化大纲剧情单元格式无效")
        for unit_index, unit in enumerate(units, 1):
            if not isinstance(unit, dict):
                raise ValueError("结构化大纲剧情单元格式无效")
            unit_key = f"{stage_key}-u{unit_index}"
            adjustments.append(_outline_item(unit, "plot_unit", unit_key, stage_key))
            groups = unit.get("chapterGroups", [])
            if not isinstance(groups, list):
                raise ValueError("结构化大纲章节组格式无效")
            for group_index, group in enumerate(groups, 1):
                if not isinstance(group, dict):
                    raise ValueError("结构化大纲章节组格式无效")
                adjustments.append(
                    _outline_item(
                        group,
                        "chapter_group",
                        f"{unit_key}-g{group_index}",
                        unit_key,
                    )
                )
    return {"outlineTreeMode": mode, "outlineAdjustments": adjustments}


def _outline_item(
    source: dict[str, Any],
    kind: str,
    client_key: str,
    parent_key: str | None,
) -> dict[str, Any]:
    title = source.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("结构化大纲节点缺少标题")
    result = {
        "action": "create",
        "kind": kind,
        "title": title.strip(),
        "clientKey": client_key,
        "parentKey": parent_key,
    }
    for key in (
        "chapterStartOrder",
        "chapterEndOrder",
        "estimatedWordCount",
    ):
        if source.get(key) is not None:
            result[key] = source[key]
    return {key: value for key, value in result.items() if value is not None}


def _put_item_text(updates: dict[str, Any], event: dict[str, Any], content: str) -> None:
    section = event.get("section")
    field = event.get("field")
    items = updates.get(section) if isinstance(section, str) else None
    if not isinstance(items, list) or not isinstance(field, str):
        raise ValueError("长文本更新目标 section 不存在")
    for item in items:
        if isinstance(item, dict) and _matches_target(item, event):
            item[field] = content
            return
    raise ValueError("长文本更新目标项目不存在")


def _matches_target(item: dict[str, Any], event: dict[str, Any]) -> bool:
    target_id = event.get("targetId")
    if isinstance(target_id, str) and target_id in {
        item.get("id"),
        item.get("characterId"),
        item.get("locationId"),
        item.get("itemId"),
        item.get("factionId"),
        item.get("glossaryId"),
        item.get("nodeId"),
        item.get("referenceId"),
    }:
        return True
    target_key = event.get("targetKey")
    if isinstance(target_key, str) and target_key in {
        item.get("clientKey"),
        item.get("parentKey"),
    }:
        return True
    target_name = event.get("targetName")
    return isinstance(target_name, str) and target_name in {
        item.get("name"),
        item.get("title"),
        item.get("nodeTitle"),
        item.get("term"),
        item.get("characterName"),
        item.get("chapterTitle"),
    }

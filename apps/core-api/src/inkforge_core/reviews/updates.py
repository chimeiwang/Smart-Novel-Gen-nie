from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

ARRAY_SECTIONS = (
    "characters",
    "locations",
    "items",
    "factions",
    "glossaries",
    "characterExperiences",
    "outline",
    "outlineAdjustments",
    "foreshadowing",
    "references",
)
TEXT_SECTIONS = ("outlineContent", "worldSetting", "storyBackground")

_ENTITY_CONFIG = {
    "characters": ("characters", ("id", "characterId"), "name"),
    "locations": ("locations", ("id", "locationId"), "name"),
    "items": ("items", ("id", "itemId"), "name"),
    "factions": ("factions", ("id", "factionId"), "name"),
    "glossaries": ("glossary", ("id", "glossaryId"), "term"),
}
_ENTITY_FIELDS = {
    "characters": {
        "name",
        "aliases",
        "gender",
        "age",
        "identity",
        "personality",
        "appearance",
        "background",
        "coreDesire",
        "behaviorBoundaries",
        "speechStyle",
        "relationshipPrinciples",
        "shortTermGoal",
        "factionId",
        "powerLevel",
        "combatAbility",
        "specialSkills",
        "currentStatus",
        "statusNote",
    },
    "locations": {
        "name",
        "aliases",
        "type",
        "parentId",
        "description",
        "climate",
        "culture",
    },
    "items": {
        "name",
        "aliases",
        "type",
        "rarity",
        "effect",
        "origin",
        "description",
        "ownerId",
    },
    "factions": {"name", "aliases", "type", "baseId", "description"},
    "glossaries": {"term", "definition", "category"},
}


class LoreUpdatesPort(Protocol):
    async def list_entities(
        self, novel_id: str, user_id: str, kind: str
    ) -> list[dict[str, Any]]: ...
    async def create_entity(
        self, novel_id: str, user_id: str, kind: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_entity(
        self, novel_id: str, user_id: str, kind: str, entity_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_entity(
        self, novel_id: str, user_id: str, kind: str, entity_id: str
    ) -> None: ...
    async def create_experience(
        self, novel_id: str, user_id: str, character_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_experience(
        self, novel_id: str, user_id: str, experience_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_experience(self, novel_id: str, user_id: str, experience_id: str) -> None: ...
    async def upsert_content(
        self, novel_id: str, user_id: str, kind: str, content: Any
    ) -> dict[str, Any]: ...


class OutlineUpdatesPort(Protocol):
    async def list_nodes(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def list_foreshadowings(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def create_foreshadowing(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_foreshadowing(
        self, novel_id: str, user_id: str, foreshadowing_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def upsert_outline(self, novel_id: str, user_id: str, content: str) -> dict[str, Any]: ...
    async def create_node(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_node(
        self, novel_id: str, user_id: str, node_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_node(self, novel_id: str, user_id: str, node_id: str) -> None: ...
    async def replace_nodes(
        self, novel_id: str, user_id: str, adjustments: list[dict[str, Any]]
    ) -> None: ...


class ReferenceUpdatesPort(Protocol):
    async def list_references(self, novel_id: str, user_id: str) -> list[dict[str, Any]]: ...
    async def create_reference(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_reference(
        self, novel_id: str, user_id: str, reference_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_reference(self, novel_id: str, user_id: str, reference_id: str) -> None: ...


class AgentUpdatesExecutor:
    def __init__(
        self,
        lore: LoreUpdatesPort,
        outlines: OutlineUpdatesPort,
        references: ReferenceUpdatesPort,
    ) -> None:
        self._lore = lore
        self._outlines = outlines
        self._references = references

    async def apply(self, novel_id: str, user_id: str, updates: dict[str, object]) -> int:
        count = 0
        for section, (kind, id_fields, name_field) in _ENTITY_CONFIG.items():
            items = updates.get(section)
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError(f"{section} 更新项结构无效")
                    await self._apply_entity(
                        novel_id, user_id, section, kind, id_fields, name_field, item
                    )
                    count += 1
        experiences = updates.get("characterExperiences")
        if isinstance(experiences, list):
            for item in experiences:
                if not isinstance(item, dict):
                    raise ValueError("characterExperiences 更新项结构无效")
                await self._apply_experience(novel_id, user_id, item)
                count += 1
        count += await self._apply_outline_updates(novel_id, user_id, updates)
        count += await self._apply_foreshadowing(novel_id, user_id, updates)
        count += await self._apply_references(novel_id, user_id, updates)
        for section, kind in (
            ("outlineContent", "outline"),
            ("worldSetting", "world-setting"),
            ("storyBackground", "story-background"),
        ):
            if section not in updates:
                continue
            content = updates[section]
            if not isinstance(content, str):
                raise ValueError(f"{section} 必须是完整文本")
            if kind == "outline":
                await self._outlines.upsert_outline(novel_id, user_id, content)
            else:
                await self._lore.upsert_content(novel_id, user_id, kind, content)
            count += 1
        if count == 0:
            raise ValueError("agent_updates 不包含可应用更新")
        return count

    async def _apply_entity(
        self,
        novel_id: str,
        user_id: str,
        section: str,
        kind: str,
        id_fields: tuple[str, ...],
        name_field: str,
        item: dict[str, Any],
    ) -> None:
        action = item.get("action")
        if action not in {"create", "update", "delete"}:
            raise ValueError(f"{section} action 无效")
        fields = _strict_fields(item, _ENTITY_FIELDS[section], section)
        if action == "create":
            await self._lore.create_entity(novel_id, user_id, kind, fields)
            return
        entity_id = next(
            (item[field] for field in id_fields if isinstance(item.get(field), str)), None
        )
        if entity_id is None:
            name = item.get(name_field)
            values = await self._lore.list_entities(novel_id, user_id, kind)
            matches = [value for value in values if value.get(name_field) == name]
            if len(matches) != 1 or not isinstance(matches[0].get("id"), str):
                raise ValueError(f"{section} 无法唯一解析已有实体")
            entity_id = matches[0]["id"]
        if action == "delete":
            await self._lore.delete_entity(novel_id, user_id, kind, entity_id)
        else:
            await self._lore.update_entity(novel_id, user_id, kind, entity_id, fields)

    async def _apply_experience(self, novel_id: str, user_id: str, item: dict[str, Any]) -> None:
        action = item.get("action")
        experience_id = item.get("id")
        fields = _strict_fields(item, {"chapterId", "content", "order"}, "characterExperiences")
        if action == "create":
            character_id = item.get("characterId")
            if not isinstance(character_id, str):
                characters = await self._lore.list_entities(novel_id, user_id, "characters")
                matches = [
                    value for value in characters if value.get("name") == item.get("characterName")
                ]
                if len(matches) != 1 or not isinstance(matches[0].get("id"), str):
                    raise ValueError("角色经历无法唯一解析角色")
                character_id = matches[0]["id"]
            await self._lore.create_experience(novel_id, user_id, character_id, fields)
        elif action == "update" and isinstance(experience_id, str):
            await self._lore.update_experience(novel_id, user_id, experience_id, fields)
        elif action == "delete" and isinstance(experience_id, str):
            await self._lore.delete_experience(novel_id, user_id, experience_id)
        else:
            raise ValueError("角色经历更新缺少有效标识")

    async def _apply_outline_updates(
        self, novel_id: str, user_id: str, updates: dict[str, object]
    ) -> int:
        count = 0
        status_updates = updates.get("outline")
        if isinstance(status_updates, list):
            for item in status_updates:
                if not isinstance(item, dict) or not isinstance(item.get("nodeId"), str):
                    raise ValueError("outline 更新缺少 nodeId")
                fields = _strict_fields(item, {"status", "actualWordCount"}, "outline")
                await self._outlines.update_node(novel_id, user_id, item["nodeId"], fields)
                count += 1
        adjustments = updates.get("outlineAdjustments")
        if not isinstance(adjustments, list):
            return count
        typed = [item for item in adjustments if isinstance(item, dict)]
        if len(typed) != len(adjustments):
            raise ValueError("outlineAdjustments 更新项结构无效")
        if updates.get("outlineTreeMode") == "replace":
            await self._outlines.replace_nodes(novel_id, user_id, typed)
            return count + len(typed)
        nodes = await self._outlines.list_nodes(novel_id, user_id)
        client_ids: dict[str, str] = {}
        for item in typed:
            action = item.get("action")
            node_id = _resolve_named_id(item, nodes, ("nodeId",), "title")
            fields = _strict_fields(
                item,
                {
                    "title",
                    "content",
                    "kind",
                    "parentId",
                    "status",
                    "estimatedWordCount",
                    "actualWordCount",
                    "chapterStartOrder",
                    "chapterEndOrder",
                },
                "outlineAdjustments",
            )
            parent_key = item.get("parentKey")
            if isinstance(parent_key, str):
                if parent_key not in client_ids:
                    raise ValueError("outlineAdjustments parentKey 无法解析")
                fields["parentId"] = client_ids[parent_key]
            if action == "create":
                created = await self._outlines.create_node(novel_id, user_id, fields)
                client_key = item.get("clientKey")
                if isinstance(client_key, str) and isinstance(created.get("id"), str):
                    client_ids[client_key] = created["id"]
            elif action == "update" and node_id is not None:
                await self._outlines.update_node(novel_id, user_id, node_id, fields)
            elif action == "delete" and node_id is not None:
                await self._outlines.delete_node(novel_id, user_id, node_id)
            else:
                raise ValueError("outlineAdjustments 缺少有效标识")
            count += 1
        return count

    async def _apply_foreshadowing(
        self, novel_id: str, user_id: str, updates: dict[str, object]
    ) -> int:
        items = updates.get("foreshadowing")
        if not isinstance(items, list):
            return 0
        existing: list[dict[str, Any]] | None = None
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("foreshadowing 更新项结构无效")
            if item.get("payoffNote") is not None:
                raise ValueError("payoffNote 无法写入现有数据库结构")
            action = item.get("action")
            fields = _strict_fields(
                item,
                {"name", "plantedAt", "plantedContent", "expectedPayoff", "payoffAt"},
                "foreshadowing",
            )
            if action == "create":
                await self._outlines.create_foreshadowing(novel_id, user_id, fields)
                continue
            if existing is None:
                existing = await self._outlines.list_foreshadowings(novel_id, user_id)
            item_id = _resolve_named_id(item, existing, ("id",), "name")
            if item_id is None:
                raise ValueError("foreshadowing 无法唯一解析已有伏笔")
            if action == "payoff":
                fields["status"] = "paid_off"
            elif action == "abandon":
                fields["status"] = "abandoned"
            elif action != "update":
                raise ValueError("foreshadowing action 无效")
            await self._outlines.update_foreshadowing(novel_id, user_id, item_id, fields)
        return len(items)

    async def _apply_references(
        self, novel_id: str, user_id: str, updates: dict[str, object]
    ) -> int:
        items = updates.get("references")
        if not isinstance(items, list):
            return 0
        existing = await self._references.list_references(novel_id, user_id)
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("references 更新项结构无效")
            action = item.get("action")
            fields = _strict_fields(item, {"title", "type", "content"}, "references")
            if action == "create":
                if not isinstance(fields.get("type"), str) or not isinstance(
                    fields.get("content"), str
                ):
                    raise ValueError("新建参考资料必须提供 type 和完整 content")
                await self._references.create_reference(novel_id, user_id, fields)
                continue
            item_id = _resolve_named_id(item, existing, ("id", "referenceId"), "title")
            if item_id is None:
                raise ValueError("references 无法唯一解析已有参考资料")
            if action == "update":
                await self._references.update_reference(novel_id, user_id, item_id, fields)
            elif action == "delete":
                await self._references.delete_reference(novel_id, user_id, item_id)
            else:
                raise ValueError("references action 无效")
        return len(items)


def filter_agent_updates_by_selection(
    updates: dict[str, Any], selected_refs: list[dict[str, Any]] | None
) -> dict[str, Any]:
    if selected_refs is None:
        return deepcopy(updates)

    selected: dict[str, dict[str, Any]] = {}
    for reference in selected_refs:
        section = reference.get("section")
        if not isinstance(section, str):
            continue
        entry = selected.setdefault(section, {"full": False, "indices": set()})
        index = reference.get("index")
        if index is None:
            entry["full"] = True
        elif isinstance(index, int) and not isinstance(index, bool) and index >= 0:
            entry["indices"].add(index)

    output: dict[str, Any] = {}
    for section in ARRAY_SECTIONS:
        items = updates.get(section)
        choice = selected.get(section)
        if not isinstance(items, list) or choice is None:
            continue
        picked = (
            items
            if choice["full"]
            else [item for index, item in enumerate(items) if index in choice["indices"]]
        )
        if picked:
            output[section] = deepcopy(picked)

    for section in TEXT_SECTIONS:
        if section in selected and updates.get(section):
            output[section] = deepcopy(updates[section])

    if output.get("outlineAdjustments") and updates.get("outlineTreeMode"):
        output["outlineTreeMode"] = updates["outlineTreeMode"]
    return output


def _strict_fields(item: dict[str, Any], allowed: set[str], section: str) -> dict[str, Any]:
    control = {
        "action",
        "id",
        "characterId",
        "locationId",
        "itemId",
        "factionId",
        "glossaryId",
        "referenceId",
        "nodeId",
        "nodeTitle",
        "clientKey",
        "parentKey",
        "characterName",
        "chapterTitle",
        "fieldChanges",
        "payoffNote",
    }
    unknown = set(item) - allowed - control
    if unknown:
        names = "、".join(sorted(unknown))
        raise ValueError(f"{section} 包含无法持久化字段：{names}")
    return {key: deepcopy(value) for key, value in item.items() if key in allowed}


def _resolve_named_id(
    item: dict[str, Any],
    existing: list[dict[str, Any]],
    id_fields: tuple[str, ...],
    name_field: str,
) -> str | None:
    for field in id_fields:
        value = item.get(field)
        if isinstance(value, str) and value:
            return value
    name = item.get(name_field) or item.get("nodeTitle")
    matches = [value for value in existing if value.get(name_field) == name]
    if len(matches) == 1:
        resolved = matches[0].get("id")
        if isinstance(resolved, str):
            return resolved
    return None

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel

from ..lore.repository import EntityMutation, ExperienceMutation
from ..lore.schemas import (
    CreateCharacterRequest,
    CreateExperienceRequest,
    CreateFactionRequest,
    CreateGlossaryRequest,
    CreateItemRequest,
    CreateLocationRequest,
    UpdateCharacterRequest,
    UpdateExperienceRequest,
    UpdateFactionRequest,
    UpdateGlossaryRequest,
    UpdateItemRequest,
    UpdateLocationRequest,
)
from ..references.repository import ReferenceMutation
from ..references.schemas import CreateReferenceRequest, UpdateReferenceRequest

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
_ENTITY_CREATE_REQUESTS: dict[str, type[BaseModel]] = {
    "characters": CreateCharacterRequest,
    "locations": CreateLocationRequest,
    "items": CreateItemRequest,
    "factions": CreateFactionRequest,
    "glossaries": CreateGlossaryRequest,
}
_ENTITY_UPDATE_REQUESTS: dict[str, type[BaseModel]] = {
    "characters": UpdateCharacterRequest,
    "locations": UpdateLocationRequest,
    "items": UpdateItemRequest,
    "factions": UpdateFactionRequest,
    "glossaries": UpdateGlossaryRequest,
}
_ENTITY_CREATE_FIELDS = {
    section: set(schema.model_fields) - {"clientRequestId"}
    for section, schema in _ENTITY_CREATE_REQUESTS.items()
}
_ENTITY_UPDATE_FIELDS = {
    section: set(schema.model_fields) - {"expectedUpdatedAt"}
    for section, schema in _ENTITY_UPDATE_REQUESTS.items()
}
_ENTITY_ACTION_CONTROLS = {
    "create": {"action", "fieldChanges", "clientRequestId"},
    "update": {"action", "fieldChanges", "expectedUpdatedAt"},
    "delete": {"action", "fieldChanges", "expectedUpdatedAt"},
}
_EXPERIENCE_CREATE_FIELDS = set(CreateExperienceRequest.model_fields) - {
    "clientRequestId"
}
_EXPERIENCE_UPDATE_FIELDS = set(UpdateExperienceRequest.model_fields) - {
    "expectedUpdatedAt"
}
_EXPERIENCE_ACTION_CONTROLS = {
    "create": {"action", "fieldChanges", "clientRequestId"},
    "update": {"action", "fieldChanges", "id", "expectedUpdatedAt"},
    "delete": {"action", "id", "expectedUpdatedAt"},
}
_EXPERIENCE_ACTION_TARGETS = {
    "create": {"characterId", "characterName"},
    "update": set(),
    "delete": set(),
}
_REFERENCE_CREATE_FIELDS = set(CreateReferenceRequest.model_fields) - {
    "clientRequestId"
}
_REFERENCE_UPDATE_FIELDS = set(UpdateReferenceRequest.model_fields) - {
    "expectedUpdatedAt"
}
_REFERENCE_ACTION_CONTROLS = {
    "create": {"action", "fieldChanges", "clientRequestId"},
    "update": {"action", "fieldChanges", "id", "referenceId", "expectedUpdatedAt"},
    "delete": {"action", "fieldChanges", "id", "referenceId", "expectedUpdatedAt"},
}


class LoreUpdatesPort(Protocol):
    async def list_entities(
        self, novel_id: str, user_id: str, kind: str
    ) -> list[dict[str, Any]]: ...
    async def apply_entity_mutations(
        self, novel_id: str, user_id: str, mutations: list[EntityMutation]
    ) -> list[dict[str, Any]]: ...
    async def apply_experience_mutations(
        self, novel_id: str, user_id: str, mutations: list[ExperienceMutation]
    ) -> list[dict[str, Any]]: ...
    async def upsert_content(
        self,
        novel_id: str,
        user_id: str,
        kind: str,
        content: Any,
        expected_updated_at: datetime | None,
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
    async def upsert_outline(
        self,
        novel_id: str,
        user_id: str,
        content: str,
        expected_updated_at: datetime | None = None,
    ) -> dict[str, Any]: ...
    async def create_review_node(
        self, novel_id: str, user_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def update_review_node(
        self, novel_id: str, user_id: str, node_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_review_node(
        self, novel_id: str, user_id: str, node_id: str
    ) -> None: ...
    async def replace_nodes(
        self, novel_id: str, user_id: str, adjustments: list[dict[str, Any]]
    ) -> None: ...


class ReferenceUpdatesPort(Protocol):
    async def apply_reference_mutations(
        self,
        novel_id: str,
        user_id: str,
        mutations: list[ReferenceMutation],
        *,
        index_enabled: bool = False,
    ) -> list[dict[str, Any]]: ...


class AgentUpdatesExecutor:
    def __init__(
        self,
        lore: LoreUpdatesPort,
        outlines: OutlineUpdatesPort,
        references: ReferenceUpdatesPort,
        *,
        reference_index_enabled: bool = False,
    ) -> None:
        self._lore = lore
        self._outlines = outlines
        self._references = references
        self._reference_index_enabled = reference_index_enabled

    async def apply(
        self,
        novel_id: str,
        user_id: str,
        updates: dict[str, object],
        *,
        expected_outline_updated_at: datetime | None = None,
        expected_lore_updated_at: dict[str, datetime | None] | None = None,
    ) -> int:
        count = 0
        entity_items: list[
            tuple[str, str, tuple[str, ...], str, dict[str, Any], dict[str, Any]]
        ] = []
        for section, (kind, id_fields, name_field) in _ENTITY_CONFIG.items():
            items = updates.get(section)
            if section in updates and not isinstance(items, list):
                raise ValueError(f"{section} 必须是数组")
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        raise ValueError(f"{section} 更新项结构无效")
                    fields = _validate_entity_item(item, section)
                    entity_items.append(
                        (section, kind, id_fields, name_field, item, fields)
                    )
        entity_mutations = [
            self._build_entity_mutation(
                section, kind, id_fields, name_field, item, fields
            )
            for section, kind, id_fields, name_field, item, fields in entity_items
        ]
        experience_mutations: list[ExperienceMutation] = []
        experiences = updates.get("characterExperiences")
        if "characterExperiences" in updates and not isinstance(experiences, list):
            raise ValueError("characterExperiences 必须是数组")
        if isinstance(experiences, list):
            for item in experiences:
                if not isinstance(item, dict):
                    raise ValueError("characterExperiences 更新项结构无效")
                experience_mutations.append(self._build_experience_mutation(item))
        for section in ("worldSetting", "storyBackground"):
            if section not in updates:
                continue
            if not isinstance(updates[section], str):
                raise ValueError(f"{section} 必须是完整文本")
            if (
                expected_lore_updated_at is None
                or section not in expected_lore_updated_at
            ):
                raise ValueError(f"{section} 缺少审核草案版本基线")
        if entity_mutations:
            await self._lore.apply_entity_mutations(
                novel_id, user_id, entity_mutations
            )
            count += len(entity_mutations)
        if experience_mutations:
            await self._lore.apply_experience_mutations(
                novel_id, user_id, experience_mutations
            )
            count += len(experience_mutations)
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
                await self._outlines.upsert_outline(
                    novel_id,
                    user_id,
                    content,
                    expected_outline_updated_at,
                )
            else:
                if expected_lore_updated_at is None:
                    raise ValueError(f"{section} 缺少审核草案版本基线")
                await self._lore.upsert_content(
                    novel_id,
                    user_id,
                    kind,
                    content,
                    expected_lore_updated_at[section],
                )
            count += 1
        if count == 0:
            raise ValueError("agent_updates 不包含可应用更新")
        return count

    @staticmethod
    def _build_entity_mutation(
        section: str,
        kind: str,
        id_fields: tuple[str, ...],
        name_field: str,
        item: dict[str, Any],
        fields: dict[str, Any],
    ) -> EntityMutation:
        action = item.get("action")
        if action not in {"create", "update", "delete"}:
            raise ValueError(f"{section} action 无效")
        if action == "create":
            client_request_id = item.get("clientRequestId")
            if not isinstance(client_request_id, str) or not 16 <= len(client_request_id) <= 256:
                raise ValueError(f"{section} create 必须提供 16..256 字符的 clientRequestId")
            return EntityMutation(
                action="create",
                kind=kind,
                fields=fields,
                client_request_id=client_request_id,
                error_label=section,
            )
        entity_id = next(
            (
                item[field]
                for field in id_fields
                if isinstance(item.get(field), str) and item[field]
            ),
            None,
        )
        expected_updated_at = _require_entity_expected_updated_at(item, section)
        if action == "delete":
            return EntityMutation(
                action="delete",
                kind=kind,
                fields={},
                entity_id=entity_id,
                expected_updated_at=expected_updated_at,
                lookup_field=name_field if entity_id is None else None,
                lookup_value=item.get(name_field) if entity_id is None else None,
                error_label=section,
            )
        return EntityMutation(
            action="update",
            kind=kind,
            fields=fields,
            entity_id=entity_id,
            expected_updated_at=expected_updated_at,
            lookup_field=name_field if entity_id is None else None,
            lookup_value=item.get(name_field) if entity_id is None else None,
            error_label=section,
        )

    @staticmethod
    def _build_experience_mutation(item: dict[str, Any]) -> ExperienceMutation:
        action = item.get("action")
        if action not in {"create", "update", "delete"}:
            raise ValueError("characterExperiences action 无效")
        business_fields = (
            _EXPERIENCE_CREATE_FIELDS
            if action == "create"
            else _EXPERIENCE_UPDATE_FIELDS if action == "update" else set()
        )
        allowed = (
            business_fields
            | _EXPERIENCE_ACTION_CONTROLS[action]
            | _EXPERIENCE_ACTION_TARGETS[action]
        )
        unknown = set(item) - allowed
        if unknown:
            names = "、".join(sorted(unknown))
            raise ValueError(
                f"characterExperiences 包含无法持久化字段：{names}"
            )
        fields = {
            key: deepcopy(value)
            for key, value in item.items()
            if key in business_fields
        }
        if action == "create":
            character_id = item.get("characterId")
            character_name = item.get("characterName")
            for field in ("characterId", "characterName"):
                if field in item and (
                    not isinstance(item[field], str) or not item[field]
                ):
                    raise ValueError(
                        f"characterExperiences {field} 标识必须是非空字符串"
                    )
            if not character_id and not character_name:
                raise ValueError("角色经历无法唯一解析角色")
            client_request_id = item.get("clientRequestId")
            if not isinstance(client_request_id, str) or not 16 <= len(client_request_id) <= 256:
                raise ValueError(
                    "characterExperiences create 必须提供 16..256 字符的 clientRequestId"
                )
            try:
                CreateExperienceRequest.model_validate(
                    {**fields, "clientRequestId": client_request_id}
                )
            except ValueError as error:
                raise ValueError(
                    "characterExperiences create 业务字段无效"
                ) from error
            return ExperienceMutation(
                action="create",
                fields=fields,
                character_id=character_id if isinstance(character_id, str) else None,
                character_name=character_name if isinstance(character_name, str) else None,
                client_request_id=client_request_id,
            )
        experience_id = item.get("id")
        if not isinstance(experience_id, str) or not experience_id:
            raise ValueError("角色经历更新缺少有效标识")
        expected_updated_at = _require_entity_expected_updated_at(
            item, "characterExperiences"
        )
        if action == "update":
            try:
                UpdateExperienceRequest.model_validate(
                    {**fields, "expectedUpdatedAt": expected_updated_at}
                )
            except ValueError as error:
                raise ValueError(
                    "characterExperiences update 业务字段类型无效"
                ) from error
            if any(
                fields.get(field) is None
                for field in ("content", "order")
                if field in fields
            ):
                raise ValueError("characterExperiences content/order 不能为 null")
            return ExperienceMutation(
                action="update",
                fields=fields,
                entity_id=experience_id,
                expected_updated_at=expected_updated_at,
            )
        return ExperienceMutation(
            action="delete",
            fields={},
            entity_id=experience_id,
            expected_updated_at=expected_updated_at,
        )

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
                await self._outlines.update_review_node(
                    novel_id, user_id, item["nodeId"], fields
                )
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
                created = await self._outlines.create_review_node(
                    novel_id, user_id, fields
                )
                client_key = item.get("clientKey")
                if isinstance(client_key, str) and isinstance(created.get("id"), str):
                    client_ids[client_key] = created["id"]
            elif action == "update" and node_id is not None:
                await self._outlines.update_review_node(
                    novel_id, user_id, node_id, fields
                )
            elif action == "delete" and node_id is not None:
                await self._outlines.delete_review_node(novel_id, user_id, node_id)
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
        if "references" not in updates:
            return 0
        if not isinstance(items, list):
            raise ValueError("references 必须是数组")
        mutations: list[ReferenceMutation] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("references 更新项结构无效")
            mutations.append(_build_reference_mutation(item))
        if mutations:
            await self._references.apply_reference_mutations(
                novel_id,
                user_id,
                mutations,
                index_enabled=self._reference_index_enabled,
            )
        return len(items)


def _build_reference_mutation(item: dict[str, Any]) -> ReferenceMutation:
    action = item.get("action")
    if action not in {"create", "update", "delete"}:
        raise ValueError("references action 无效")
    business_fields = (
        _REFERENCE_CREATE_FIELDS
        if action == "create"
        else _REFERENCE_UPDATE_FIELDS if action == "update" else set()
    )
    allowed = business_fields | _REFERENCE_ACTION_CONTROLS[action]
    unknown = set(item) - allowed
    if unknown:
        names = "、".join(sorted(unknown))
        raise ValueError(f"references 包含无法持久化字段：{names}")
    fields = {
        key: deepcopy(value)
        for key, value in item.items()
        if key in business_fields
    }
    if action == "create":
        client_request_id = item.get("clientRequestId")
        if not isinstance(client_request_id, str) or not 16 <= len(client_request_id) <= 256:
            raise ValueError("references create 必须提供 16..256 字符的 clientRequestId")
        try:
            validated = CreateReferenceRequest.model_validate(
                {**fields, "clientRequestId": client_request_id}
            )
        except ValueError as error:
            raise ValueError("references create 业务字段无效") from error
        if not validated.title.strip():
            raise ValueError("references title 不能为空")
        return ReferenceMutation(
            action="create",
            fields=validated.model_dump(exclude={"clientRequestId"}),
            client_request_id=client_request_id,
        )
    reference_id = item.get("id") or item.get("referenceId")
    if not isinstance(reference_id, str) or not reference_id:
        raise ValueError(f"references {action} 缺少有效 referenceId")
    for field in ("id", "referenceId"):
        if field in item and (
            not isinstance(item[field], str) or not item[field]
        ):
            raise ValueError(f"references {field} 标识必须是非空字符串")
    if (
        isinstance(item.get("id"), str)
        and isinstance(item.get("referenceId"), str)
        and item["id"] != item["referenceId"]
    ):
        raise ValueError("references id 与 referenceId 不一致")
    expected_updated_at = _require_entity_expected_updated_at(item, "references")
    if action == "update":
        try:
            validated_update = UpdateReferenceRequest.model_validate(
                {**fields, "expectedUpdatedAt": expected_updated_at}
            )
        except ValueError as error:
            raise ValueError("references update 业务字段无效") from error
        validated_fields = validated_update.model_dump(
            exclude={"expectedUpdatedAt"}, exclude_unset=True
        )
        if any(
            validated_fields.get(field) is None
            for field in ("title", "type", "content")
            if field in validated_fields
        ):
            raise ValueError("references title/type/content 不能为 null")
        if "title" in validated_fields and not validated_fields["title"].strip():
            raise ValueError("references title 不能为空")
        return ReferenceMutation(
            action="update",
            fields=validated_fields,
            reference_id=reference_id,
            expected_updated_at=expected_updated_at,
        )
    return ReferenceMutation(
        action="delete",
        fields={},
        reference_id=reference_id,
        expected_updated_at=expected_updated_at,
    )


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


def _strict_fields(
    item: dict[str, Any],
    allowed: set[str],
    section: str,
    *,
    extra_control: set[str] | None = None,
) -> dict[str, Any]:
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
    if extra_control is not None:
        control.update(extra_control)
    unknown = set(item) - allowed - control
    if unknown:
        names = "、".join(sorted(unknown))
        raise ValueError(f"{section} 包含无法持久化字段：{names}")
    return {key: deepcopy(value) for key, value in item.items() if key in allowed}


def _require_entity_expected_updated_at(item: dict[str, Any], section: str) -> datetime:
    value = item.get("expectedUpdatedAt")
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        raise ValueError(f"{section} update/delete 必须提供非空 expectedUpdatedAt")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{section} expectedUpdatedAt 格式无效") from error


def _validate_entity_item(item: dict[str, Any], section: str) -> dict[str, Any]:
    action = item.get("action")
    if action not in {"create", "update", "delete"}:
        raise ValueError(f"{section} action 无效")
    business_fields = (
        _ENTITY_CREATE_FIELDS[section]
        if action == "create"
        else _ENTITY_UPDATE_FIELDS[section]
    )
    _, id_fields, name_field = _ENTITY_CONFIG[section]
    allowed = (
        business_fields
        | _ENTITY_ACTION_CONTROLS[action]
        | set(id_fields)
        | {name_field}
    )
    unknown = set(item) - allowed
    if unknown:
        names = "、".join(sorted(unknown))
        raise ValueError(f"{section} 包含无法持久化字段：{names}")
    fields = {
        key: deepcopy(value)
        for key, value in item.items()
        if key in business_fields
    }
    for field in id_fields:
        if field in item and (
            not isinstance(item[field], str) or not item[field]
        ):
            raise ValueError(f"{section} {field} 标识必须是非空字符串")
    if name_field in item and (
        not isinstance(item[name_field], str) or not item[name_field]
    ):
        raise ValueError(f"{section} {name_field} 标识必须是非空字符串")
    if action == "create":
        client_request_id = item.get("clientRequestId")
        if not isinstance(client_request_id, str) or not 16 <= len(client_request_id) <= 256:
            raise ValueError(f"{section} create 必须提供 16..256 字符的 clientRequestId")
        try:
            _ENTITY_CREATE_REQUESTS[section].model_validate(
                {**fields, "clientRequestId": client_request_id}
            )
        except ValueError as error:
            raise ValueError(f"{section} create 业务字段无效") from error
        return fields
    expected_updated_at = _require_entity_expected_updated_at(item, section)
    has_id = any(
        isinstance(item.get(field), str) and bool(item[field])
        for field in id_fields
    )
    has_name = isinstance(item.get(name_field), str) and bool(item[name_field])
    if not has_id and not has_name:
        raise ValueError(f"{section} {action} 缺少可解析目标")
    if action == "update" or fields:
        try:
            _ENTITY_UPDATE_REQUESTS[section].model_validate(
                {**fields, "expectedUpdatedAt": expected_updated_at}
            )
        except ValueError as error:
            raise ValueError(f"{section} {action} 业务字段无效") from error
    return fields


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

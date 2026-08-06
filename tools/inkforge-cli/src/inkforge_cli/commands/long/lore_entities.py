from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...json_types import JsonObject
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result
from .mutation_support import (
    encode_path_id,
    require_data_fields,
    require_expected_updated_at,
    require_payload_fields,
    require_string,
)

CHARACTER_FIELDS = frozenset({
    "name",
    "aliases",
    "gender",
    "age",
    "appearance",
    "personality",
    "identity",
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
})
LOCATION_FIELDS = frozenset({
    "name",
    "aliases",
    "type",
    "parentId",
    "climate",
    "culture",
    "description",
})
FACTION_FIELDS = frozenset({"name", "aliases", "type", "baseId", "description"})
ITEM_FIELDS = frozenset({
    "name",
    "aliases",
    "type",
    "rarity",
    "effect",
    "origin",
    "description",
    "ownerId",
})
GLOSSARY_FIELDS = frozenset({"term", "definition", "category"})

_CHARACTER_STATUSES = frozenset({"active", "missing", "dead", "imprisoned", "unknown"})


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    path_segment: str
    id_field: str
    business_fields: frozenset[str]
    create_required_fields: frozenset[str]


ENTITY_RESOURCES: dict[str, ResourceSpec] = {
    "character": ResourceSpec(
        "characters",
        "characterId",
        CHARACTER_FIELDS,
        frozenset({"name"}),
    ),
    "location": ResourceSpec(
        "locations",
        "locationId",
        LOCATION_FIELDS,
        frozenset({"name"}),
    ),
    "faction": ResourceSpec(
        "factions",
        "factionId",
        FACTION_FIELDS,
        frozenset({"name"}),
    ),
    "item": ResourceSpec(
        "items",
        "itemId",
        ITEM_FIELDS,
        frozenset({"name"}),
    ),
    "glossary": ResourceSpec(
        "glossary",
        "glossaryId",
        GLOSSARY_FIELDS,
        frozenset({"term", "definition"}),
    ),
}

_CREATE_REQUIRED_FIELDS = frozenset({"novelId", "clientRequestId", "data"})
_UPDATE_REQUIRED_BASE_FIELDS = frozenset({"novelId", "expectedUpdatedAt", "data"})
_DELETE_REQUIRED_BASE_FIELDS = frozenset({"novelId", "expectedUpdatedAt"})
_NO_FILE = FileOutputSpec(kind="none")
_Handler = Callable[[CliRuntime, JsonObject], JsonObject]


def _require_client_request_id(payload: JsonObject) -> str:
    value = require_string(payload, "clientRequestId")
    if not 16 <= len(value) <= 256:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "clientRequestId 长度必须在 16 到 256 个字符之间",
        )
    return value


def _validate_business_data(
    resource_name: str,
    resource: ResourceSpec,
    data: JsonObject,
    *,
    creating: bool,
) -> None:
    if creating:
        missing = sorted(resource.create_required_fields - set(data))
        if missing:
            raise CliInputError(
                "FIELD_REQUIRED",
                f"data 缺少创建必填字段：{', '.join(missing)}",
            )

    for field, value in data.items():
        if value is None:
            if creating and field in resource.create_required_fields:
                raise CliInputError(
                    "INVALID_DATA_FIELD",
                    f"data.{field} 不能为 null",
                )
            if creating and field == "currentStatus":
                raise CliInputError(
                    "INVALID_DATA_FIELD",
                    "data.currentStatus 不能为 null",
                )
            continue
        if not isinstance(value, str):
            raise CliInputError(
                "INVALID_DATA_FIELD",
                f"data.{field} 必须是字符串或 null",
            )
        if field in {"name", "term"} and not value.strip():
            raise CliInputError(
                "INVALID_DATA_FIELD",
                f"data.{field} 不能为空字符串",
            )
        if (
            resource_name == "character"
            and field == "currentStatus"
            and value not in _CHARACTER_STATUSES
        ):
            raise CliInputError(
                "INVALID_DATA_FIELD",
                "data.currentStatus 不是受支持的角色状态",
            )


def _collection_path(payload: JsonObject, resource: ResourceSpec) -> str:
    novel_id = encode_path_id(require_string(payload, "novelId"))
    return f"/api/v1/novels/{novel_id}/{resource.path_segment}"


def _entity_path(payload: JsonObject, resource: ResourceSpec) -> str:
    entity_id = encode_path_id(require_string(payload, resource.id_field))
    return f"{_collection_path(payload, resource)}/{entity_id}"


def _create_handler(resource_name: str, resource: ResourceSpec) -> _Handler:
    def create_entity(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
        require_payload_fields(payload, required=_CREATE_REQUIRED_FIELDS)
        data = require_data_fields(payload, allowed=resource.business_fields)
        _validate_business_data(resource_name, resource, data, creating=True)
        response = runtime.require_api().request(
            "POST",
            _collection_path(payload, resource),
            json={
                **data,
                "clientRequestId": _require_client_request_id(payload),
            },
        )
        return ensure_command_json_result(response)

    return create_entity


def _update_handler(resource_name: str, resource: ResourceSpec) -> _Handler:
    def update_entity(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
        require_payload_fields(
            payload,
            required=_UPDATE_REQUIRED_BASE_FIELDS | {resource.id_field},
        )
        data = require_data_fields(payload, allowed=resource.business_fields)
        _validate_business_data(resource_name, resource, data, creating=False)
        response = runtime.require_api().request(
            "PATCH",
            _entity_path(payload, resource),
            json={
                **data,
                "expectedUpdatedAt": require_expected_updated_at(
                    payload,
                    nullable=False,
                ),
            },
        )
        return ensure_command_json_result(response)

    return update_entity


def _delete_handler(resource: ResourceSpec) -> _Handler:
    def delete_entity(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
        require_payload_fields(
            payload,
            required=_DELETE_REQUIRED_BASE_FIELDS | {resource.id_field},
        )
        response = runtime.require_api().request(
            "DELETE",
            _entity_path(payload, resource),
            json={
                "expectedUpdatedAt": require_expected_updated_at(
                    payload,
                    nullable=False,
                ),
            },
        )
        return ensure_command_json_result(response)

    return delete_entity


def _command_spec(
    resource_name: str,
    operation: str,
    handler: _Handler,
) -> CommandSpec:
    return CommandSpec(
        name=f"long.lore.{resource_name}.{operation}",
        handler=handler,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=operation == "create",
    )


LORE_ENTITY_COMMAND_SPECS: tuple[CommandSpec, ...] = tuple(
    spec
    for resource_name, resource in ENTITY_RESOURCES.items()
    for spec in (
        _command_spec(resource_name, "create", _create_handler(resource_name, resource)),
        _command_spec(resource_name, "update", _update_handler(resource_name, resource)),
        _command_spec(resource_name, "delete", _delete_handler(resource)),
    )
)

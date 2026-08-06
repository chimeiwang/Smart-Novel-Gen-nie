from __future__ import annotations

from ...json_types import JsonObject
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import (
    CliInputError,
    CliRuntime,
    ensure_command_json_result,
    require_client_request_id,
)
from .mutation_support import (
    encode_path_id,
    require_data_fields,
    require_expected_updated_at,
    require_payload_fields,
    require_string,
)

_RELATION_CREATE_FIELDS = frozenset({
    "characterId",
    "targetId",
    "relationType",
    "intimacy",
    "description",
    "startDate",
    "endDate",
})
_RELATION_UPDATE_FIELDS = frozenset({
    "relationType",
    "intimacy",
    "description",
    "startDate",
    "endDate",
})
_EXPERIENCE_FIELDS = frozenset({"chapterId", "content", "order"})
_RELATION_TYPES = frozenset({
    "family",
    "master_student",
    "friend",
    "enemy",
    "ally",
    "lover",
    "rival",
    "subordinate",
    "acquaintance",
    "other",
})
_RELATION_NULLABLE_STRING_FIELDS = frozenset({
    "description",
    "startDate",
    "endDate",
})


def _require_create_request_id(payload: JsonObject) -> str:
    value = require_client_request_id(payload)
    if len(value) > 256:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "clientRequestId 长度必须在 16 到 256 个字符之间",
        )
    return value


def _require_nullable_string(data: JsonObject, field: str) -> None:
    value = data[field]
    if value is not None and not isinstance(value, str):
        raise CliInputError(
            "INVALID_DATA_FIELD",
            f"data.{field} 必须是字符串或 null",
        )


def _require_nullable_integer(data: JsonObject, field: str) -> int | None:
    value = data[field]
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise CliInputError(
            "INVALID_DATA_FIELD",
            f"data.{field} 必须是整数或 null",
        )
    return value


def _validate_relation_data(data: JsonObject, *, creating: bool) -> None:
    if creating:
        require_string(data, "characterId")
        require_string(data, "targetId")

    if "relationType" in data:
        relation_type = data["relationType"]
        if not isinstance(relation_type, str) or relation_type not in _RELATION_TYPES:
            raise CliInputError(
                "INVALID_DATA_FIELD",
                "data.relationType 不是受支持的关系类型",
            )
    elif creating:
        raise CliInputError("FIELD_REQUIRED", "data 缺少字段 relationType")

    if "intimacy" in data:
        intimacy = _require_nullable_integer(data, "intimacy")
        if intimacy is None:
            raise CliInputError(
                "INVALID_DATA_FIELD",
                "data.intimacy 不能为 null",
            )
        if intimacy is not None and not 0 <= intimacy <= 100:
            raise CliInputError(
                "INVALID_DATA_FIELD",
                "data.intimacy 必须在 0 到 100 之间",
            )

    for field in _RELATION_NULLABLE_STRING_FIELDS & data.keys():
        _require_nullable_string(data, field)


def _validate_experience_data(data: JsonObject, *, creating: bool) -> None:
    if creating:
        require_string(data, "content", allow_empty=True)
    elif "content" in data:
        _require_nullable_string(data, "content")
        if data["content"] is None:
            raise CliInputError(
                "INVALID_DATA_FIELD",
                "data.content 不能为 null",
            )

    if "chapterId" in data:
        _require_nullable_string(data, "chapterId")
    if "order" in data:
        order = _require_nullable_integer(data, "order")
        if order is None and not creating:
            raise CliInputError(
                "INVALID_DATA_FIELD",
                "data.order 不能为 null",
            )


def _novel_path(payload: JsonObject) -> str:
    return f"/api/v1/novels/{encode_path_id(require_string(payload, 'novelId'))}"


def create_relation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({"novelId", "clientRequestId", "data"}),
    )
    data = require_data_fields(payload, allowed=_RELATION_CREATE_FIELDS)
    _validate_relation_data(data, creating=True)
    response = runtime.require_api().request(
        "POST",
        f"{_novel_path(payload)}/relations",
        json={**data, "clientRequestId": _require_create_request_id(payload)},
    )
    return ensure_command_json_result(response)


def update_relation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({
            "novelId",
            "relationId",
            "expectedUpdatedAt",
            "data",
        }),
    )
    data = require_data_fields(payload, allowed=_RELATION_UPDATE_FIELDS)
    _validate_relation_data(data, creating=False)
    relation_id = encode_path_id(require_string(payload, "relationId"))
    response = runtime.require_api().request(
        "PATCH",
        f"{_novel_path(payload)}/relations/{relation_id}",
        json={
            **data,
            "expectedUpdatedAt": require_expected_updated_at(
                payload,
                nullable=False,
            ),
        },
    )
    return ensure_command_json_result(response)


def delete_relation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({"novelId", "relationId", "expectedUpdatedAt"}),
    )
    relation_id = encode_path_id(require_string(payload, "relationId"))
    response = runtime.require_api().request(
        "DELETE",
        f"{_novel_path(payload)}/relations/{relation_id}",
        json={
            "expectedUpdatedAt": require_expected_updated_at(
                payload,
                nullable=False,
            ),
        },
    )
    return ensure_command_json_result(response)


def create_experience(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({
            "novelId",
            "characterId",
            "clientRequestId",
            "data",
        }),
    )
    data = require_data_fields(payload, allowed=_EXPERIENCE_FIELDS)
    _validate_experience_data(data, creating=True)
    character_id = encode_path_id(require_string(payload, "characterId"))
    response = runtime.require_api().request(
        "POST",
        f"{_novel_path(payload)}/characters/{character_id}/experiences",
        json={**data, "clientRequestId": _require_create_request_id(payload)},
    )
    return ensure_command_json_result(response)


def update_experience(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({
            "novelId",
            "experienceId",
            "expectedUpdatedAt",
            "data",
        }),
    )
    data = require_data_fields(payload, allowed=_EXPERIENCE_FIELDS)
    _validate_experience_data(data, creating=False)
    experience_id = encode_path_id(require_string(payload, "experienceId"))
    response = runtime.require_api().request(
        "PATCH",
        f"{_novel_path(payload)}/experiences/{experience_id}",
        json={
            **data,
            "expectedUpdatedAt": require_expected_updated_at(
                payload,
                nullable=False,
            ),
        },
    )
    return ensure_command_json_result(response)


def delete_experience(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({"novelId", "experienceId", "expectedUpdatedAt"}),
    )
    experience_id = encode_path_id(require_string(payload, "experienceId"))
    response = runtime.require_api().request(
        "DELETE",
        f"{_novel_path(payload)}/experiences/{experience_id}",
        json={
            "expectedUpdatedAt": require_expected_updated_at(
                payload,
                nullable=False,
            ),
        },
    )
    return ensure_command_json_result(response)


_NO_FILE = FileOutputSpec(kind="none")

LORE_RELATIONSHIP_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.lore.relation.create",
        handler=create_relation,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.lore.relation.update",
        handler=update_relation,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.lore.relation.delete",
        handler=delete_relation,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.lore.experience.create",
        handler=create_experience,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.lore.experience.update",
        handler=update_experience,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.lore.experience.delete",
        handler=delete_experience,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

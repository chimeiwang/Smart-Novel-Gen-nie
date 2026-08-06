from __future__ import annotations

from ...json_types import JsonObject
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import (
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


def _novel_path(payload: JsonObject) -> str:
    return f"/api/v1/novels/{encode_path_id(require_string(payload, 'novelId'))}"


def create_relation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({"novelId", "clientRequestId", "data"}),
    )
    data = require_data_fields(payload, allowed=_RELATION_CREATE_FIELDS)
    require_string(data, "characterId")
    require_string(data, "targetId")
    require_string(data, "relationType")
    response = runtime.require_api().request(
        "POST",
        f"{_novel_path(payload)}/relations",
        json={**data, "clientRequestId": require_client_request_id(payload)},
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
    require_string(data, "content", allow_empty=True)
    character_id = encode_path_id(require_string(payload, "characterId"))
    response = runtime.require_api().request(
        "POST",
        f"{_novel_path(payload)}/characters/{character_id}/experiences",
        json={**data, "clientRequestId": require_client_request_id(payload)},
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

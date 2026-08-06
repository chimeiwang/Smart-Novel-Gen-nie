from __future__ import annotations

import re

from ...json_types import JsonObject
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result
from .mutation_support import (
    encode_path_id,
    require_content_source,
    require_expected_updated_at,
    require_payload_fields,
    require_string,
)

_REFERENCE_TYPES = frozenset({"note", "web", "book", "image", "custom"})
_CONTENT_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

_CREATE_REQUIRED_FIELDS = frozenset({
    "novelId",
    "clientRequestId",
    "title",
    "type",
})
_CREATE_OPTIONAL_FIELDS = frozenset({"content", "contentFile", "sourceUrl"})
_UPDATE_REQUIRED_FIELDS = frozenset({
    "novelId",
    "referenceId",
    "expectedUpdatedAt",
})
_UPDATE_OPTIONAL_FIELDS = frozenset({
    "title",
    "type",
    "sourceUrl",
    "content",
    "contentFile",
})
_DELETE_REQUIRED_FIELDS = frozenset({
    "novelId",
    "referenceId",
    "expectedUpdatedAt",
})
_REINDEX_REQUIRED_FIELDS = frozenset({
    "novelId",
    "referenceId",
    "expectedContentHash",
})


def _require_client_request_id(payload: JsonObject) -> str:
    value = require_string(payload, "clientRequestId")
    if not 16 <= len(value) <= 256:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "clientRequestId 长度必须在 16 到 256 个字符之间",
        )
    return value


def _require_title(payload: JsonObject) -> str:
    value = require_string(payload, "title")
    if not value.strip():
        raise CliInputError("INVALID_REFERENCE_TITLE", "title 不能为空白字符串")
    return value


def _require_reference_type(payload: JsonObject) -> str:
    value = require_string(payload, "type")
    if value not in _REFERENCE_TYPES:
        raise CliInputError(
            "INVALID_REFERENCE_TYPE",
            "type 必须是 note、web、book、image 或 custom",
        )
    return value


def _optional_source_url(payload: JsonObject) -> str | None:
    value = payload["sourceUrl"]
    if value is not None and not isinstance(value, str):
        raise CliInputError(
            "INVALID_SOURCE_URL",
            "sourceUrl 必须是字符串或显式 null",
        )
    return value


def _collection_path(payload: JsonObject) -> str:
    novel_id = encode_path_id(require_string(payload, "novelId"))
    return f"/api/v1/novels/{novel_id}/references"


def _reference_path(payload: JsonObject) -> str:
    reference_id = encode_path_id(require_string(payload, "referenceId"))
    return f"{_collection_path(payload)}/{reference_id}"


def create_reference(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=_CREATE_REQUIRED_FIELDS,
        optional=_CREATE_OPTIONAL_FIELDS,
    )
    body: JsonObject = {
        "clientRequestId": _require_client_request_id(payload),
        "title": _require_title(payload),
        "type": _require_reference_type(payload),
        "content": require_content_source(payload),
    }
    if "sourceUrl" in payload:
        body["sourceUrl"] = _optional_source_url(payload)
    path = _collection_path(payload)
    response = runtime.require_api().request("POST", path, json=body)
    return ensure_command_json_result(response)


def update_reference(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=_UPDATE_REQUIRED_FIELDS,
        optional=_UPDATE_OPTIONAL_FIELDS,
    )
    if not set(payload).intersection(_UPDATE_OPTIONAL_FIELDS):
        raise CliInputError("DATA_REQUIRED", "更新至少需要一个业务字段")

    body: JsonObject = {}
    if "title" in payload:
        body["title"] = _require_title(payload)
    if "type" in payload:
        body["type"] = _require_reference_type(payload)
    if "sourceUrl" in payload:
        body["sourceUrl"] = _optional_source_url(payload)
    if "content" in payload or "contentFile" in payload:
        body["content"] = require_content_source(payload)
    body["expectedUpdatedAt"] = require_expected_updated_at(
        payload,
        nullable=False,
    )
    path = _reference_path(payload)
    response = runtime.require_api().request("PATCH", path, json=body)
    return ensure_command_json_result(response)


def delete_reference(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(payload, required=_DELETE_REQUIRED_FIELDS)
    body: JsonObject = {
        "expectedUpdatedAt": require_expected_updated_at(
            payload,
            nullable=False,
        ),
    }
    path = _reference_path(payload)
    response = runtime.require_api().request("DELETE", path, json=body)
    return ensure_command_json_result(response)


def reindex_reference(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(payload, required=_REINDEX_REQUIRED_FIELDS)
    expected_content_hash = require_string(payload, "expectedContentHash")
    if _CONTENT_HASH_PATTERN.fullmatch(expected_content_hash) is None:
        raise CliInputError(
            "INVALID_CONTENT_HASH",
            "expectedContentHash 必须是 64 位小写十六进制字符串",
        )
    path = f"{_reference_path(payload)}/reindex"
    response = runtime.require_api().request(
        "POST",
        path,
        json={"expectedContentHash": expected_content_hash},
    )
    return ensure_command_json_result(response)


_NO_FILE = FileOutputSpec(kind="none")


REFERENCE_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.reference.create",
        handler=create_reference,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.reference.update",
        handler=update_reference,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.reference.delete",
        handler=delete_reference,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.reference.reindex",
        handler=reindex_reference,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

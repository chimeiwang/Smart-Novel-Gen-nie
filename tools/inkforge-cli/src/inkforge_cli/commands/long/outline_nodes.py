from __future__ import annotations

from collections.abc import Callable

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

_BUSINESS_FIELDS = frozenset({
    "title",
    "content",
    "kind",
    "status",
    "order",
    "parentId",
    "linkedChapterId",
    "estimatedWordCount",
    "actualWordCount",
    "chapterStartOrder",
    "chapterEndOrder",
})
_KINDS = frozenset({"stage", "plot_unit", "chapter_group"})
_STATUSES = frozenset({"planned", "in_progress", "completed", "skipped"})
_STRING_FIELDS = frozenset({"title", "content", "parentId", "linkedChapterId"})
_INTEGER_FIELDS = frozenset({
    "order",
    "estimatedWordCount",
    "actualWordCount",
    "chapterStartOrder",
    "chapterEndOrder",
})
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


def _validate_data(data: JsonObject, *, creating: bool) -> None:
    if creating:
        missing = sorted({"title", "kind"} - set(data))
        if missing:
            raise CliInputError(
                "FIELD_REQUIRED",
                f"data 缺少创建必填字段：{', '.join(missing)}",
            )

    for field in _STRING_FIELDS & set(data):
        value = data[field]
        if value is not None and not isinstance(value, str):
            raise CliInputError("INVALID_DATA_FIELD", f"data.{field} 必须是字符串或 null")
    if "title" in data and (
        not isinstance(data["title"], str) or not data["title"].strip()
    ):
        raise CliInputError("INVALID_DATA_FIELD", "data.title 必须是非空字符串")
    if "kind" in data and data["kind"] not in _KINDS:
        raise CliInputError("INVALID_DATA_FIELD", "data.kind 不是受支持的大纲节点类型")
    if "status" in data and data["status"] not in _STATUSES:
        raise CliInputError("INVALID_DATA_FIELD", "data.status 不是受支持的大纲节点状态")
    for field in _INTEGER_FIELDS & set(data):
        value = data[field]
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
            raise CliInputError("INVALID_DATA_FIELD", f"data.{field} 必须是整数或 null")
    for field in {"estimatedWordCount", "actualWordCount"} & set(data):
        value = data[field]
        if isinstance(value, int) and value < 0:
            raise CliInputError("INVALID_DATA_FIELD", f"data.{field} 不能小于 0")
    has_start = data.get("chapterStartOrder") is not None
    has_end = data.get("chapterEndOrder") is not None
    if creating and has_start != has_end:
        raise CliInputError("INVALID_DATA_FIELD", "章节范围必须同时提供起止序号")
    if has_start and has_end:
        start = data["chapterStartOrder"]
        end = data["chapterEndOrder"]
        if not isinstance(start, int) or not isinstance(end, int) or start <= 0 or start > end:
            raise CliInputError("INVALID_DATA_FIELD", "章节范围必须是有效的正整数闭区间")


def _collection_path(payload: JsonObject) -> str:
    novel_id = encode_path_id(require_string(payload, "novelId"))
    return f"/api/v1/novels/{novel_id}/outline-nodes"


def _item_path(payload: JsonObject) -> str:
    node_id = encode_path_id(require_string(payload, "outlineNodeId"))
    return f"{_collection_path(payload)}/{node_id}"


def create_node(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required={"novelId", "clientRequestId", "data"},
    )
    data = require_data_fields(payload, allowed=_BUSINESS_FIELDS)
    _validate_data(data, creating=True)
    response = runtime.require_api().request(
        "POST",
        _collection_path(payload),
        json={**data, "clientRequestId": _require_client_request_id(payload)},
    )
    return ensure_command_json_result(response)


def update_node(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required={"novelId", "outlineNodeId", "expectedUpdatedAt", "data"},
    )
    data = require_data_fields(payload, allowed=_BUSINESS_FIELDS)
    _validate_data(data, creating=False)
    response = runtime.require_api().request(
        "PATCH",
        _item_path(payload),
        json={
            **data,
            "expectedUpdatedAt": require_expected_updated_at(payload, nullable=False),
        },
    )
    return ensure_command_json_result(response)


def delete_node(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required={"novelId", "outlineNodeId", "expectedUpdatedAt"},
    )
    response = runtime.require_api().request(
        "DELETE",
        _item_path(payload),
        json={
            "expectedUpdatedAt": require_expected_updated_at(payload, nullable=False),
        },
    )
    return ensure_command_json_result(response)


def _spec(name: str, handler: _Handler, *, create: bool = False) -> CommandSpec:
    return CommandSpec(
        name=name,
        handler=handler,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=create,
    )


OUTLINE_NODE_COMMAND_SPECS = (
    _spec("long.outline-node.create", create_node, create=True),
    _spec("long.outline-node.update", update_node),
    _spec("long.outline-node.delete", delete_node),
)

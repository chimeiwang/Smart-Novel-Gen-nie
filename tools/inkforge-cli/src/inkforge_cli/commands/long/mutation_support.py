from __future__ import annotations

from urllib.parse import quote

from ...io import read_utf8_text_exact
from ...json_types import JsonObject
from ...runtime import CliInputError

_LOCAL_FIELDS = frozenset({"profile"})


def require_payload_fields(
    payload: JsonObject,
    *,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    allowed = set(required) | set(optional) | set(_LOCAL_FIELDS)
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CliInputError(
            "UNEXPECTED_FIELDS",
            f"命令包含不支持的字段：{', '.join(unknown)}",
        )
    missing = sorted(set(required) - set(payload))
    if missing:
        raise CliInputError(
            "FIELD_REQUIRED",
            f"命令缺少字段：{', '.join(missing)}",
        )


def require_string(
    payload: JsonObject,
    name: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def require_object(payload: JsonObject, name: str) -> JsonObject:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise CliInputError("OBJECT_REQUIRED", f"字段 {name} 必须是 JSON 对象")
    return value


def require_expected_updated_at(
    payload: JsonObject,
    *,
    nullable: bool,
) -> str | None:
    if "expectedUpdatedAt" not in payload:
        raise CliInputError("FIELD_REQUIRED", "缺少字段 expectedUpdatedAt")
    value = payload["expectedUpdatedAt"]
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value:
        message = "expectedUpdatedAt 必须是非空字符串"
        if nullable:
            message += "或显式 null"
        raise CliInputError(
            "INVALID_EXPECTED_UPDATED_AT",
            message,
        )
    return value


def require_content_source(payload: JsonObject) -> str:
    has_text = "content" in payload
    has_file = "contentFile" in payload
    if has_text == has_file:
        raise CliInputError(
            "CONTENT_SOURCE_REQUIRED",
            "content 与 contentFile 必须且只能提供一个",
        )
    if has_text:
        return require_string(payload, "content", allow_empty=True)
    return read_utf8_text_exact(require_string(payload, "contentFile"))


def require_data_fields(
    payload: JsonObject,
    *,
    allowed: set[str] | frozenset[str],
) -> JsonObject:
    data = require_object(payload, "data")
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise CliInputError(
            "UNEXPECTED_DATA_FIELDS",
            f"data 包含不支持的字段：{', '.join(unknown)}",
        )
    if not data:
        raise CliInputError("DATA_REQUIRED", "data 至少包含一个业务字段")
    return data


def encode_path_id(value: str) -> str:
    return quote(value, safe="")

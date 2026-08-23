"""章节影视化命令共用的严格 JSON 输入校验。"""

from __future__ import annotations

import json
from collections.abc import Collection
from typing import cast
from urllib.parse import quote

from ....io import read_utf8_text_exact
from ....json_types import JsonObject
from ....runtime import CliInputError, CliRuntime, ensure_command_json_result

_LOCAL_FIELDS = frozenset({"profile"})


def encode_id(value: str) -> str:
    return quote(value, safe="")


def require_fields(
    payload: JsonObject,
    *,
    required: Collection[str] = (),
    optional: Collection[str] = (),
    allow_output_file: bool = False,
) -> None:
    local_fields = set(_LOCAL_FIELDS)
    if allow_output_file:
        local_fields.add("outputFile")
    allowed = set(required) | set(optional) | local_fields
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
    min_length: int = 1,
    max_length: int | None = None,
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CliInputError("FIELD_REQUIRED", f"缺少非空字符串字段：{name}")
    if len(value) < min_length:
        raise CliInputError(
            "INVALID_FIELD",
            f"{name} 长度不能小于 {min_length}",
        )
    if max_length is not None and len(value) > max_length:
        raise CliInputError(
            "INVALID_FIELD",
            f"{name} 长度不能超过 {max_length}",
        )
    return value


def optional_string(
    payload: JsonObject,
    name: str,
    *,
    max_length: int | None = None,
) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CliInputError("INVALID_FIELD", f"{name} 必须是非空字符串或 null")
    if max_length is not None and len(value) > max_length:
        raise CliInputError(
            "INVALID_FIELD",
            f"{name} 长度不能超过 {max_length}",
        )
    return value


def require_client_request_id(payload: JsonObject) -> str:
    value = require_string(payload, "clientRequestId", max_length=128)
    if len(value.strip()) < 16:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "clientRequestId 长度必须为 16 到 128 个字符",
        )
    return value


def require_int(
    payload: JsonObject,
    name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = payload.get(name)
    if type(value) is not int:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是整数")
    if minimum is not None and value < minimum:
        raise CliInputError("INVALID_FIELD", f"{name} 不能小于 {minimum}")
    if maximum is not None and value > maximum:
        raise CliInputError("INVALID_FIELD", f"{name} 不能大于 {maximum}")
    return value


def enum_value(
    payload: JsonObject,
    name: str,
    allowed: Collection[str],
    *,
    default: str | None = None,
) -> str:
    raw = payload.get(name, default)
    if not isinstance(raw, str) or raw not in allowed:
        raise CliInputError(
            "INVALID_FIELD",
            f"{name} 必须是：{', '.join(sorted(allowed))}",
        )
    return raw


def string_list(
    payload: JsonObject,
    name: str,
    *,
    default: list[str] | None = None,
    max_items: int,
    unique: bool = True,
) -> list[str]:
    raw = payload.get(name, [] if default is None else default)
    if not isinstance(raw, list) or not all(
        isinstance(item, str) and bool(item.strip()) for item in raw
    ):
        raise CliInputError(
            "INVALID_FIELD",
            f"{name} 必须是非空字符串数组",
        )
    values = cast(list[str], raw)
    if len(values) > max_items:
        raise CliInputError(
            "INVALID_FIELD",
            f"{name} 最多包含 {max_items} 项",
        )
    if unique and len(set(values)) != len(values):
        raise CliInputError("INVALID_FIELD", f"{name} 不能包含重复项")
    return values


def json_object_source(
    payload: JsonObject,
    *,
    inline_field: str,
    file_field: str,
) -> JsonObject:
    has_inline = inline_field in payload
    has_file = file_field in payload
    if has_inline == has_file:
        raise CliInputError(
            "JSON_SOURCE_REQUIRED",
            f"{inline_field} 与 {file_field} 必须且只能提供一个",
        )
    if has_inline:
        value = payload.get(inline_field)
    else:
        path = require_string(payload, file_field)
        value = json.loads(read_utf8_text_exact(path))
    if not isinstance(value, dict):
        raise CliInputError(
            "OBJECT_REQUIRED",
            f"{inline_field} 必须是 JSON 对象",
        )
    return value


def text_source(
    payload: JsonObject,
    *,
    inline_field: str,
    file_field: str,
    max_length: int | None = None,
) -> str:
    has_inline = inline_field in payload
    has_file = file_field in payload
    if has_inline == has_file:
        raise CliInputError(
            "TEXT_SOURCE_REQUIRED",
            f"{inline_field} 与 {file_field} 必须且只能提供一个",
        )
    value = (
        payload.get(inline_field)
        if has_inline
        else read_utf8_text_exact(require_string(payload, file_field))
    )
    if not isinstance(value, str) or not value.strip():
        raise CliInputError("INVALID_FIELD", f"{inline_field} 内容不能为空")
    if max_length is not None and len(value) > max_length:
        raise CliInputError(
            "INVALID_FIELD",
            f"{inline_field} 长度不能超过 {max_length}",
        )
    return value


def request_json(
    runtime: CliRuntime,
    method: str,
    path: str,
    **kwargs: object,
) -> JsonObject:
    response = runtime.require_api().request(method, path, **kwargs)
    return ensure_command_json_result(response)


def as_json_object(value: object, message: str) -> JsonObject:
    if not isinstance(value, dict):
        from ....api import CoreResponseContractError

        raise CoreResponseContractError(message)
    return cast(JsonObject, value)

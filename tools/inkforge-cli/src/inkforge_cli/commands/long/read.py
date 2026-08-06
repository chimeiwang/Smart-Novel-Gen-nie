from __future__ import annotations

from urllib.parse import quote

from ...json_types import JsonObject
from ...runtime import (
    CliInputError,
    CliRuntime,
    ensure_command_json_result,
)

_LOCAL_READ_FIELDS = frozenset({"profile", "outputFile"})


def public_id(value: str) -> str:
    return quote(value, safe="")


def require_string(payload: JsonObject, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CliInputError("FIELD_REQUIRED", f"缺少非空字符串字段 {name}")
    return value


def validate_read_payload(
    payload: JsonObject,
    *,
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
) -> None:
    allowed = set(required) | set(optional) | _LOCAL_READ_FIELDS
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise CliInputError(
            "UNEXPECTED_FIELDS",
            f"命令包含不支持的字段：{', '.join(unknown)}",
        )
    for name in required:
        require_string(payload, name)


def query_fields(payload: JsonObject, names: tuple[str, ...]) -> JsonObject:
    return {name: payload[name] for name in names if name in payload}


def request_json(
    runtime: CliRuntime,
    path: str,
    *,
    params: JsonObject | None = None,
) -> JsonObject:
    kwargs = {} if params is None else {"params": params}
    response = runtime.require_api().request("GET", path, **kwargs)
    return ensure_command_json_result(response)


def list_novels(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload)
    return request_json(
        runtime,
        "/api/v1/novels",
        params={"storyLengthProfile": "long_serial"},
    )


def get_novel(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("novelId",))
    novel_id = require_string(payload, "novelId")
    return request_json(runtime, f"/api/v1/novels/{public_id(novel_id)}")


def list_chapters(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("novelId",))
    novel_id = require_string(payload, "novelId")
    return request_json(
        runtime,
        f"/api/v1/novels/{public_id(novel_id)}/chapters",
    )


def get_chapter(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("chapterId",))
    chapter_id = require_string(payload, "chapterId")
    return request_json(runtime, f"/api/v1/chapters/{public_id(chapter_id)}")


def list_sessions(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(
        payload,
        required=("novelId",),
        optional=("chapterId",),
    )
    return request_json(
        runtime,
        "/api/v1/writing/sessions",
        params=query_fields(payload, ("novelId", "chapterId")),
    )


def get_session(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("sessionId",))
    session_id = require_string(payload, "sessionId")
    return request_json(
        runtime,
        f"/api/v1/writing/sessions/{public_id(session_id)}",
    )

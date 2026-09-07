from __future__ import annotations

from ...json_types import JsonObject
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result
from .mutation_support import require_payload_fields


def create_session(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(
        payload,
        required=frozenset({"novelId", "chapterId"}),
        optional=frozenset({"title"}),
    )
    body: JsonObject = {}
    for name, maximum in (("novelId", 256), ("chapterId", 256), ("title", 500)):
        if name not in payload:
            continue
        value = payload[name]
        nullable = name == "title"
        if not (nullable and value is None) and (
            not isinstance(value, str) or not 1 <= len(value) <= maximum
        ):
            suffix = "或 null" if nullable else ""
            raise CliInputError(
                "INVALID_FIELD", f"{name} 必须是长度 1 到 {maximum} 的字符串{suffix}"
            )
        body[name] = value
    # 原公共接口无幂等字段；连接结果不确定交调用方回读核对，不自动重试。
    response = runtime.require_api().request("POST", "/api/v1/writing/sessions", json=body)
    return ensure_command_json_result(response)

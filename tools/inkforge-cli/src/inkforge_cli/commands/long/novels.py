from __future__ import annotations

from ...json_types import JsonObject
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result

_TEXT_FIELDS = (
    "summary",
    "genre",
    "protagonist",
    "coreSellingPoint",
    "readerPromise",
    "firstChapterGoal",
)
_ALLOWED_FIELDS = frozenset({"profile", "name", "targetTotalWordCount", *_TEXT_FIELDS})


def _validate_payload(payload: JsonObject) -> JsonObject:
    unknown = sorted(set(payload) - _ALLOWED_FIELDS)
    if unknown:
        raise CliInputError(
            "UNEXPECTED_FIELDS",
            f"命令包含不支持的字段：{', '.join(unknown)}",
        )

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CliInputError("FIELD_REQUIRED", "缺少非空字符串字段：name")

    body: JsonObject = {"name": name.strip()}
    for field in _TEXT_FIELDS:
        value = payload.get(field)
        if value is not None and not isinstance(value, str):
            raise CliInputError(
                "INVALID_FIELD",
                f"{field} 必须是字符串或 null",
            )
        if field in payload:
            body[field] = value

    target_word_count = payload.get("targetTotalWordCount")
    if target_word_count is not None and (
        isinstance(target_word_count, bool)
        or not isinstance(target_word_count, int)
        or target_word_count <= 0
    ):
        raise CliInputError(
            "INVALID_FIELD",
            "targetTotalWordCount 必须是大于 0 的整数或 null",
        )
    if "targetTotalWordCount" in payload:
        body["targetTotalWordCount"] = target_word_count

    body["storyLengthProfile"] = "long_serial"
    return body


def create_novel(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    response = runtime.require_api().request(
        "POST",
        "/api/v1/novels",
        json=_validate_payload(payload),
    )
    return ensure_command_json_result(response)

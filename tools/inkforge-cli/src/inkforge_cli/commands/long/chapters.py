from __future__ import annotations

from urllib.parse import quote

from ...io import read_utf8_text_exact
from ...json_types import JsonObject, JsonValue
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result


def _require_string(
    payload: JsonObject,
    name: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or (not allow_empty and not value):
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def _require_expected_updated_at(
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
        raise CliInputError(
            "INVALID_EXPECTED_UPDATED_AT",
            "expectedUpdatedAt 必须是非空字符串",
        )
    return value


def _chapter_path(payload: JsonObject) -> str:
    chapter_id = _require_string(payload, "chapterId")
    return f"/api/v1/chapters/{quote(chapter_id, safe='')}"


def _chapter_content(payload: JsonObject) -> str:
    has_content = "content" in payload
    has_content_file = "contentFile" in payload
    if has_content == has_content_file:
        raise CliInputError(
            "CONTENT_SOURCE_REQUIRED",
            "content 与 contentFile 必须且只能提供一个",
        )
    if has_content:
        return _require_string(payload, "content", allow_empty=True)
    content_file = _require_string(payload, "contentFile")
    return read_utf8_text_exact(content_file)


def save(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    response = runtime.require_api().request(
        "PATCH",
        _chapter_path(payload),
        json={
            "title": _require_string(payload, "title"),
            "content": _chapter_content(payload),
            "expectedUpdatedAt": _require_expected_updated_at(
                payload,
                nullable=False,
            ),
        },
    )
    return ensure_command_json_result(response)


def update_status(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    response = runtime.require_api().request(
        "PATCH",
        f"{_chapter_path(payload)}/status",
        json={
            "status": _require_string(payload, "status"),
            "expectedUpdatedAt": _require_expected_updated_at(
                payload,
                nullable=False,
            ),
        },
    )
    return ensure_command_json_result(response)


def save_progress(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    content: JsonValue = payload.get("content")
    if not isinstance(content, str):
        raise CliInputError("FIELD_REQUIRED", "缺少字符串字段 content")
    response = runtime.require_api().request(
        "PUT",
        f"{_chapter_path(payload)}/progress",
        json={
            "content": content,
            "expectedUpdatedAt": _require_expected_updated_at(
                payload,
                nullable=True,
            ),
        },
    )
    return ensure_command_json_result(response)


_NO_FILE = FileOutputSpec(kind="none")

CHAPTER_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.chapter.save",
        handler=save,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.chapter.status",
        handler=update_status,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.chapter.progress.save",
        handler=save_progress,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

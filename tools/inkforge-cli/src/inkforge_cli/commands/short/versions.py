from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ...io import write_large_result
from ...json_types import JsonObject
from ...runtime import (
    CliInputError,
    CliRuntime,
    ensure_command_json_result,
    require_client_request_id,
)
from .snapshots import ensure_snapshot_clean

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_FIELDS = (
    "profile",
    "novelId",
    "versionId",
    "outputFile",
    "outputDirectory",
    "manifestPath",
)


def _require_string(payload: JsonObject, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def _require_confirmation_hash(payload: JsonObject) -> str:
    value = payload.get("confirmationHash")
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise CliInputError(
            "INVALID_CONFIRMATION_HASH",
            "confirmationHash 必须是 64 位小写 SHA-256",
        )
    return value


def _ensure_clean_snapshot(payload: JsonObject, *, novel_id: str) -> None:
    manifest_path = payload.get("manifestPath")
    if not isinstance(manifest_path, str) or not manifest_path:
        raise CliInputError(
            "MANIFEST_REQUIRED",
            "写操作必须提供 short.pull 生成的 manifestPath",
        )
    ensure_snapshot_clean(manifest_path, novel_id=novel_id)


def _public_id(value: str) -> str:
    return quote(value, safe="")


def _without(payload: JsonObject, *names: str) -> JsonObject:
    excluded = set(names)
    return {key: value for key, value in payload.items() if key not in excluded}


def _root(payload: JsonObject) -> tuple[str, str]:
    novel_id = _require_string(payload, "novelId")
    return novel_id, f"/api/v1/novels/{_public_id(novel_id)}"


def _write_response_file(
    response: Any,
    *,
    payload: JsonObject,
    field: str,
    default_name: str,
) -> Any:
    if not isinstance(response, dict) or field not in response:
        return response
    output_file = payload.get("outputFile")
    if output_file is None:
        output_directory = payload.get("outputDirectory")
        if isinstance(output_directory, str) and output_directory:
            output_file = str(Path(output_directory) / default_name)
    if not isinstance(output_file, str) or not output_file:
        raise CliInputError(
            "OUTPUT_FILE_REQUIRED",
            f"响应包含完整 {field}，必须提供 outputFile 或 outputDirectory",
        )

    raw_value = response[field]
    content = (
        raw_value
        if isinstance(raw_value, str)
        else json.dumps(raw_value, ensure_ascii=False, indent=2) + "\n"
    )
    result = dict(response)
    del result[field]
    result[f"{field}File"] = write_large_result(output_file, content)
    return result


def preview(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    _, root = _root(payload)
    response = runtime.require_api().request(
        "POST",
        f"{root}/versions/preview",
        json=_without(payload, *_LOCAL_FIELDS),
    )
    result = _write_response_file(
        response,
        payload=payload,
        field="diff",
        default_name="version-preview-diff.json",
    )
    return ensure_command_json_result(result)


def submit(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    novel_id, root = _root(payload)
    require_client_request_id(payload)
    _require_confirmation_hash(payload)
    _ensure_clean_snapshot(payload, novel_id=novel_id)
    response = runtime.require_api().request(
        "POST",
        f"{root}/versions",
        json=_without(payload, *_LOCAL_FIELDS),
    )
    return ensure_command_json_result(response)


def list_versions(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    _, root = _root(payload)
    response = runtime.require_api().request(
        "GET",
        f"{root}/versions",
        params=_without(payload, *_LOCAL_FIELDS),
    )
    return ensure_command_json_result(response)


def diff(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    _, root = _root(payload)
    response = runtime.require_api().request(
        "GET",
        f"{root}/version-diff",
        params=_without(payload, *_LOCAL_FIELDS),
    )
    if not response:
        return ensure_command_json_result(response)
    output_file = payload.get("outputFile")
    if output_file is None:
        output_directory = payload.get("outputDirectory")
        if isinstance(output_directory, str) and output_directory:
            output_file = str(Path(output_directory) / "version-diff.json")
    if not isinstance(output_file, str) or not output_file:
        raise CliInputError(
            "OUTPUT_FILE_REQUIRED",
            "完整 Diff 必须提供 outputFile 或 outputDirectory",
        )
    serialized = json.dumps(response, ensure_ascii=False, indent=2) + "\n"
    return ensure_command_json_result(
        {"diffFile": write_large_result(output_file, serialized)}
    )


def get(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    _, root = _root(payload)
    version_id = _require_string(payload, "versionId")
    response = runtime.require_api().request(
        "GET",
        f"{root}/versions/{_public_id(version_id)}",
    )
    result = _write_response_file(
        response,
        payload=payload,
        field="content",
        default_name=f"version-{version_id}.txt",
    )
    return ensure_command_json_result(result)


def adopt(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _apply_action(runtime, payload, action="adopt")


def restore(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _apply_action(runtime, payload, action="restore")


def _apply_action(
    runtime: CliRuntime,
    payload: JsonObject,
    *,
    action: str,
) -> JsonObject:
    novel_id, root = _root(payload)
    version_id = _require_string(payload, "versionId")
    require_client_request_id(payload)
    _require_confirmation_hash(payload)
    _ensure_clean_snapshot(payload, novel_id=novel_id)
    response = runtime.require_api().request(
        "POST",
        f"{root}/versions/{_public_id(version_id)}/{action}",
        json=_without(payload, *_LOCAL_FIELDS),
    )
    return ensure_command_json_result(response)

from __future__ import annotations

from urllib.parse import quote

from ...json_types import JsonObject, JsonValue
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import (
    CliInputError,
    CliRuntime,
    ensure_command_json_result,
    require_client_request_id,
)

_RUN_FIELDS = {"profile", "checkId", "clientRequestId", "taskId", "message"}
_CAS_FIELDS = {"profile", "checkId", "expectedUpdatedAt"}


def _require_string(payload: JsonObject, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def _require_stable_client_request_id(payload: JsonObject) -> str:
    value = require_client_request_id(payload)
    if len(value) > 128:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "clientRequestId 长度必须为 16 到 128 个字符",
        )
    return value


def _reject_unexpected_fields(payload: JsonObject, allowed: set[str]) -> None:
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        raise CliInputError(
            "UNEXPECTED_FIELD",
            f"命令不接受字段：{unexpected[0]}",
        )


def _check_path(payload: JsonObject) -> str:
    check_id = _require_string(payload, "checkId")
    return f"/api/v1/quality-checks/{quote(check_id, safe='')}"


def _expected_updated_at(payload: JsonObject) -> str:
    if "expectedUpdatedAt" not in payload:
        raise CliInputError("FIELD_REQUIRED", "缺少字段 expectedUpdatedAt")
    value = payload["expectedUpdatedAt"]
    if not isinstance(value, str) or not value:
        raise CliInputError(
            "INVALID_EXPECTED_UPDATED_AT",
            "expectedUpdatedAt 必须是非空字符串",
        )
    return value


def _optional_string_or_null(payload: JsonObject, name: str) -> JsonValue:
    value = payload[name]
    if value is not None and not isinstance(value, str):
        raise CliInputError(
            "INVALID_FIELD",
            f"{name} 必须是字符串或 null",
        )
    return value


def run(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    _reject_unexpected_fields(payload, _RUN_FIELDS)
    body: JsonObject = {
        "clientRequestId": _require_stable_client_request_id(payload),
    }
    for name in ("taskId", "message"):
        if name in payload:
            body[name] = _optional_string_or_null(payload, name)
    response = runtime.require_api().request(
        "POST",
        f"{_check_path(payload)}/run",
        json=body,
    )
    return ensure_command_json_result(response)


def _update(
    runtime: CliRuntime,
    payload: JsonObject,
    *,
    status: str,
    reset_result: bool,
) -> JsonObject:
    _reject_unexpected_fields(payload, _CAS_FIELDS)
    response = runtime.require_api().request(
        "PATCH",
        _check_path(payload),
        json={
            "status": status,
            "resetResult": reset_result,
            "expectedUpdatedAt": _expected_updated_at(payload),
        },
    )
    return ensure_command_json_result(response)


def skip(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _update(
        runtime,
        payload,
        status="skipped",
        reset_result=False,
    )


def reset(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _update(
        runtime,
        payload,
        status="pending",
        reset_result=True,
    )


_NO_FILE = FileOutputSpec(kind="none")

QUALITY_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.quality.run",
        handler=run,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.quality.skip",
        handler=skip,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.quality.reset",
        handler=reset,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

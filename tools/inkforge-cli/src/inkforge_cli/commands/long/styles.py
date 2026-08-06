from __future__ import annotations

from ...json_types import JsonObject
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result
from .mutation_support import encode_path_id, require_payload_fields, require_string

_APPLY_REQUIRED_FIELDS = frozenset({"novelId", "styleId", "expectedStyleId"})
_CLEAR_REQUIRED_FIELDS = frozenset({"novelId", "expectedStyleId"})


def _require_expected_style_id(payload: JsonObject) -> str | None:
    value = payload["expectedStyleId"]
    if value is None:
        return None
    if not isinstance(value, str):
        raise CliInputError(
            "INVALID_EXPECTED_STYLE_ID",
            "expectedStyleId 必须是字符串或显式 null",
        )
    return value


def _applied_style_path(payload: JsonObject) -> str:
    novel_id = encode_path_id(require_string(payload, "novelId"))
    return f"/api/v1/novels/{novel_id}/applied-style"


def _set_applied_style(
    runtime: CliRuntime,
    payload: JsonObject,
    *,
    style_id: str | None,
) -> JsonObject:
    path = _applied_style_path(payload)
    response = runtime.require_api().request(
        "PATCH",
        path,
        json={
            "styleId": style_id,
            "expectedStyleId": _require_expected_style_id(payload),
        },
    )
    return ensure_command_json_result(response)


def apply_style(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(payload, required=_APPLY_REQUIRED_FIELDS)
    style_id = require_string(payload, "styleId")
    return _set_applied_style(runtime, payload, style_id=style_id)


def clear_style(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(payload, required=_CLEAR_REQUIRED_FIELDS)
    return _set_applied_style(runtime, payload, style_id=None)


_NO_FILE = FileOutputSpec(kind="none")


STYLE_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.style.apply",
        handler=apply_style,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.style.clear",
        handler=clear_style,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

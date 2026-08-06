from __future__ import annotations

from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from ...api import SseConnectionError
from ...json_types import JsonObject
from ...runtime import (
    CliInputError,
    CliRuntime,
    ensure_command_json_result,
    require_client_request_id,
)
from .snapshots import ensure_snapshot_clean

_MAX_SSE_RECONNECTS = 3
_START_FIELDS = (
    "clientRequestId",
    "novelId",
    "documentType",
    "chapterId",
    "baseVersionId",
    "sourceOutlineVersionId",
    "selectionStart",
    "selectionEnd",
    "selectedTextHash",
    "userInstruction",
)


def _require_string(payload: JsonObject, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
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


def start(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_client_request_id(payload)
    novel_id = _require_string(payload, "novelId")
    _ensure_clean_snapshot(payload, novel_id=novel_id)
    operation = payload.get("operation")
    operation_mapping = {
        "outline": "generate_outline",
        "manuscript": "generate_manuscript",
        "selection": "replace_selection",
        "full_check": "full_check",
    }
    if not isinstance(operation, str) or operation not in operation_mapping:
        raise CliInputError(
            "INVALID_AGENT_OPERATION",
            "operation 只能是 outline、manuscript、selection 或 full_check",
        )
    if operation == "selection":
        instruction = payload.get("userInstruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise CliInputError(
                "FIELD_REQUIRED",
                "selection 操作必须提供非空 userInstruction",
            )
    body = {field: payload[field] for field in _START_FIELDS if field in payload}
    body["workflow"] = "short_medium"
    body["operation"] = operation_mapping[operation]
    response = runtime.require_api().request(
        "POST",
        "/api/v1/writing/runs",
        json=body,
    )
    return ensure_command_json_result(response)


def watch(
    runtime: CliRuntime,
    payload: JsonObject,
) -> Generator[JsonObject, None, int]:
    api = runtime.require_api()
    task_id = _require_string(payload, "taskId")
    last_event_id = payload.get("lastEventId")
    if last_event_id is not None and not isinstance(last_event_id, str):
        raise CliInputError("INVALID_LAST_EVENT_ID", "lastEventId 必须是字符串")
    reconnects = 0
    while True:
        disconnected = False
        try:
            for event in api.iter_sse(task_id, last_event_id):
                event_id = event.get("id") if isinstance(event, dict) else None
                if isinstance(event_id, str) and event_id:
                    last_event_id = event_id
                yield ensure_command_json_result({"type": "event", **event})
        except SseConnectionError:
            disconnected = True

        state: Any | None = None
        if not disconnected or reconnects >= _MAX_SSE_RECONNECTS:
            state = api.request(
                "GET",
                f"/api/v1/writing/runs/{_public_id(task_id)}",
            )
            if _is_terminal_run_state(state):
                yield ensure_command_json_result({"type": "terminal", "data": state})
                return 0
        if reconnects >= _MAX_SSE_RECONNECTS:
            yield ensure_command_json_result({"type": "state", "data": state})
            yield ensure_command_json_result(
                {
                    "type": "error",
                    "error": {
                        "code": "SSE_RECONNECT_EXHAUSTED",
                        "message": "SSE 重连次数已达上限，任务仍未进入终态",
                    },
                },
            )
            return 5
        reconnects += 1


def _is_terminal_run_state(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    phase = state.get("phase")
    command_status = state.get("commandStatus")
    return (
        phase in {"completed", "error", "cancelled", "canceled"}
        or command_status in {"succeeded", "failed"}
    )

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from ...api import CoreResponseContractError, SseConnectionError
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
    observed_engine: int | None = None
    while True:
        disconnected = False
        try:
            for event in api.iter_sse(task_id, last_event_id):
                cursor, event_engine, terminal_hint = _event_observation(event, task_id)
                if cursor is not None:
                    last_event_id = cursor
                if event_engine is not None:
                    if observed_engine is not None and observed_engine != event_engine:
                        raise CoreResponseContractError(
                            "同一任务的 engineVersion 在观察期间发生变化"
                        )
                    observed_engine = event_engine
                yield ensure_command_json_result({"type": "event", **event})
                if terminal_hint:
                    break
        except SseConnectionError:
            disconnected = True

        state: Any | None = None
        if not disconnected or observed_engine == 2 or reconnects >= _MAX_SSE_RECONNECTS:
            state = api.request(
                "GET",
                f"/api/v1/writing/runs/{_public_id(task_id)}",
            )
            engine = _engine_version(state)
            if observed_engine is not None and observed_engine != engine:
                raise CoreResponseContractError("同一任务的 engineVersion 在观察期间发生变化")
            observed_engine = engine
            terminal_exit = _terminal_exit(state, task_id)
            if terminal_exit is not None:
                yield ensure_command_json_result({"type": "terminal", "data": state})
                return terminal_exit
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
    return _terminal_exit(state) is not None


def _engine_version(state: Any) -> int:
    if not isinstance(state, dict):
        raise CoreResponseContractError("任务状态不是 JSON 对象")
    value = state.get("engineVersion", 1)
    if type(value) is not int or value not in {1, 2}:
        raise CoreResponseContractError("任务状态缺少有效 engineVersion")
    return value


def _terminal_exit(state: Any, task_id: str | None = None) -> int | None:
    if not isinstance(state, dict):
        return None
    if _engine_version(state) == 2:
        if (
            state.get("workflow") != "short_medium"
            or (task_id is not None and state.get("runId") != task_id)
            or not isinstance(state.get("activeSteps"), list)
            or not isinstance(state.get("status"), str)
            or state.get("status") not in {"pending", "running", "completed", "failed", "cancelled"}
        ):
            raise CoreResponseContractError("V2 中短篇任务身份或状态无效")
        for field in ("artifact", "error", "checkReport"):
            if state.get(field) is not None and not isinstance(state[field], dict):
                raise CoreResponseContractError("V2 中短篇任务结果字段无效")
        candidate = state.get("candidateVersionId")
        if candidate is not None and (not isinstance(candidate, str) or not candidate):
            raise CoreResponseContractError("V2 中短篇候选版本身份无效")
        status = state["status"]
        if status in {"failed", "cancelled"}:
            return 5
        if status != "completed":
            return None
        if state.get("operation") == "full_check":
            report = state.get("checkReport")
            if (
                candidate is not None
                or not isinstance(report, dict)
                or not isinstance(report.get("text"), str)
                or not report["text"]
            ):
                raise CoreResponseContractError("V2 全文检查缺少权威完整报告")
        elif (
            not isinstance(state.get("operation"), str)
            or state.get("operation")
            not in {"generate_outline", "generate_manuscript", "replace_selection"}
            or candidate is None
            or state.get("checkReport") is not None
        ):
            raise CoreResponseContractError("V2 中短篇生成缺少权威候选版本")
        return 0
    phase = state.get("phase")
    command_status = state.get("commandStatus")
    terminal = phase in {"completed", "error", "cancelled", "canceled"} or command_status in {
        "succeeded",
        "failed",
    }
    return 0 if terminal else None


def _event_observation(event: Any, task_id: str) -> tuple[str | None, int | None, bool]:
    if not isinstance(event, dict):
        raise CoreResponseContractError("SSE 事件不是 JSON 对象")
    raw_cursor = event.get("id")
    if raw_cursor is None or raw_cursor == "":
        cursor = None
    elif isinstance(raw_cursor, str):
        cursor = raw_cursor
    elif type(raw_cursor) is int and raw_cursor >= 0:
        cursor = str(raw_cursor)
    else:
        raise CoreResponseContractError("SSE 事件包含无效游标")
    data = event.get("data")
    engine = _engine_version(data) if isinstance(data, dict) and "engineVersion" in data else None
    terminal_hint = False
    if engine == 2 and isinstance(data, dict):
        if "runId" in data and data["runId"] != task_id:
            raise CoreResponseContractError("V2 SSE 事件不属于当前任务")
        terminal_hint = event.get("event") in ("completed", "failed", "cancelled")
        if event.get("event") == "run_snapshot":
            base = data.get("baseSequence")
            snapshot = data.get("snapshot")
            if (
                type(base) is not int
                or base < 0
                or not isinstance(snapshot, dict)
                or (cursor is not None and cursor != str(base))
            ):
                raise CoreResponseContractError("V2 run_snapshot 游标或快照无效")
            cursor = str(base)
            terminal_hint = snapshot.get("status") in ("completed", "failed", "cancelled")
    return cursor, engine, terminal_hint

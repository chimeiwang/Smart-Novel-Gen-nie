from __future__ import annotations

from collections.abc import Generator

from ...api import CoreTransportError, SseConnectionError
from ...json_types import JsonObject
from ...runtime import CliRuntime, CoreResponseContractError
from .read import (
    public_id,
    query_fields,
    request_json,
    require_string,
    validate_read_payload,
)


def list_tasks(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    filters = (
        "novelId",
        "chapterId",
        "writingSessionId",
        "operation",
        "outcome",
        "cursor",
        "limit",
    )
    validate_read_payload(
        payload,
        required=("novelId",),
        optional=filters[1:],
    )
    return request_json(
        runtime,
        "/api/v1/writing/runs",
        params=query_fields(payload, filters),
    )


def get_task(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    validate_read_payload(payload, required=("taskId",))
    task_id = require_string(payload, "taskId")
    return request_json(
        runtime,
        f"/api/v1/writing/runs/{public_id(task_id)}",
    )


_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 5.0, 10.0)
_UNREACHABLE_TIMEOUT_SECONDS = 300.0
_RUNNING_STATES = frozenset({"queued", "running"})
_SUCCESS_STATES = frozenset({"waiting_user", "succeeded"})
_FAILED_STATES = frozenset({"failed", "cancelled", "inconsistent"})
_OUTCOME_STATES = _RUNNING_STATES | _SUCCESS_STATES | _FAILED_STATES


def watch(
    runtime: CliRuntime,
    payload: JsonObject,
) -> Generator[JsonObject, None, int]:
    validate_read_payload(
        payload,
        required=("taskId",),
        allow_output_file=False,
    )
    task_id = require_string(payload, "taskId")
    api = runtime.require_api()
    task_path = f"/api/v1/writing/runs/{public_id(task_id)}"
    last_event_id: str | None = None
    last_snapshot: JsonObject | None = None
    unreachable_since: float | None = None
    backoff_index = 0
    snapshot_emitted = False
    needs_status = True
    backoff_after_status = False

    try:
        while True:
            if needs_status:
                try:
                    snapshot = request_json(runtime, task_path)
                except CoreTransportError:
                    now = runtime.dependencies.monotonic_fn()
                    if unreachable_since is None:
                        unreachable_since = now
                    elif now - unreachable_since > _UNREACHABLE_TIMEOUT_SECONDS:
                        yield _unreachable_frame(
                            task_id,
                            last_event_id,
                            last_snapshot,
                        )
                        return 5
                    backoff_index = _sleep_with_backoff(runtime, backoff_index)
                    backoff_after_status = False
                    continue

                unreachable_since = None
                last_snapshot = snapshot
                needs_status = False
                state = _outcome_state(snapshot)
                if not snapshot_emitted:
                    yield {"type": "snapshot", "data": snapshot}
                    snapshot_emitted = True

                terminal = _terminal_result(task_id, snapshot, state)
                if terminal is not None:
                    frame, exit_code = terminal
                    yield frame
                    return exit_code

                if backoff_after_status:
                    backoff_index = _sleep_with_backoff(runtime, backoff_index)
                    backoff_after_status = False

            received_event = False
            try:
                for raw_event in api.iter_sse(task_id, last_event_id):
                    frame, event_id = _event_frame(raw_event)
                    if event_id is not None:
                        last_event_id = event_id
                    received_event = True
                    yield frame
            except SseConnectionError:
                pass

            if received_event:
                backoff_index = 0
            needs_status = True
            backoff_after_status = True
    except KeyboardInterrupt:
        yield {
            "type": "error",
            "error": {
                "code": "WATCH_INTERRUPTED",
                "message": "仅停止观察，服务端任务未取消",
                "taskId": task_id,
                "lastEventId": last_event_id,
            },
        }
        return 130


def _sleep_with_backoff(runtime: CliRuntime, index: int) -> int:
    delay = _BACKOFF_SECONDS[min(index, len(_BACKOFF_SECONDS) - 1)]
    runtime.dependencies.sleep_fn(delay)
    return min(index + 1, len(_BACKOFF_SECONDS) - 1)


def _outcome_state(snapshot: JsonObject) -> str:
    outcome = snapshot.get("outcome")
    state = outcome.get("state") if isinstance(outcome, dict) else None
    if not isinstance(state, str) or state not in _OUTCOME_STATES:
        raise CoreResponseContractError("任务状态响应缺少有效的 outcome.state")
    return state


def _waiting_artifact_id(snapshot: JsonObject) -> str:
    outcome = snapshot.get("outcome")
    result = outcome.get("result") if isinstance(outcome, dict) else None
    artifact_id = result.get("id") if isinstance(result, dict) else None
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CoreResponseContractError("waiting_user 任务缺少权威 Artifact ID")
    return artifact_id


def _terminal_result(
    task_id: str,
    snapshot: JsonObject,
    state: str,
) -> tuple[JsonObject, int] | None:
    if state == "waiting_user":
        return (
            {
                "type": "waiting_user",
                "taskId": task_id,
                "artifactId": _waiting_artifact_id(snapshot),
                "data": snapshot,
            },
            0,
        )
    if state == "succeeded":
        return {"type": "terminal", "data": snapshot}, 0
    if state in _FAILED_STATES:
        return {"type": "terminal", "data": snapshot}, 5
    return None


def _event_frame(event: object) -> tuple[JsonObject, str | None]:
    if not isinstance(event, dict):
        raise CoreResponseContractError("SSE 事件不是 JSON 对象")
    raw_event_id = event.get("id")
    event_id = raw_event_id if isinstance(raw_event_id, str) and raw_event_id else None
    raw_event_name = event.get("event", "message")
    event_name = raw_event_name if isinstance(raw_event_name, str) else "message"
    frame = {
        "type": "event",
        "id": raw_event_id if isinstance(raw_event_id, str) else None,
        "event": event_name,
        "data": event.get("data"),
    }
    return frame, event_id


def _unreachable_frame(
    task_id: str,
    last_event_id: str | None,
    last_snapshot: JsonObject | None,
) -> JsonObject:
    state = _outcome_state(last_snapshot) if last_snapshot is not None else None
    return {
        "type": "error",
        "error": {
            "code": "WATCH_CORE_UNREACHABLE",
            "message": "Core API 连续不可达超过 300 秒；仅停止观察，服务端任务未取消",
            "taskId": task_id,
            "lastEventId": last_event_id,
            "state": state,
        },
    }

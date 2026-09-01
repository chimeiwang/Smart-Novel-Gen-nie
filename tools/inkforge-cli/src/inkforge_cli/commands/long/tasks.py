from __future__ import annotations

from collections.abc import Generator

from ...api import (
    CoreApiError,
    CoreResponseContractError,
    CoreTransportError,
    SseConnectionError,
)
from ...json_types import JsonObject
from ...runtime import CliRuntime
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
_V1_RUNNING_STATES = frozenset({"queued", "running"})
_V1_SUCCESS_STATES = frozenset({"waiting_user", "succeeded"})
_V1_FAILED_STATES = frozenset({"failed", "cancelled", "inconsistent"})
_V1_OUTCOME_STATES = _V1_RUNNING_STATES | _V1_SUCCESS_STATES | _V1_FAILED_STATES
_V2_RUNNING_STATUSES = frozenset({"pending", "running"})
_V2_SUCCESS_STATUSES = frozenset({"waiting_user", "completed"})
_V2_FAILED_STATUSES = frozenset({"failed", "cancelled"})
_V2_RUN_STATUSES = _V2_RUNNING_STATUSES | _V2_SUCCESS_STATUSES | _V2_FAILED_STATUSES


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
    observed_engine_version: int | None = None

    try:
        while True:
            if needs_status:
                attempt_started = runtime.dependencies.monotonic_fn()
                try:
                    snapshot = request_json(runtime, task_path)
                except (CoreApiError, CoreTransportError) as error:
                    if not _is_retryable_unavailable(error):
                        raise
                    now = runtime.dependencies.monotonic_fn()
                    if unreachable_since is None:
                        unreachable_since = attempt_started
                    if now - unreachable_since > _UNREACHABLE_TIMEOUT_SECONDS:
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
                engine_version = _engine_version(snapshot)
                if (
                    observed_engine_version is not None
                    and observed_engine_version != engine_version
                ):
                    raise CoreResponseContractError(
                        "同一任务的 engineVersion 在观察期间发生变化"
                    )
                observed_engine_version = engine_version
                state = _run_state(snapshot, engine_version)
                if not snapshot_emitted:
                    yield {"type": "snapshot", "data": snapshot}
                    snapshot_emitted = True

                terminal = _terminal_result(
                    task_id,
                    snapshot,
                    engine_version,
                    state,
                )
                if terminal is not None:
                    frame, exit_code = terminal
                    yield frame
                    return exit_code

                if backoff_after_status:
                    backoff_index = _sleep_with_backoff(runtime, backoff_index)
                    backoff_after_status = False

            received_event = False
            sse_attempt_started = runtime.dependencies.monotonic_fn()
            try:
                for raw_event in api.iter_sse(task_id, last_event_id):
                    frame, event_id = _event_frame(raw_event)
                    if event_id is not None:
                        last_event_id = event_id
                    received_event = True
                    yield frame
            except SseConnectionError:
                pass
            except CoreApiError as error:
                if not _is_retryable_unavailable(error):
                    raise
                unavailable_started = (
                    runtime.dependencies.monotonic_fn()
                    if received_event
                    else sse_attempt_started
                )
                if unreachable_since is None:
                    unreachable_since = unavailable_started
                if (
                    runtime.dependencies.monotonic_fn() - unreachable_since
                    > _UNREACHABLE_TIMEOUT_SECONDS
                ):
                    yield _unreachable_frame(
                        task_id,
                        last_event_id,
                        last_snapshot,
                    )
                    return 5

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


def _is_retryable_unavailable(
    error: CoreApiError | CoreTransportError,
) -> bool:
    return isinstance(error, CoreTransportError) or error.status_code >= 500


def _engine_version(snapshot: JsonObject) -> int:
    # 只有字段完全缺失的历史响应兼容为 V1；显式 null 或错误类型不能
    # 根据 outcome/status 的形状反猜引擎，否则同一 Run 会有两套生命周期权威。
    if "engineVersion" not in snapshot:
        return 1
    value = snapshot["engineVersion"]
    if type(value) is not int or value not in {1, 2}:
        raise CoreResponseContractError("任务状态响应缺少有效的 engineVersion")
    return value


def _run_state(snapshot: JsonObject, engine_version: int) -> str:
    if engine_version == 1:
        return _outcome_state(snapshot)
    return _workflow_status(snapshot)


def _outcome_state(snapshot: JsonObject) -> str:
    outcome = snapshot.get("outcome")
    state = outcome.get("state") if isinstance(outcome, dict) else None
    if not isinstance(state, str) or state not in _V1_OUTCOME_STATES:
        raise CoreResponseContractError("任务状态响应缺少有效的 outcome.state")
    return state


def _workflow_status(snapshot: JsonObject) -> str:
    status = snapshot.get("status")
    if not isinstance(status, str) or status not in _V2_RUN_STATUSES:
        raise CoreResponseContractError("V2 任务状态响应缺少有效的 status")

    active_steps = snapshot.get("activeSteps")
    artifact = snapshot.get("artifact")
    error = snapshot.get("error")
    if not isinstance(active_steps, list):
        raise CoreResponseContractError("V2 任务状态响应缺少有效的 activeSteps")
    if artifact is not None and not isinstance(artifact, dict):
        raise CoreResponseContractError("V2 任务状态响应包含无效的 artifact")
    if error is not None and not isinstance(error, dict):
        raise CoreResponseContractError("V2 任务状态响应包含无效的 error")
    return status


def _waiting_artifact_id(snapshot: JsonObject, engine_version: int) -> str:
    if engine_version == 2:
        artifact = snapshot.get("artifact")
        artifact_id = (
            artifact.get("artifactId") if isinstance(artifact, dict) else None
        )
        if not isinstance(artifact_id, str) or not artifact_id:
            raise CoreResponseContractError(
                "V2 waiting_user 任务缺少权威 Artifact ID"
            )
        return artifact_id

    outcome = snapshot.get("outcome")
    result = outcome.get("result") if isinstance(outcome, dict) else None
    artifact_id = result.get("id") if isinstance(result, dict) else None
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CoreResponseContractError("waiting_user 任务缺少权威 Artifact ID")
    return artifact_id


def _terminal_result(
    task_id: str,
    snapshot: JsonObject,
    engine_version: int,
    state: str,
) -> tuple[JsonObject, int] | None:
    if state == "waiting_user":
        return (
            {
                "type": "waiting_user",
                "taskId": task_id,
                "artifactId": _waiting_artifact_id(snapshot, engine_version),
                "data": snapshot,
            },
            0,
        )
    if (engine_version == 1 and state == "succeeded") or (
        engine_version == 2 and state == "completed"
    ):
        return {"type": "terminal", "data": snapshot}, 0
    if (engine_version == 1 and state in _V1_FAILED_STATES) or (
        engine_version == 2 and state in _V2_FAILED_STATUSES
    ):
        return {"type": "terminal", "data": snapshot}, 5
    return None


def _event_frame(event: object) -> tuple[JsonObject, str | None]:
    if not isinstance(event, dict):
        raise CoreResponseContractError("SSE 事件不是 JSON 对象")
    raw_event_id = event.get("id")
    event_id: str | None
    frame_event_id: str | int | None
    if raw_event_id is None:
        event_id = None
        frame_event_id = None
    elif isinstance(raw_event_id, str):
        event_id = raw_event_id or None
        frame_event_id = raw_event_id
    elif type(raw_event_id) is int and raw_event_id >= 0:
        event_id = str(raw_event_id)
        frame_event_id = raw_event_id
    else:
        raise CoreResponseContractError("SSE 事件包含无效游标")
    raw_event_name = event.get("event", "message")
    event_name = raw_event_name if isinstance(raw_event_name, str) else "message"
    frame = {
        "type": "event",
        "id": frame_event_id,
        "event": event_name,
        "data": event.get("data"),
    }
    return frame, event_id


def _unreachable_frame(
    task_id: str,
    last_event_id: str | None,
    last_snapshot: JsonObject | None,
) -> JsonObject:
    state = (
        _run_state(last_snapshot, _engine_version(last_snapshot))
        if last_snapshot is not None
        else None
    )
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

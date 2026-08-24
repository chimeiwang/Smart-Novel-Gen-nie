"""逐镜 Seedance 任务、候选 Take 与选片确认 CLI 命令。"""

from __future__ import annotations

from collections.abc import Generator
from typing import cast

from ....api import CoreApiError, CoreResponseContractError, CoreTransportError
from ....io import write_bytes
from ....json_types import JsonObject
from ....registry import CommandSpec, FileOutputSpec
from ....runtime import CliInputError, CliRuntime
from .support import (
    encode_id,
    enum_value,
    request_json,
    require_client_request_id,
    require_fields,
    require_int,
    require_string,
)

_NO_FILE = FileOutputSpec(kind="none")
_DATA_JSON = FileOutputSpec(kind="data_json")
_RESOLUTIONS = frozenset({"480p", "720p", "1080p"})
_ACTIVE_STATUSES = frozenset({"pending", "submitting", "queued", "running", "archiving"})
_SUCCESS_STATUSES = frozenset({"succeeded"})
_FAILED_STATUSES = frozenset(
    {"submission_unknown", "failed", "expired", "cancelled"}
)
_ALL_STATUSES = _ACTIVE_STATUSES | _SUCCESS_STATUSES | _FAILED_STATUSES
_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 5.0, 10.0)
_UNREACHABLE_TIMEOUT_SECONDS = 300.0


def list_renders(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"adaptationId"}, allow_output_file=True)
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/renders",
    )


def start_render(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "shotId",
            "clientRequestId",
            "expectedPromptRevision",
            "durationSeconds",
        },
        optional={"resolution", "generateAudio", "watermark"},
    )
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    shot_id = encode_id(require_string(payload, "shotId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/render-tasks",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedPromptRevision": require_int(
                payload,
                "expectedPromptRevision",
                minimum=1,
            ),
            "durationSeconds": require_int(
                payload,
                "durationSeconds",
                minimum=2,
                maximum=12,
            ),
            "resolution": enum_value(
                payload,
                "resolution",
                _RESOLUTIONS,
                default="720p",
            ),
            "generateAudio": _optional_bool(payload, "generateAudio", default=True),
            "watermark": _optional_bool(payload, "watermark", default=False),
        },
    )


def get_render(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"taskId"}, allow_output_file=True)
    return _get_render(runtime, require_string(payload, "taskId"))


def retry_render(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"taskId", "clientRequestId"})
    task_id = encode_id(require_string(payload, "taskId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/render-tasks/{task_id}/retry",
        json={"clientRequestId": require_client_request_id(payload)},
    )


def confirm_take(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "shotId",
            "takeId",
            "clientRequestId",
            "expectedTakeRevision",
        },
    )
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    shot_id = encode_id(require_string(payload, "shotId"))
    take_id = encode_id(require_string(payload, "takeId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/takes/{take_id}/confirm",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedTakeRevision": require_int(
                payload,
                "expectedTakeRevision",
                minimum=1,
            ),
        },
    )


def download_take(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"takeId", "outputFile"},
        allow_output_file=True,
    )
    take_id = require_string(payload, "takeId")
    output_file = require_string(payload, "outputFile")
    response = runtime.require_api().request_bytes(
        "GET",
        f"/api/v1/video/takes/{encode_id(take_id)}/content",
    )
    descriptor = write_bytes(output_file, response.content, response.media_type)
    return {
        "takeId": take_id,
        "resultFile": cast(JsonObject, dict(descriptor)),
    }


def watch_render(
    runtime: CliRuntime,
    payload: JsonObject,
) -> Generator[JsonObject, None, int]:
    """轮询单条耐久任务；停止 watcher 不取消供应商任务。"""

    require_fields(payload, required={"taskId"})
    task_id = require_string(payload, "taskId")
    unreachable_since: float | None = None
    backoff_index = 0
    last_signature: tuple[object, ...] | None = None
    first_snapshot = True
    try:
        while True:
            attempt_started = runtime.dependencies.monotonic_fn()
            try:
                task = _get_render(runtime, task_id)
            except (CoreApiError, CoreTransportError) as error:
                if not _retryable_unavailable(error):
                    raise
                now = runtime.dependencies.monotonic_fn()
                if unreachable_since is None:
                    unreachable_since = attempt_started
                if now - unreachable_since > _UNREACHABLE_TIMEOUT_SECONDS:
                    yield {
                        "type": "error",
                        "error": {
                            "code": "WATCH_CORE_UNREACHABLE",
                            "message": (
                                "Core API 连续不可达超过 300 秒；"
                                "仅停止观察，服务端任务未取消"
                            ),
                            "taskId": task_id,
                        },
                    }
                    return 5
                backoff_index = _sleep_with_backoff(runtime, backoff_index)
                continue
            unreachable_since = None
            status = task.get("status")
            if not isinstance(status, str) or status not in _ALL_STATUSES:
                raise CoreResponseContractError("逐镜视频任务缺少有效 status")
            signature = (
                status,
                task.get("pollCount"),
                task.get("updatedAt"),
                task.get("lastErrorCode"),
                task.get("lastErrorMessage"),
            )
            if first_snapshot:
                yield {"type": "snapshot", "data": task}
                first_snapshot = False
            elif signature != last_signature:
                yield {"type": "progress", "taskId": task_id, "data": task}
            last_signature = signature
            if status in _SUCCESS_STATUSES:
                yield {"type": "terminal", "data": task}
                return 0
            if status in _FAILED_STATUSES:
                yield {"type": "terminal", "data": task}
                return 5
            backoff_index = _sleep_with_backoff(runtime, backoff_index)
    except KeyboardInterrupt:
        yield {
            "type": "error",
            "error": {
                "code": "WATCH_INTERRUPTED",
                "message": "仅停止观察，服务端任务未取消",
                "taskId": task_id,
            },
        }
        return 130


def _get_render(runtime: CliRuntime, task_id: str) -> JsonObject:
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/render-tasks/{encode_id(task_id)}",
    )


def _optional_bool(payload: JsonObject, name: str, *, default: bool) -> bool:
    value = payload.get(name, default)
    if type(value) is not bool:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是布尔值")
    return value


def _retryable_unavailable(error: CoreApiError | CoreTransportError) -> bool:
    return isinstance(error, CoreTransportError) or (
        not isinstance(error, CoreResponseContractError) and error.status_code >= 500
    )


def _sleep_with_backoff(runtime: CliRuntime, index: int) -> int:
    delay = _BACKOFF_SECONDS[min(index, len(_BACKOFF_SECONDS) - 1)]
    runtime.dependencies.sleep_fn(delay)
    return min(index + 1, len(_BACKOFF_SECONDS) - 1)


VIDEO_RENDER_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.video.render.list",
        handler=list_renders,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.render.start",
        handler=start_render,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.render.get",
        handler=get_render,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.render.retry",
        handler=retry_render,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.render.watch",
        handler=watch_render,
        inputMode="json",
        outputMode="jsonl",
        fileOutput=_NO_FILE,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.take.confirm",
        handler=confirm_take,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.take.download",
        handler=download_take,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

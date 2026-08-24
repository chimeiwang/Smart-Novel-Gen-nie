"""关键帧、粗剪、声音字幕与整集导出 CLI 命令。"""

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
    json_object_source,
    optional_string,
    request_json,
    require_client_request_id,
    require_fields,
    require_int,
    require_string,
)

_NO_FILE = FileOutputSpec(kind="none")
_DATA_JSON = FileOutputSpec(kind="data_json")
_KEYFRAME_ROLES = frozenset({"initial_state", "transition_anchor", "end_state"})
_RESOLUTIONS = frozenset({"720p", "1080p"})
_EXPORT_ACTIVE = frozenset({"pending", "rendering"})
_EXPORT_TERMINAL = frozenset({"succeeded", "failed"})
_EXPORT_STATUSES = _EXPORT_ACTIVE | _EXPORT_TERMINAL
_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 5.0, 10.0)
_UNREACHABLE_TIMEOUT_SECONDS = 300.0


def show_post_production(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"adaptationId"}, allow_output_file=True)
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/post-production",
    )


def set_keyframe(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "shotId",
            "role",
            "assetId",
            "clientRequestId",
            "expectedRevision",
        },
        optional={"sourceTakeId", "sourceTimeMs"},
    )
    source_take_id = optional_string(payload, "sourceTakeId")
    source_time_ms = _optional_int(payload, "sourceTimeMs", minimum=0)
    if (source_take_id is None) != (source_time_ms is None):
        raise CliInputError(
            "INVALID_FIELD",
            "sourceTakeId 与 sourceTimeMs 必须同时提供",
        )
    return _save_keyframe(
        runtime,
        payload,
        asset_id=require_string(payload, "assetId"),
        source_take_id=source_take_id,
        source_time_ms=source_time_ms,
    )


def clear_keyframe(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "shotId",
            "role",
            "clientRequestId",
            "expectedRevision",
        },
    )
    return _save_keyframe(
        runtime,
        payload,
        asset_id=None,
        source_take_id=None,
        source_time_ms=None,
    )


def _save_keyframe(
    runtime: CliRuntime,
    payload: JsonObject,
    *,
    asset_id: str | None,
    source_take_id: str | None,
    source_time_ms: int | None,
) -> JsonObject:
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    shot_id = encode_id(require_string(payload, "shotId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/keyframe-versions",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
            "role": enum_value(payload, "role", _KEYFRAME_ROLES),
            "assetId": asset_id,
            "sourceTakeId": source_take_id,
            "sourceTimeMs": source_time_ms,
        },
    )


def extract_keyframe(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"takeId", "clientRequestId", "timestampMs", "name"},
    )
    take_id = encode_id(require_string(payload, "takeId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/takes/{take_id}/frames",
        json={
            "clientRequestId": require_client_request_id(payload),
            "timestampMs": require_int(payload, "timestampMs", minimum=0),
            "name": require_string(payload, "name", max_length=200),
        },
    )


def save_edit(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "episodeNo",
            "clientRequestId",
            "expectedRevision",
        },
        optional={"basedOnVersionId", "edit", "editFile"},
    )
    edit = json_object_source(payload, inline_field="edit", file_field="editFile")
    clips = edit.get("clips")
    if not isinstance(clips, list):
        raise CliInputError("INVALID_FIELD", "edit.clips 必须是数组")
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    episode_no = require_int(payload, "episodeNo", minimum=1)
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/edit-versions",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
            "basedOnVersionId": optional_string(payload, "basedOnVersionId"),
            "clips": clips,
        },
    )


def get_edit(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"versionId"}, allow_output_file=True)
    version_id = encode_id(require_string(payload, "versionId"))
    return request_json(runtime, "GET", f"/api/v1/video/edit-versions/{version_id}")


def save_mix(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "episodeNo",
            "clientRequestId",
            "expectedRevision",
            "editVersionId",
        },
        optional={"basedOnVersionId", "mix", "mixFile"},
    )
    mix = json_object_source(payload, inline_field="mix", file_field="mixFile")
    audio_clips = mix.get("audioClips", [])
    subtitle_cues = mix.get("subtitleCues", [])
    if not isinstance(audio_clips, list) or not isinstance(subtitle_cues, list):
        raise CliInputError(
            "INVALID_FIELD",
            "mix.audioClips 与 mix.subtitleCues 必须是数组",
        )
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    episode_no = require_int(payload, "episodeNo", minimum=1)
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/mix-versions",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
            "basedOnVersionId": optional_string(payload, "basedOnVersionId"),
            "editVersionId": require_string(payload, "editVersionId"),
            "audioClips": audio_clips,
            "subtitleCues": subtitle_cues,
        },
    )


def get_mix(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"versionId"}, allow_output_file=True)
    version_id = encode_id(require_string(payload, "versionId"))
    return request_json(runtime, "GET", f"/api/v1/video/mix-versions/{version_id}")


def start_export(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "episodeNo",
            "editVersionId",
            "mixVersionId",
            "clientRequestId",
        },
        optional={"resolution", "framesPerSecond", "burnSubtitles"},
    )
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    episode_no = require_int(payload, "episodeNo", minimum=1)
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/export-tasks",
        json={
            "clientRequestId": require_client_request_id(payload),
            "editVersionId": require_string(payload, "editVersionId"),
            "mixVersionId": require_string(payload, "mixVersionId"),
            "resolution": enum_value(
                payload,
                "resolution",
                _RESOLUTIONS,
                default="720p",
            ),
            "framesPerSecond": _optional_enum_int(
                payload,
                "framesPerSecond",
                {24, 25, 30},
                default=24,
            ),
            "burnSubtitles": _optional_bool(payload, "burnSubtitles", default=True),
        },
    )


def get_export(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"taskId"}, allow_output_file=True)
    return _get_export(runtime, require_string(payload, "taskId"))


def retry_export(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"taskId", "clientRequestId"})
    task_id = encode_id(require_string(payload, "taskId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/export-tasks/{task_id}/retry",
        json={"clientRequestId": require_client_request_id(payload)},
    )


def download_export(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"exportId", "outputFile"}, allow_output_file=True)
    export_id = require_string(payload, "exportId")
    output_file = require_string(payload, "outputFile")
    response = runtime.require_api().request_bytes(
        "GET",
        f"/api/v1/video/exports/{encode_id(export_id)}/content",
    )
    descriptor = write_bytes(output_file, response.content, response.media_type)
    return {"exportId": export_id, "resultFile": cast(JsonObject, dict(descriptor))}


def watch_export(
    runtime: CliRuntime,
    payload: JsonObject,
) -> Generator[JsonObject, None, int]:
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
                task = _get_export(runtime, task_id)
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
            if not isinstance(status, str) or status not in _EXPORT_STATUSES:
                raise CoreResponseContractError("整集导出任务缺少有效 status")
            signature = (
                status,
                task.get("attemptCount"),
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
            if status in _EXPORT_TERMINAL:
                yield {"type": "terminal", "data": task}
                return 0 if status == "succeeded" else 5
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


def _get_export(runtime: CliRuntime, task_id: str) -> JsonObject:
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/export-tasks/{encode_id(task_id)}",
    )


def _optional_int(
    payload: JsonObject,
    name: str,
    *,
    minimum: int | None = None,
) -> int | None:
    if name not in payload or payload.get(name) is None:
        return None
    return require_int(payload, name, minimum=minimum)


def _optional_bool(payload: JsonObject, name: str, *, default: bool) -> bool:
    value = payload.get(name, default)
    if type(value) is not bool:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是布尔值")
    return value


def _optional_enum_int(
    payload: JsonObject,
    name: str,
    allowed: set[int],
    *,
    default: int,
) -> int:
    value = payload.get(name, default)
    if type(value) is not int or value not in allowed:
        options = ", ".join(str(item) for item in sorted(allowed))
        raise CliInputError("INVALID_FIELD", f"{name} 必须是：{options}")
    return value


def _retryable_unavailable(error: CoreApiError | CoreTransportError) -> bool:
    return isinstance(error, CoreTransportError) or (
        not isinstance(error, CoreResponseContractError) and error.status_code >= 500
    )


def _sleep_with_backoff(runtime: CliRuntime, index: int) -> int:
    delay = _BACKOFF_SECONDS[min(index, len(_BACKOFF_SECONDS) - 1)]
    runtime.dependencies.sleep_fn(delay)
    return min(index + 1, len(_BACKOFF_SECONDS) - 1)


VIDEO_POST_PRODUCTION_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.video.post.show",
        handler=show_post_production,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.keyframe.set",
        handler=set_keyframe,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.keyframe.clear",
        handler=clear_keyframe,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.keyframe.extract",
        handler=extract_keyframe,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.edit.save",
        handler=save_edit,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.edit.get",
        handler=get_edit,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.mix.save",
        handler=save_mix,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.mix.get",
        handler=get_mix,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.export.start",
        handler=start_export,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.export.get",
        handler=get_export,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.export.retry",
        handler=retry_export,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.export.watch",
        handler=watch_export,
        inputMode="json",
        outputMode="jsonl",
        fileOutput=_NO_FILE,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.export.download",
        handler=download_export,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

"""章节改编、镜头方案、分集与逐镜提示词 CLI 命令。"""

from __future__ import annotations

from collections.abc import Generator

from ....api import (
    CoreApiError,
    CoreResponseContractError,
    CoreTransportError,
)
from ....json_types import JsonObject
from ....registry import CommandSpec, FileOutputSpec
from ....runtime import CliInputError, CliRuntime
from .support import (
    as_json_object,
    encode_id,
    enum_value,
    json_object_source,
    optional_string,
    request_json,
    require_client_request_id,
    require_fields,
    require_int,
    require_string,
    string_list,
    text_source,
)

_NO_FILE = FileOutputSpec(kind="none")
_DATA_JSON = FileOutputSpec(kind="data_json")
_PACING_PRESETS = frozenset({"short_drama", "cinematic", "dialogue_driven"})
_EPISODE_SECONDS = frozenset({60, 90, 120})
_ACTIVE_TASK_STATUSES = frozenset({"pending", "submitted", "processing"})
_SUCCESS_TASK_STATUSES = frozenset({"completed"})
_FAILED_TASK_STATUSES = frozenset({"failed", "cancelled"})
_TASK_STATUSES = _ACTIVE_TASK_STATUSES | _SUCCESS_TASK_STATUSES | _FAILED_TASK_STATUSES
_BACKOFF_SECONDS = (0.5, 1.0, 2.0, 5.0, 10.0)
_UNREACHABLE_TIMEOUT_SECONDS = 300.0


def list_adaptations(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"projectId"}, allow_output_file=True)
    project_id = encode_id(require_string(payload, "projectId"))
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/projects/{project_id}/chapter-adaptations",
    )


def get_adaptation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"adaptationId"}, allow_output_file=True)
    return _get_adaptation(runtime, require_string(payload, "adaptationId"))


def create_adaptation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "projectId",
            "chapterId",
            "expectedChapterUpdatedAt",
            "clientRequestId",
        },
    )
    project_id = encode_id(require_string(payload, "projectId"))
    body: JsonObject = {
        "clientRequestId": require_client_request_id(payload),
        "chapterId": require_string(payload, "chapterId"),
        "expectedChapterUpdatedAt": require_string(
            payload,
            "expectedChapterUpdatedAt",
        ),
    }
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/projects/{project_id}/chapter-adaptations",
        json=body,
    )


def start_plan(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"adaptationId", "clientRequestId"},
        optional={
            "pacingPreset",
            "targetEpisodeSeconds",
            "baseShotPlanVersionId",
            "revisionBrief",
        },
    )
    base_version = optional_string(payload, "baseShotPlanVersionId")
    revision_brief = optional_string(payload, "revisionBrief", max_length=1_200)
    if revision_brief is not None and base_version is None:
        raise CliInputError(
            "REVISION_BASE_REQUIRED",
            "没有正式镜头方案基线时不能提交修订重点",
        )
    target_seconds = payload.get("targetEpisodeSeconds", 90)
    if type(target_seconds) is not int or target_seconds not in _EPISODE_SECONDS:
        raise CliInputError(
            "INVALID_TARGET_EPISODE_SECONDS",
            "targetEpisodeSeconds 必须是 60、90 或 120",
        )
    body: JsonObject = {
        "clientRequestId": require_client_request_id(payload),
        "pacingPreset": enum_value(
            payload,
            "pacingPreset",
            _PACING_PRESETS,
            default="short_drama",
        ),
        "targetEpisodeSeconds": target_seconds,
        "baseShotPlanVersionId": base_version,
        "revisionBrief": revision_brief,
    }
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan-runs",
        json=body,
    )


def confirm_plan(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "clientRequestId",
            "expectedArtifactRevision",
            "expectedAdaptationRevision",
        },
        optional={"plan", "planFile"},
    )
    adaptation_id = require_string(payload, "adaptationId")
    artifact_revision = require_int(payload, "expectedArtifactRevision", minimum=1)
    adaptation_revision = require_int(
        payload,
        "expectedAdaptationRevision",
        minimum=1,
    )
    plan = json_object_source(
        payload,
        inline_field="plan",
        file_field="planFile",
    )
    _preflight_candidate(
        _get_adaptation(runtime, adaptation_id),
        artifact_revision=artifact_revision,
        adaptation_revision=adaptation_revision,
    )
    body: JsonObject = {
        "clientRequestId": require_client_request_id(payload),
        "expectedArtifactRevision": artifact_revision,
        "expectedAdaptationRevision": adaptation_revision,
        "plan": plan,
    }
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{encode_id(adaptation_id)}/shot-plan/confirm",
        json=body,
    )


def discard_plan_candidate(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "clientRequestId",
            "expectedArtifactRevision",
            "expectedAdaptationRevision",
        },
    )
    adaptation_id = require_string(payload, "adaptationId")
    artifact_revision = require_int(payload, "expectedArtifactRevision", minimum=1)
    adaptation_revision = require_int(
        payload,
        "expectedAdaptationRevision",
        minimum=1,
    )
    _preflight_candidate(
        _get_adaptation(runtime, adaptation_id),
        artifact_revision=artifact_revision,
        adaptation_revision=adaptation_revision,
    )
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{encode_id(adaptation_id)}/candidate/discard",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedArtifactRevision": artifact_revision,
            "expectedAdaptationRevision": adaptation_revision,
        },
    )


def save_episode_plan(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "clientRequestId",
            "expectedAdaptationRevision",
            "shotPlanVersionId",
            "breakAfterShotIds",
        },
    )
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    return request_json(
        runtime,
        "PUT",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/episode-plan",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedAdaptationRevision": require_int(
                payload,
                "expectedAdaptationRevision",
                minimum=1,
            ),
            "shotPlanVersionId": require_string(payload, "shotPlanVersionId"),
            "breakAfterShotIds": string_list(
                payload,
                "breakAfterShotIds",
                max_items=119,
            ),
        },
    )


def start_prompts(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "adaptationId",
            "clientRequestId",
            "expectedAdaptationRevision",
            "shotPlanVersionId",
        },
        optional={"shotIds"},
    )
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/prompt-runs",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedAdaptationRevision": require_int(
                payload,
                "expectedAdaptationRevision",
                minimum=1,
            ),
            "shotPlanVersionId": require_string(payload, "shotPlanVersionId"),
            "shotIds": string_list(payload, "shotIds", max_items=120),
        },
    )


def save_prompt(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"adaptationId", "shotId", "expectedPromptRevision"},
        optional={"candidateTaskId", "currentPrompt", "currentPromptFile"},
    )
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    shot_id = encode_id(require_string(payload, "shotId"))
    body: JsonObject = {
        "expectedPromptRevision": require_int(
            payload,
            "expectedPromptRevision",
            minimum=1,
        ),
        "candidateTaskId": optional_string(payload, "candidateTaskId"),
        "currentPrompt": text_source(
            payload,
            inline_field="currentPrompt",
            file_field="currentPromptFile",
            max_length=2_000,
        ),
    }
    return request_json(
        runtime,
        "PUT",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/prompt",
        json=body,
    )


def watch_adaptation(
    runtime: CliRuntime,
    payload: JsonObject,
) -> Generator[JsonObject, None, int]:
    """只轮询公共改编聚合；退出观察不会改变服务端任务。"""

    require_fields(payload, required={"adaptationId", "taskId"})
    adaptation_id = require_string(payload, "adaptationId")
    task_id = require_string(payload, "taskId")
    unreachable_since: float | None = None
    backoff_index = 0
    last_signature: tuple[object, ...] | None = None
    first_snapshot = True

    try:
        while True:
            attempt_started = runtime.dependencies.monotonic_fn()
            try:
                snapshot = _get_adaptation(runtime, adaptation_id)
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
                            "adaptationId": adaptation_id,
                            "taskId": task_id,
                        },
                    }
                    return 5
                backoff_index = _sleep_with_backoff(runtime, backoff_index)
                continue

            unreachable_since = None
            task = _latest_task(snapshot)
            current_task_id = task.get("id")
            if current_task_id != task_id:
                yield {
                    "type": "error",
                    "error": {
                        "code": "VIDEO_TASK_SUPERSEDED",
                        "message": "改编当前最新任务与目标 taskId 不一致；仅停止观察",
                        "adaptationId": adaptation_id,
                        "taskId": task_id,
                        "latestTaskId": current_task_id,
                    },
                }
                return 5

            status = task.get("status")
            if not isinstance(status, str) or status not in _TASK_STATUSES:
                raise CoreResponseContractError("章节影视化任务缺少有效 status")
            signature = (
                status,
                task.get("checkpointStage"),
                task.get("updatedAt"),
                task.get("lastErrorCode"),
                task.get("lastErrorMessage"),
            )
            if first_snapshot:
                yield {"type": "snapshot", "data": snapshot}
                first_snapshot = False
            elif signature != last_signature:
                yield {
                    "type": "progress",
                    "adaptationId": adaptation_id,
                    "taskId": task_id,
                    "data": task,
                }
            last_signature = signature

            if status in _SUCCESS_TASK_STATUSES:
                yield {"type": "terminal", "data": snapshot}
                return 0
            if status in _FAILED_TASK_STATUSES:
                yield {"type": "terminal", "data": snapshot}
                return 5
            backoff_index = _sleep_with_backoff(runtime, backoff_index)
    except KeyboardInterrupt:
        yield {
            "type": "error",
            "error": {
                "code": "WATCH_INTERRUPTED",
                "message": "仅停止观察，服务端任务未取消",
                "adaptationId": adaptation_id,
                "taskId": task_id,
            },
        }
        return 130


def _get_adaptation(runtime: CliRuntime, adaptation_id: str) -> JsonObject:
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/chapter-adaptations/{encode_id(adaptation_id)}",
    )


def _preflight_candidate(
    snapshot: JsonObject,
    *,
    artifact_revision: int,
    adaptation_revision: int,
) -> None:
    """在提交前拒绝本地已知的过期候选，Core 仍执行最终事务 CAS。"""

    current_revision = snapshot.get("headRevision")
    review = snapshot.get("reviewArtifact")
    candidate = snapshot.get("candidatePlan")
    if current_revision != adaptation_revision:
        raise CoreApiError(
            409,
            code="VIDEO_ADAPTATION_REVISION_CONFLICT",
            message="改编 revision 已变化，请重新读取并确认候选",
            details={"currentRevision": current_revision},
        )
    if not isinstance(review, dict) or not isinstance(candidate, dict):
        raise CoreApiError(
            409,
            code="VIDEO_ADAPTATION_CANDIDATE_MISSING",
            message="当前没有可确认或丢弃的完整镜头候选",
        )
    if review.get("revision") != artifact_revision:
        raise CoreApiError(
            409,
            code="VIDEO_ARTIFACT_REVISION_CONFLICT",
            message="候选 revision 已变化，请重新读取并确认完整候选",
            details={"currentRevision": review.get("revision")},
        )
    if review.get("status") != "awaiting_user":
        raise CoreApiError(
            409,
            code="VIDEO_ADAPTATION_CANDIDATE_NOT_REVIEWABLE",
            message="当前候选不处于等待用户确认状态",
            details={"status": review.get("status")},
        )


def _latest_task(snapshot: JsonObject) -> JsonObject:
    task = snapshot.get("latestTask")
    return as_json_object(task, "章节影视化响应缺少 latestTask")


def _retryable_unavailable(error: CoreApiError | CoreTransportError) -> bool:
    return isinstance(error, CoreTransportError) or (
        not isinstance(error, CoreResponseContractError) and error.status_code >= 500
    )


def _sleep_with_backoff(runtime: CliRuntime, index: int) -> int:
    delay = _BACKOFF_SECONDS[min(index, len(_BACKOFF_SECONDS) - 1)]
    runtime.dependencies.sleep_fn(delay)
    return min(index + 1, len(_BACKOFF_SECONDS) - 1)


VIDEO_ADAPTATION_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.video.adaptation.list",
        handler=list_adaptations,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.adaptation.get",
        handler=get_adaptation,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.adaptation.create",
        handler=create_adaptation,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.adaptation.watch",
        handler=watch_adaptation,
        inputMode="json",
        outputMode="jsonl",
        fileOutput=_NO_FILE,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.plan.start",
        handler=start_plan,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.plan.confirm",
        handler=confirm_plan,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.plan.discard",
        handler=discard_plan_candidate,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.episode.save",
        handler=save_episode_plan,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.prompt.start",
        handler=start_prompts,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.prompt.save",
        handler=save_prompt,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

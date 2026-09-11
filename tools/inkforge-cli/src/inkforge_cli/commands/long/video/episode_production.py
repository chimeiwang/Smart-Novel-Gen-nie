"""独立分集 P2/P3 制作、后期与交付 CLI 命令。"""

from __future__ import annotations

import json
import re
from typing import cast
from urllib.parse import quote

from ....io import read_utf8_text_exact, write_bytes
from ....json_types import JsonObject
from ....registry import CommandHandler, CommandSpec, FileOutputSpec
from ....runtime import CliInputError, CliRuntime
from .support import (
    encode_id,
    enum_value,
    json_object_source,
    request_json,
    require_client_request_id,
    require_fields,
    require_int,
    require_string,
    string_list,
)

_NO_FILE = FileOutputSpec(kind="none")
_DATA_JSON = FileOutputSpec(kind="data_json")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STORYBOARD_OPERATIONS = frozenset({"episode_storyboard_generate", "episode_storyboard_revise"})
_IMPACT_STATUSES = frozenset({"pending", "resolved"})
_IMPACT_ACTIONS = frozenset({"keep_existing", "revise_target", "not_applicable", "defer"})


def get_capabilities(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, allow_output_file=True)
    return request_json(runtime, "GET", "/api/v1/video/production-capabilities")


def get_storyboard_draft(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId"}, allow_output_file=True)
    return request_json(runtime, "GET", f"{_episode_path(payload)}/storyboard/draft")


def save_storyboard_draft(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "clientRequestId",
            "expectedRevision",
            "scriptVersionId",
            "baseStoryboardVersionId",
        },
        optional={"document", "documentFile"},
    )
    document = json_object_source(payload, inline_field="document", file_field="documentFile")
    return request_json(
        runtime,
        "PUT",
        f"{_episode_path(payload)}/storyboard/draft",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
            "scriptVersionId": require_string(payload, "scriptVersionId", max_length=128),
            "baseStoryboardVersionId": _nullable_identifier(
                payload, "baseStoryboardVersionId", required=True
            ),
            "document": document,
        },
    )


def start_storyboard_run(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "clientRequestId",
            "expectedDraftRevision",
            "scriptVersionId",
            "operation",
            "instruction",
        },
        optional={"selectedShotIds"},
    )
    operation = enum_value(payload, "operation", _STORYBOARD_OPERATIONS)
    selected = string_list(payload, "selectedShotIds", max_items=300)
    if operation == "episode_storyboard_generate" and selected:
        raise CliInputError("INVALID_FIELD", "分镜起草不能携带局部修订范围")
    if operation == "episode_storyboard_revise" and not selected:
        raise CliInputError("INVALID_FIELD", "分镜修订必须选择至少一个稳定镜头")
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/storyboard/runs",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedDraftRevision": require_int(payload, "expectedDraftRevision", minimum=1),
            "scriptVersionId": require_string(payload, "scriptVersionId", max_length=128),
            "operation": operation,
            "selectedShotIds": selected,
            "instruction": require_string(payload, "instruction", max_length=8_000),
        },
    )


def list_storyboard_runs(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId"},
        optional={"limit", "beforeRunId"},
        allow_output_file=True,
    )
    query = _page_query(payload, maximum=50, cursor="beforeRunId")
    return request_json(runtime, "GET", f"{_episode_path(payload)}/storyboard/runs{query}")


def get_storyboard_run(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "runId"}, allow_output_file=True)
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/storyboard/runs/{_id(payload, 'runId')}",
    )


def get_storyboard_candidate(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "artifactId"}, allow_output_file=True)
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/storyboard/candidates/{_id(payload, 'artifactId')}",
    )


def adopt_storyboard_candidate(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "artifactId",
            "clientRequestId",
            "expectedArtifactRevision",
            "expectedDraftRevision",
        },
    )
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/storyboard/candidates/{_id(payload, 'artifactId')}/adopt",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedArtifactRevision": require_int(payload, "expectedArtifactRevision", minimum=1),
            "expectedDraftRevision": require_int(payload, "expectedDraftRevision", minimum=1),
        },
    )


def prepare_storyboard_confirmation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "clientRequestId",
            "expectedDraftRevision",
            "expectedEpisodeRevision",
        },
    )
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/storyboard/confirmations",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedDraftRevision": require_int(payload, "expectedDraftRevision", minimum=1),
            "expectedEpisodeRevision": require_int(payload, "expectedEpisodeRevision", minimum=1),
        },
    )


def get_storyboard_confirmation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "artifactId"}, allow_output_file=True)
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/storyboard/confirmations/{_id(payload, 'artifactId')}",
    )


def approve_storyboard_confirmation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "artifactId",
            "clientRequestId",
            "expectedArtifactRevision",
            "expectedDraftRevision",
            "expectedEpisodeRevision",
            "confirmationHash",
        },
    )
    confirmation_hash = _sha256(payload, "confirmationHash")
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/storyboard/confirmations/{_id(payload, 'artifactId')}/approve",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedArtifactRevision": require_int(payload, "expectedArtifactRevision", minimum=1),
            "expectedDraftRevision": require_int(payload, "expectedDraftRevision", minimum=1),
            "expectedEpisodeRevision": require_int(payload, "expectedEpisodeRevision", minimum=1),
            "confirmationHash": confirmation_hash,
        },
    )


def list_storyboard_versions(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _list_baseline_root(runtime, payload, "storyboard/versions")


def get_storyboard_version(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "versionId"}, allow_output_file=True)
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/storyboard/versions/{_id(payload, 'versionId')}",
    )


def list_takes(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "targetShotVersionId"},
        optional={"limit", "beforeTakeId"},
        allow_output_file=True,
    )
    parts: list[tuple[str, object]] = [
        ("targetShotVersionId", require_string(payload, "targetShotVersionId", max_length=128)),
        ("limit", _limit(payload, 100)),
    ]
    before = _nullable_identifier(payload, "beforeTakeId")
    if before is not None:
        parts.append(("beforeTakeId", before))
    return request_json(runtime, "GET", f"{_episode_path(payload)}/takes{_query(parts)}")


def download_take(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "takeId", "outputFile"},
        allow_output_file=True,
    )
    take_id = require_string(payload, "takeId")
    response = runtime.require_api().request_bytes(
        "GET", f"{_episode_path(payload)}/takes/{encode_id(take_id)}/content"
    )
    descriptor = write_bytes(
        require_string(payload, "outputFile"), response.content, response.media_type
    )
    return {"takeId": take_id, "resultFile": cast(JsonObject, dict(descriptor))}


def create_adoption(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "clientRequestId",
            "expectedProductionRevision",
            "targetShotVersionId",
            "sourceTakeId",
            "sourceBaselineId",
        },
        optional={"comparison", "comparisonFile"},
    )
    comparison = json_object_source(payload, inline_field="comparison", file_field="comparisonFile")
    expected = {
        "sourceBaselineId",
        "targetShotVersionId",
        "directInputsUnchanged",
        "referenceHashesChecked",
        "summary",
    }
    if set(comparison) != expected:
        raise CliInputError("INVALID_FIELD", "comparison 字段必须精确匹配公共契约")
    source_baseline_id = require_string(payload, "sourceBaselineId", max_length=128)
    target_shot_version_id = require_string(payload, "targetShotVersionId", max_length=128)
    if comparison.get("sourceBaselineId") != source_baseline_id:
        raise CliInputError("INVALID_FIELD", "comparison.sourceBaselineId 与请求不一致")
    if comparison.get("targetShotVersionId") != target_shot_version_id:
        raise CliInputError("INVALID_FIELD", "comparison.targetShotVersionId 与请求不一致")
    hashes = comparison.get("referenceHashesChecked")
    if (
        not isinstance(hashes, list)
        or len(hashes) > 20
        or any(not isinstance(value, str) or _SHA256.fullmatch(value) is None for value in hashes)
    ):
        raise CliInputError("INVALID_FIELD", "referenceHashesChecked 必须是小写 SHA-256 数组")
    if type(comparison.get("directInputsUnchanged")) is not bool:
        raise CliInputError("INVALID_FIELD", "directInputsUnchanged 必须是布尔值")
    _object_string(comparison, "summary", maximum=4_000)
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/take-adoptions",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedProductionRevision": require_int(
                payload, "expectedProductionRevision", minimum=1
            ),
            "targetShotVersionId": target_shot_version_id,
            "sourceTakeId": require_string(payload, "sourceTakeId", max_length=128),
            "sourceBaselineId": source_baseline_id,
            "comparison": comparison,
        },
    )


def get_adoption(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "adoptionId"}, allow_output_file=True)
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/take-adoptions/{_id(payload, 'adoptionId')}",
    )


def create_baseline(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "clientRequestId",
            "expectedEpisodeRevision",
            "expectedProductionRevision",
            "basedOnBaselineId",
            "scriptVersionId",
            "storyboardVersionId",
        },
        optional={"shotAdoptions", "shotAdoptionsFile", "keyframes", "keyframesFile"},
    )
    adoptions = _array_source(
        payload,
        "shotAdoptions",
        "shotAdoptionsFile",
        maximum=300,
        default=[],
    )
    seen: set[str] = set()
    for item in adoptions:
        if not isinstance(item, dict) or set(item) != {"shotVersionId", "adoptionId"}:
            raise CliInputError("INVALID_FIELD", "shotAdoptions 项字段必须精确匹配公共契约")
        shot_version_id = _object_string(item, "shotVersionId", maximum=128)
        _object_string(item, "adoptionId", maximum=128)
        if shot_version_id in seen:
            raise CliInputError("INVALID_FIELD", "shotAdoptions 不能重复镜头版本")
        seen.add(shot_version_id)
    keyframes = _array_source(payload, "keyframes", "keyframesFile", maximum=900, default=[])
    keyframe_keys: set[tuple[str, str]] = set()
    for item in keyframes:
        if not isinstance(item, dict) or set(item) != {
            "shotVersionId",
            "role",
            "assetId",
        }:
            raise CliInputError("INVALID_FIELD", "keyframes 项字段必须精确匹配公共契约")
        shot_version_id = _object_string(item, "shotVersionId", maximum=128)
        role = _object_enum(
            item,
            "role",
            frozenset({"initial_state", "transition_anchor", "end_state"}),
        )
        _object_string(item, "assetId", maximum=128)
        if (shot_version_id, role) in keyframe_keys:
            raise CliInputError("INVALID_FIELD", "keyframes 不能重复镜头版本与角色")
        keyframe_keys.add((shot_version_id, role))
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/production-baselines",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedEpisodeRevision": require_int(payload, "expectedEpisodeRevision", minimum=1),
            "expectedProductionRevision": require_int(
                payload, "expectedProductionRevision", minimum=1
            ),
            "basedOnBaselineId": _nullable_identifier(payload, "basedOnBaselineId", required=True),
            "scriptVersionId": require_string(payload, "scriptVersionId", max_length=128),
            "storyboardVersionId": require_string(payload, "storyboardVersionId", max_length=128),
            "shotAdoptions": adoptions,
            "keyframes": keyframes,
        },
    )


def list_baselines(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _list_baseline_root(runtime, payload, "production-baselines")


def get_baseline(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "baselineId"}, allow_output_file=True)
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/production-baselines/{_id(payload, 'baselineId')}",
    )


def list_impacts(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId"},
        optional={"status", "limit", "beforeReviewId"},
        allow_output_file=True,
    )
    parts: list[tuple[str, object]] = []
    if "status" in payload and payload.get("status") is not None:
        parts.append(("status", enum_value(payload, "status", _IMPACT_STATUSES)))
    parts.append(("limit", _limit(payload, 100)))
    before = _nullable_identifier(payload, "beforeReviewId")
    if before is not None:
        parts.append(("beforeReviewId", before))
    return request_json(runtime, "GET", f"{_episode_path(payload)}/impact-reviews{_query(parts)}")


def get_impact(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "reviewId"}, allow_output_file=True)
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/impact-reviews/{_id(payload, 'reviewId')}",
    )


def decide_impact(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "reviewId", "clientRequestId", "expectedRevision"},
        optional={"decisions", "decisionsFile"},
    )
    decisions = _array_source(payload, "decisions", "decisionsFile", minimum=1, maximum=500)
    seen: set[str] = set()
    for item in decisions:
        if not isinstance(item, dict) or set(item) - {"itemId", "action", "note"}:
            raise CliInputError("INVALID_FIELD", "decisions 项字段必须精确匹配公共契约")
        if not {"itemId", "action"} <= set(item):
            raise CliInputError("INVALID_FIELD", "decisions 项缺少 itemId 或 action")
        item_id = _object_string(item, "itemId", maximum=128)
        if item_id in seen:
            raise CliInputError("INVALID_FIELD", "decisions 不能重复影响项")
        seen.add(item_id)
        action = _object_enum(item, "action", _IMPACT_ACTIONS)
        note = item.get("note", "")
        if not isinstance(note, str) or len(note) > 4_000 or action != "defer" and not note.strip():
            raise CliInputError("INVALID_FIELD", "影响决定必须包含有效依据")
        item["note"] = note
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/impact-reviews/{_id(payload, 'reviewId')}/decisions",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
            "decisions": decisions,
        },
    )


def start_render(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "baselineId", "shotId", "clientRequestId"},
        optional={"feeConfirmed"},
    )
    return request_json(
        runtime,
        "POST",
        f"{_baseline_path(payload)}/shots/{_id(payload, 'shotId')}/render-tasks",
        json={
            "clientRequestId": require_client_request_id(payload),
            "feeConfirmed": _bool(payload, "feeConfirmed", False),
        },
    )


def get_render(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "taskId"}, allow_output_file=True)
    return request_json(
        runtime, "GET", f"{_episode_path(payload)}/render-tasks/{_id(payload, 'taskId')}"
    )


def retry_render(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "taskId", "clientRequestId"},
        optional={"feeConfirmed"},
    )
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/render-tasks/{_id(payload, 'taskId')}/retry",
        json={
            "clientRequestId": require_client_request_id(payload),
            "feeConfirmed": _bool(payload, "feeConfirmed", False),
        },
    )


def create_edit(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "baselineId",
            "clientRequestId",
            "expectedHeadRevision",
            "basedOnVersionId",
        },
        optional={"edit", "editFile"},
    )
    edit = json_object_source(payload, inline_field="edit", file_field="editFile")
    if set(edit) != {"clips", "omissions"}:
        raise CliInputError("INVALID_FIELD", "edit 必须只包含 clips 与 omissions")
    clips = edit.get("clips")
    omissions = edit.get("omissions")
    if not isinstance(clips, list) or not 1 <= len(clips) <= 500:
        raise CliInputError("INVALID_FIELD", "edit.clips 必须包含 1 到 500 项")
    if not isinstance(omissions, list) or len(omissions) > 300:
        raise CliInputError("INVALID_FIELD", "edit.omissions 最多包含 300 项")
    return request_json(
        runtime,
        "POST",
        f"{_baseline_path(payload)}/edit-versions",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedHeadRevision": require_int(payload, "expectedHeadRevision", minimum=1),
            "basedOnVersionId": _nullable_identifier(payload, "basedOnVersionId", required=True),
            "clips": clips,
            "omissions": omissions,
        },
    )


def list_edits(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _list_post_versions(runtime, payload, "edit-versions")


def get_edit(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _get_post_version(runtime, payload, "edit-versions")


def create_mix(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "baselineId",
            "clientRequestId",
            "expectedHeadRevision",
            "basedOnVersionId",
            "editVersionId",
        },
        optional={"mix", "mixFile"},
    )
    mix = json_object_source(payload, inline_field="mix", file_field="mixFile")
    if set(mix) != {"audioClips", "subtitleCues"}:
        raise CliInputError("INVALID_FIELD", "mix 必须只包含 audioClips 与 subtitleCues")
    audio = mix.get("audioClips")
    subtitles = mix.get("subtitleCues")
    if not isinstance(audio, list) or len(audio) > 1_000:
        raise CliInputError("INVALID_FIELD", "mix.audioClips 最多包含 1000 项")
    if not isinstance(subtitles, list) or len(subtitles) > 2_000:
        raise CliInputError("INVALID_FIELD", "mix.subtitleCues 最多包含 2000 项")
    return request_json(
        runtime,
        "POST",
        f"{_baseline_path(payload)}/mix-versions",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedHeadRevision": require_int(payload, "expectedHeadRevision", minimum=1),
            "basedOnVersionId": _nullable_identifier(payload, "basedOnVersionId", required=True),
            "editVersionId": require_string(payload, "editVersionId", max_length=128),
            "audioClips": audio,
            "subtitleCues": subtitles,
        },
    )


def list_mixes(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _list_post_versions(runtime, payload, "mix-versions")


def get_mix(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _get_post_version(runtime, payload, "mix-versions")


def start_export(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "baselineId", "clientRequestId", "editVersionId", "mixVersionId"},
        optional={"resolution", "framesPerSecond", "burnSubtitles"},
    )
    return request_json(
        runtime,
        "POST",
        f"{_baseline_path(payload)}/export-tasks",
        json={
            "clientRequestId": require_client_request_id(payload),
            "editVersionId": require_string(payload, "editVersionId", max_length=128),
            "mixVersionId": require_string(payload, "mixVersionId", max_length=128),
            "resolution": enum_value(
                payload, "resolution", frozenset({"720p", "1080p"}), default="720p"
            ),
            "framesPerSecond": _enum_int(payload, "framesPerSecond", {24, 25, 30}, 24),
            "burnSubtitles": _bool(payload, "burnSubtitles", True),
        },
    )


def get_export(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "baselineId", "taskId"}, allow_output_file=True)
    return request_json(
        runtime, "GET", f"{_baseline_path(payload)}/export-tasks/{_id(payload, 'taskId')}"
    )


def retry_export(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId", "baselineId", "taskId", "clientRequestId"})
    return request_json(
        runtime,
        "POST",
        f"{_baseline_path(payload)}/export-tasks/{_id(payload, 'taskId')}/retry",
        json={"clientRequestId": require_client_request_id(payload)},
    )


def get_delivery(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload, required={"episodeId", "baselineId", "exportId"}, allow_output_file=True
    )
    return request_json(
        runtime, "GET", f"{_baseline_path(payload)}/exports/{_id(payload, 'exportId')}"
    )


def download_delivery(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "baselineId", "exportId", "outputFile"},
        allow_output_file=True,
    )
    export_id = require_string(payload, "exportId")
    response = runtime.require_api().request_bytes(
        "GET", f"{_baseline_path(payload)}/exports/{encode_id(export_id)}/content"
    )
    descriptor = write_bytes(
        require_string(payload, "outputFile"), response.content, response.media_type
    )
    return {"exportId": export_id, "resultFile": cast(JsonObject, dict(descriptor))}


def _list_baseline_root(runtime: CliRuntime, payload: JsonObject, suffix: str) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId"},
        optional={"limit", "beforeVersionNo"},
        allow_output_file=True,
    )
    query = _page_query(payload, maximum=100, cursor="beforeVersionNo")
    return request_json(runtime, "GET", f"{_episode_path(payload)}/{suffix}{query}")


def _list_post_versions(runtime: CliRuntime, payload: JsonObject, suffix: str) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "baselineId"},
        optional={"limit", "beforeVersionNo"},
        allow_output_file=True,
    )
    query = _page_query(payload, maximum=100, cursor="beforeVersionNo")
    return request_json(runtime, "GET", f"{_baseline_path(payload)}/{suffix}{query}")


def _get_post_version(runtime: CliRuntime, payload: JsonObject, suffix: str) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "baselineId", "versionId"},
        allow_output_file=True,
    )
    return request_json(
        runtime, "GET", f"{_baseline_path(payload)}/{suffix}/{_id(payload, 'versionId')}"
    )


def _page_query(payload: JsonObject, *, maximum: int, cursor: str) -> str:
    parts: list[tuple[str, object]] = [("limit", _limit(payload, maximum))]
    value = payload.get(cursor)
    if value is not None:
        if cursor == "beforeVersionNo":
            parts.append((cursor, require_int(payload, cursor, minimum=1)))
        else:
            parts.append((cursor, require_string(payload, cursor, max_length=128)))
    return _query(parts)


def _query(parts: list[tuple[str, object]]) -> str:
    return "?" + "&".join(
        f"{quote(name, safe='')}={quote(str(value), safe='')}" for name, value in parts
    )


def _episode_path(payload: JsonObject) -> str:
    return f"/api/v1/video/episodes/{_id(payload, 'episodeId')}"


def _baseline_path(payload: JsonObject) -> str:
    return f"{_episode_path(payload)}/production-baselines/{_id(payload, 'baselineId')}"


def _id(payload: JsonObject, name: str) -> str:
    return encode_id(require_string(payload, name, max_length=128))


def _limit(payload: JsonObject, maximum: int) -> int:
    return require_int(payload, "limit", minimum=1, maximum=maximum) if "limit" in payload else 20


def _nullable_identifier(payload: JsonObject, name: str, *, required: bool = False) -> str | None:
    if required and name not in payload:
        raise CliInputError("FIELD_REQUIRED", f"命令缺少字段：{name}")
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是非空字符串或 null")
    return value


def _sha256(payload: JsonObject, name: str) -> str:
    value = require_string(payload, name)
    if _SHA256.fullmatch(value) is None:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是小写 SHA-256")
    return value


def _bool(payload: JsonObject, name: str, default: bool) -> bool:
    value = payload.get(name, default)
    if type(value) is not bool:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是布尔值")
    return value


def _enum_int(payload: JsonObject, name: str, allowed: set[int], default: int) -> int:
    value = payload.get(name, default)
    if type(value) is not int or value not in allowed:
        raise CliInputError("INVALID_FIELD", f"{name} 不是受支持的整数选项")
    return value


def _array_source(
    payload: JsonObject,
    inline: str,
    file_field: str,
    *,
    minimum: int = 0,
    maximum: int,
    default: list[object] | None = None,
) -> list[object]:
    has_inline = inline in payload
    has_file = file_field in payload
    if not has_inline and not has_file and default is not None:
        return default
    if has_inline == has_file:
        raise CliInputError("JSON_SOURCE_REQUIRED", f"{inline} 与 {file_field} 必须且只能提供一个")
    value: object
    if has_inline:
        value = payload.get(inline)
    else:
        try:
            value = json.loads(read_utf8_text_exact(require_string(payload, file_field)))
        except json.JSONDecodeError as exc:
            raise CliInputError("INVALID_JSON_FILE", f"{file_field} 不是有效 JSON") from exc
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise CliInputError("INVALID_FIELD", f"{inline} 数量无效")
    return value


def _object_string(value: JsonObject, name: str, *, maximum: int) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item.strip() or len(item) > maximum:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是有效非空字符串")
    return item


def _object_enum(value: JsonObject, name: str, allowed: frozenset[str]) -> str:
    item = value.get(name)
    if not isinstance(item, str) or item not in allowed:
        raise CliInputError("INVALID_FIELD", f"{name} 不是受支持的选项")
    return item


def _read(
    name: str, handler: CommandHandler, *, file_output: FileOutputSpec = _DATA_JSON
) -> CommandSpec:
    return CommandSpec(name, handler, "json", "json", file_output, False, True, False)


def _write(name: str, handler: CommandHandler) -> CommandSpec:
    return CommandSpec(name, handler, "json", "json", _NO_FILE, True, True, True)


VIDEO_EPISODE_PRODUCTION_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    _read("long.video.production.capabilities.get", get_capabilities),
    _read("long.video.episode.storyboard.draft.get", get_storyboard_draft),
    _write("long.video.episode.storyboard.draft.save", save_storyboard_draft),
    _write("long.video.episode.storyboard.run.start", start_storyboard_run),
    _read("long.video.episode.storyboard.run.list", list_storyboard_runs),
    _read("long.video.episode.storyboard.run.get", get_storyboard_run),
    _read("long.video.episode.storyboard.candidate.get", get_storyboard_candidate),
    _write("long.video.episode.storyboard.candidate.adopt", adopt_storyboard_candidate),
    _write("long.video.episode.storyboard.confirmation.prepare", prepare_storyboard_confirmation),
    _read("long.video.episode.storyboard.confirmation.get", get_storyboard_confirmation),
    _write("long.video.episode.storyboard.confirmation.approve", approve_storyboard_confirmation),
    _read("long.video.episode.storyboard.version.list", list_storyboard_versions),
    _read("long.video.episode.storyboard.version.get", get_storyboard_version),
    _read("long.video.episode.take.list", list_takes),
    _read("long.video.episode.take.download", download_take, file_output=_NO_FILE),
    _write("long.video.episode.adoption.create", create_adoption),
    _read("long.video.episode.adoption.get", get_adoption),
    _write("long.video.episode.baseline.create", create_baseline),
    _read("long.video.episode.baseline.list", list_baselines),
    _read("long.video.episode.baseline.get", get_baseline),
    _read("long.video.episode.impact.list", list_impacts),
    _read("long.video.episode.impact.get", get_impact),
    _write("long.video.episode.impact.decide", decide_impact),
    _write("long.video.episode.render.start", start_render),
    _read("long.video.episode.render.get", get_render),
    _write("long.video.episode.render.retry", retry_render),
    _write("long.video.episode.edit.create", create_edit),
    _read("long.video.episode.edit.list", list_edits),
    _read("long.video.episode.edit.get", get_edit),
    _write("long.video.episode.mix.create", create_mix),
    _read("long.video.episode.mix.list", list_mixes),
    _read("long.video.episode.mix.get", get_mix),
    _write("long.video.episode.export.start", start_export),
    _read("long.video.episode.export.get", get_export),
    _write("long.video.episode.export.retry", retry_export),
    _read("long.video.episode.delivery.get", get_delivery),
    _read("long.video.episode.delivery.download", download_delivery, file_output=_NO_FILE),
)

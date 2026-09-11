"""独立分集、来源集和剧本生产的公开 CLI 命令。"""

from __future__ import annotations

import json
import re
from typing import cast

from ....io import read_utf8_text_exact
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
_SCRIPT_OPERATIONS = frozenset(
    {"episode_script_generate", "episode_script_revise"}
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def list_episodes(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"projectId"}, allow_output_file=True)
    project_id = encode_id(require_string(payload, "projectId"))
    return request_json(runtime, "GET", f"/api/v1/video/projects/{project_id}/episodes")


def get_episode(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId"}, allow_output_file=True)
    return request_json(runtime, "GET", _episode_path(payload))


def create_episode(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"projectId", "clientRequestId", "title"},
        optional={"creativeIntent", "targetDurationSeconds"},
    )
    project_id = encode_id(require_string(payload, "projectId"))
    body: JsonObject = {
        "clientRequestId": require_client_request_id(payload),
        "title": require_string(payload, "title", max_length=240),
        "creativeIntent": _optional_text(payload, "creativeIntent", default="", maximum=4_000),
        "targetDurationSeconds": _optional_nullable_int(
            payload, "targetDurationSeconds", minimum=1, maximum=86_400
        ),
    }
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/projects/{project_id}/episodes",
        json=body,
    )


def update_episode(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "clientRequestId", "expectedRevision"},
        optional={"title", "creativeIntent", "targetDurationSeconds"},
    )
    body: JsonObject = {
        "clientRequestId": require_client_request_id(payload),
        "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
    }
    if "title" in payload:
        body["title"] = _nullable_text(payload, "title", maximum=240, non_empty=True)
    if "creativeIntent" in payload:
        body["creativeIntent"] = _nullable_text(
            payload, "creativeIntent", maximum=4_000, non_empty=False
        )
    if "targetDurationSeconds" in payload:
        body["targetDurationSeconds"] = _optional_nullable_int(
            payload, "targetDurationSeconds", minimum=1, maximum=86_400
        )
    return request_json(runtime, "PATCH", _episode_path(payload), json=body)


def reorder_episodes(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "projectId",
            "clientRequestId",
            "expectedProjectRevision",
            "episodeIds",
        },
    )
    episode_ids = string_list(payload, "episodeIds", max_items=1_000)
    if not episode_ids:
        raise CliInputError("INVALID_FIELD", "episodeIds 不能为空")
    project_id = encode_id(require_string(payload, "projectId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/projects/{project_id}/episodes/reorder",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedProjectRevision": require_int(
                payload, "expectedProjectRevision", minimum=1
            ),
            "episodeIds": episode_ids,
        },
    )


def create_source_set(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "clientRequestId", "expectedRevision"},
        optional={"basedOnVersionId", "sources", "sourcesFile"},
    )
    sources = _source_selections(payload)
    body: JsonObject = {
        "clientRequestId": require_client_request_id(payload),
        "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
        "basedOnVersionId": _nullable_text(
            payload, "basedOnVersionId", maximum=128, non_empty=True
        ),
        "sources": sources,
    }
    return request_json(runtime, "POST", f"{_episode_path(payload)}/source-sets", json=body)


def list_source_sets(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId"}, allow_output_file=True)
    return request_json(runtime, "GET", f"{_episode_path(payload)}/source-sets")


def get_source_set(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "versionId"},
        allow_output_file=True,
    )
    version_id = encode_id(require_string(payload, "versionId"))
    return request_json(
        runtime, "GET", f"{_episode_path(payload)}/source-sets/{version_id}"
    )


def get_script_draft(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId"}, allow_output_file=True)
    return request_json(runtime, "GET", f"{_episode_path(payload)}/script/draft")


def save_script_draft(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "clientRequestId",
            "expectedRevision",
            "sourceSetVersionId",
            "baseScriptVersionId",
        },
        optional={"document", "documentFile"},
    )
    document = json_object_source(
        payload, inline_field="document", file_field="documentFile"
    )
    return request_json(
        runtime,
        "PUT",
        f"{_episode_path(payload)}/script/draft",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedRevision": require_int(payload, "expectedRevision", minimum=1),
            "sourceSetVersionId": _required_nullable_identifier(
                payload, "sourceSetVersionId"
            ),
            "baseScriptVersionId": _required_nullable_identifier(
                payload, "baseScriptVersionId"
            ),
            "document": document,
        },
    )


def start_script_run(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "episodeId",
            "clientRequestId",
            "expectedDraftRevision",
            "operation",
            "instruction",
        },
        optional={"selectedSceneIds"},
    )
    operation = enum_value(payload, "operation", _SCRIPT_OPERATIONS)
    selected_scene_ids = string_list(
        payload, "selectedSceneIds", max_items=60
    )
    if operation == "episode_script_generate" and selected_scene_ids:
        raise CliInputError("INVALID_FIELD", "起草操作不能携带局部修订范围")
    if operation == "episode_script_revise" and not selected_scene_ids:
        raise CliInputError("INVALID_FIELD", "修订必须选择至少一个稳定场次")
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/script/runs",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedDraftRevision": require_int(
                payload, "expectedDraftRevision", minimum=1
            ),
            "operation": operation,
            "selectedSceneIds": selected_scene_ids,
            "instruction": require_string(payload, "instruction", max_length=8_000),
        },
    )


def get_script_run(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "runId"},
        allow_output_file=True,
    )
    run_id = encode_id(require_string(payload, "runId"))
    return request_json(runtime, "GET", f"{_episode_path(payload)}/script/runs/{run_id}")


def adopt_script_candidate(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
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
    artifact_id = encode_id(require_string(payload, "artifactId"))
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/script/candidates/{artifact_id}/adopt",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedArtifactRevision": require_int(
                payload, "expectedArtifactRevision", minimum=1
            ),
            "expectedDraftRevision": require_int(
                payload, "expectedDraftRevision", minimum=1
            ),
        },
    )


def prepare_script_confirmation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
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
        f"{_episode_path(payload)}/script/confirmations",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedDraftRevision": require_int(
                payload, "expectedDraftRevision", minimum=1
            ),
            "expectedEpisodeRevision": require_int(
                payload, "expectedEpisodeRevision", minimum=1
            ),
        },
    )


def get_script_confirmation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "artifactId"},
        allow_output_file=True,
    )
    artifact_id = encode_id(require_string(payload, "artifactId"))
    return request_json(
        runtime,
        "GET",
        f"{_episode_path(payload)}/script/confirmations/{artifact_id}",
    )


def approve_script_confirmation(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
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
    confirmation_hash = require_string(payload, "confirmationHash")
    if _SHA256.fullmatch(confirmation_hash) is None:
        raise CliInputError("INVALID_FIELD", "confirmationHash 必须是小写 SHA-256")
    artifact_id = encode_id(require_string(payload, "artifactId"))
    return request_json(
        runtime,
        "POST",
        f"{_episode_path(payload)}/script/confirmations/{artifact_id}/approve",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedArtifactRevision": require_int(
                payload, "expectedArtifactRevision", minimum=1
            ),
            "expectedDraftRevision": require_int(
                payload, "expectedDraftRevision", minimum=1
            ),
            "expectedEpisodeRevision": require_int(
                payload, "expectedEpisodeRevision", minimum=1
            ),
            "confirmationHash": confirmation_hash,
        },
    )


def list_script_versions(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"episodeId"}, allow_output_file=True)
    return request_json(runtime, "GET", f"{_episode_path(payload)}/script/versions")


def get_script_version(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "versionId"},
        allow_output_file=True,
    )
    version_id = encode_id(require_string(payload, "versionId"))
    return request_json(
        runtime, "GET", f"{_episode_path(payload)}/script/versions/{version_id}"
    )


def get_episode_command(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"episodeId", "clientRequestId"},
        allow_output_file=True,
    )
    request_id = encode_id(require_client_request_id(payload))
    return request_json(runtime, "GET", f"{_episode_path(payload)}/commands/{request_id}")


def get_project_episode_command(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"projectId", "clientRequestId"},
        allow_output_file=True,
    )
    project_id = encode_id(require_string(payload, "projectId"))
    request_id = encode_id(require_client_request_id(payload))
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/projects/{project_id}/episode-commands/{request_id}",
    )


def _episode_path(payload: JsonObject) -> str:
    return f"/api/v1/video/episodes/{encode_id(require_string(payload, 'episodeId'))}"


def _optional_text(
    payload: JsonObject,
    name: str,
    *,
    default: str,
    maximum: int,
) -> str:
    if name not in payload:
        return default
    value = payload.get(name)
    if not isinstance(value, str):
        raise CliInputError("INVALID_FIELD", f"{name} 必须是字符串")
    if len(value) > maximum:
        raise CliInputError("INVALID_FIELD", f"{name} 长度不能超过 {maximum}")
    return value


def _nullable_text(
    payload: JsonObject,
    name: str,
    *,
    maximum: int,
    non_empty: bool,
) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or (non_empty and not value.strip()):
        suffix = "非空字符串或 null" if non_empty else "字符串或 null"
        raise CliInputError("INVALID_FIELD", f"{name} 必须是{suffix}")
    if len(value) > maximum:
        raise CliInputError("INVALID_FIELD", f"{name} 长度不能超过 {maximum}")
    return value


def _required_nullable_identifier(payload: JsonObject, name: str) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是非空字符串或 null")
    return value


def _optional_nullable_int(
    payload: JsonObject,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    value = payload.get(name)
    if value is None:
        return None
    return require_int(payload, name, minimum=minimum, maximum=maximum)


def _source_selections(payload: JsonObject) -> list[JsonObject]:
    has_inline = "sources" in payload
    has_file = "sourcesFile" in payload
    if has_inline == has_file:
        raise CliInputError(
            "JSON_SOURCE_REQUIRED", "sources 与 sourcesFile 必须且只能提供一个"
        )
    value: object
    if has_inline:
        value = payload.get("sources")
    else:
        path = require_string(payload, "sourcesFile")
        try:
            value = json.loads(read_utf8_text_exact(path))
        except json.JSONDecodeError as exc:
            raise CliInputError("INVALID_JSON_FILE", "sourcesFile 不是有效 JSON") from exc
    if not isinstance(value, list) or not value or len(value) > 40:
        raise CliInputError("INVALID_FIELD", "sources 必须包含 1 到 40 个来源")
    result: list[JsonObject] = []
    chapter_ids: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise CliInputError("INVALID_FIELD", "sources 每项必须是 JSON 对象")
        source = cast(JsonObject, raw)
        if set(source) != {"chapterId", "expectedUpdatedAt", "sourceHash", "ranges"}:
            raise CliInputError("INVALID_FIELD", "sources 项字段必须精确匹配公共契约")
        chapter_id = require_string(source, "chapterId", max_length=128)
        if chapter_id in chapter_ids:
            raise CliInputError("INVALID_FIELD", "sources 不能包含重复章节")
        chapter_ids.add(chapter_id)
        require_string(source, "expectedUpdatedAt")
        source_hash = require_string(source, "sourceHash")
        if _SHA256.fullmatch(source_hash) is None:
            raise CliInputError("INVALID_FIELD", "sourceHash 必须是小写 SHA-256")
        ranges = source.get("ranges")
        if not isinstance(ranges, list) or not ranges or len(ranges) > 100:
            raise CliInputError("INVALID_FIELD", "ranges 必须包含 1 到 100 个范围")
        for item in ranges:
            if not isinstance(item, dict) or set(item) != {"start", "end"}:
                raise CliInputError("INVALID_FIELD", "ranges 项必须只包含 start 和 end")
            start = item.get("start")
            end = item.get("end")
            if type(start) is not int or type(end) is not int or start < 0 or end <= start:
                raise CliInputError("INVALID_FIELD", "ranges 必须是非空 Unicode 半开区间")
        result.append(source)
    return result


def _read_spec(name: str, handler: CommandHandler) -> CommandSpec:
    return CommandSpec(
        name=name,
        handler=handler,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    )


def _write_spec(name: str, handler: CommandHandler) -> CommandSpec:
    return CommandSpec(
        name=name,
        handler=handler,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    )


VIDEO_EPISODE_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    _read_spec("long.video.episode.list", list_episodes),
    _read_spec("long.video.episode.get", get_episode),
    _write_spec("long.video.episode.create", create_episode),
    _write_spec("long.video.episode.update", update_episode),
    _write_spec("long.video.episode.reorder", reorder_episodes),
    _write_spec("long.video.episode.source.create", create_source_set),
    _read_spec("long.video.episode.source.list", list_source_sets),
    _read_spec("long.video.episode.source.get", get_source_set),
    _read_spec("long.video.episode.script.draft.get", get_script_draft),
    _write_spec("long.video.episode.script.draft.save", save_script_draft),
    _write_spec("long.video.episode.script.run.start", start_script_run),
    _read_spec("long.video.episode.script.run.get", get_script_run),
    _write_spec("long.video.episode.script.candidate.adopt", adopt_script_candidate),
    _write_spec("long.video.episode.script.confirmation.prepare", prepare_script_confirmation),
    _read_spec("long.video.episode.script.confirmation.get", get_script_confirmation),
    _write_spec("long.video.episode.script.confirmation.approve", approve_script_confirmation),
    _read_spec("long.video.episode.script.version.list", list_script_versions),
    _read_spec("long.video.episode.script.version.get", get_script_version),
    _read_spec("long.video.episode.command.get", get_episode_command),
    _read_spec("long.video.episode.project-command.get", get_project_episode_command),
)

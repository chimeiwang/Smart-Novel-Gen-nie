from __future__ import annotations

from ...json_types import JsonObject
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result
from .mutation_support import (
    encode_path_id,
    require_content_source,
    require_data_fields,
    require_expected_updated_at,
    require_payload_fields,
    require_string,
)

_TEXT_REQUIRED_FIELDS = frozenset({"novelId", "expectedUpdatedAt"})
_TEXT_OPTIONAL_FIELDS = frozenset({"content", "contentFile"})
_STRUCTURED_REQUIRED_FIELDS = frozenset({"novelId", "expectedUpdatedAt", "data"})
_WRITING_BIBLE_FIELDS = frozenset({
    "storyLengthProfile",
    "targetTotalWordCount",
    "genre",
    "targetReaders",
    "coreSellingPoint",
    "readerPromise",
    "appealModel",
    "taboo",
    "comparableTitles",
    "notes",
})
_PLOT_PROGRESS_FIELDS = frozenset({
    "currentStage",
    "currentGoal",
    "currentConflict",
    "nextMilestone",
})


def _planning_path(payload: JsonObject, suffix: str) -> str:
    novel_id = encode_path_id(require_string(payload, "novelId"))
    return f"/api/v1/novels/{novel_id}/{suffix}"


def _save_text(
    runtime: CliRuntime,
    payload: JsonObject,
    *,
    suffix: str,
) -> JsonObject:
    require_payload_fields(
        payload,
        required=_TEXT_REQUIRED_FIELDS,
        optional=_TEXT_OPTIONAL_FIELDS,
    )
    response = runtime.require_api().request(
        "PUT",
        _planning_path(payload, suffix),
        json={
            "content": require_content_source(payload),
            "expectedUpdatedAt": require_expected_updated_at(
                payload,
                nullable=True,
            ),
        },
    )
    return ensure_command_json_result(response)


def save_story_background(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _save_text(runtime, payload, suffix="story-background")


def save_world_setting(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _save_text(runtime, payload, suffix="world-setting")


def save_story_progress(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _save_text(runtime, payload, suffix="story-progress")


def save_writing_bible(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(payload, required=_STRUCTURED_REQUIRED_FIELDS)
    data = require_data_fields(payload, allowed=_WRITING_BIBLE_FIELDS)
    if (
        "storyLengthProfile" in data
        and data["storyLengthProfile"] != "long_serial"
    ):
        raise CliInputError(
            "INVALID_STORY_LENGTH_PROFILE",
            "长篇作品圣经的 storyLengthProfile 必须严格等于字符串 long_serial",
        )
    response = runtime.require_api().request(
        "PUT",
        _planning_path(payload, "writing-bible"),
        json={
            **data,
            "expectedUpdatedAt": require_expected_updated_at(
                payload,
                nullable=True,
            ),
        },
    )
    return ensure_command_json_result(response)


def save_plot_progress(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_payload_fields(payload, required=_STRUCTURED_REQUIRED_FIELDS)
    data = require_data_fields(payload, allowed=_PLOT_PROGRESS_FIELDS)
    require_string(data, "currentStage")
    response = runtime.require_api().request(
        "PUT",
        _planning_path(payload, "plot-progress"),
        json={
            **data,
            "expectedUpdatedAt": require_expected_updated_at(
                payload,
                nullable=True,
            ),
        },
    )
    return ensure_command_json_result(response)


_NO_FILE = FileOutputSpec(kind="none")


PLANNING_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.lore.story-background.save",
        handler=save_story_background,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.lore.world-setting.save",
        handler=save_world_setting,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.lore.writing-bible.save",
        handler=save_writing_bible,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.lore.story-progress.save",
        handler=save_story_progress,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.plot-progress.save",
        handler=save_plot_progress,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

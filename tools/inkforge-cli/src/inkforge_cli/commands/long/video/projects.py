"""视频项目与素材的公开 CLI 命令。"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import cast

from ....io import write_bytes
from ....json_types import JsonObject
from ....registry import CommandSpec, FileOutputSpec
from ....runtime import CliInputError, CliRuntime, ensure_command_json_result
from .support import (
    encode_id,
    enum_value,
    request_json,
    require_fields,
    require_string,
)

_NO_FILE = FileOutputSpec(kind="none")
_DATA_JSON = FileOutputSpec(kind="data_json")
_PROJECT_MODES = frozenset({"concept", "trailer", "highlight", "series"})
_ASPECT_RATIOS = frozenset({"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"})
_ASSET_MODALITIES = frozenset({"image", "video", "audio"})
_ASSET_DUTIES = frozenset(
    {
        "identity",
        "costume",
        "scene",
        "prop",
        "style",
        "storyboard",
        "keyframe",
        "motion",
        "camera",
        "voice",
        "ambience",
        "music",
    }
)
_SOURCE_KINDS = frozenset(
    {"user_upload", "authorized_real", "virtual", "model_generated"}
)
_RIGHTS_STATUSES = frozenset({"confirmed", "restricted", "rejected"})


def list_projects(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"novelId"}, allow_output_file=True)
    novel_id = encode_id(require_string(payload, "novelId"))
    return request_json(runtime, "GET", f"/api/v1/video/novels/{novel_id}/projects")


def get_project(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"projectId"}, allow_output_file=True)
    project_id = encode_id(require_string(payload, "projectId"))
    return request_json(runtime, "GET", f"/api/v1/video/projects/{project_id}")


def create_project(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"novelId", "title"},
        optional={"mode", "targetAspectRatio", "targetLanguage"},
    )
    novel_id = encode_id(require_string(payload, "novelId"))
    body: JsonObject = {
        "title": require_string(payload, "title", max_length=200),
        "mode": enum_value(payload, "mode", _PROJECT_MODES, default="highlight"),
        "targetAspectRatio": enum_value(
            payload,
            "targetAspectRatio",
            _ASPECT_RATIOS,
            default="16:9",
        ),
        "targetLanguage": require_string(
            payload,
            "targetLanguage",
            min_length=2,
            max_length=32,
        )
        if "targetLanguage" in payload
        else "zh-CN",
    }
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/novels/{novel_id}/projects",
        json=body,
    )


def upload_asset(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"projectId", "filePath", "name", "modality", "duty"},
        optional={"sourceKind"},
    )
    project_id = encode_id(require_string(payload, "projectId"))
    file_path = Path(require_string(payload, "filePath")).expanduser()
    if not file_path.is_file():
        raise CliInputError("LOCAL_FILE_NOT_FOUND", "filePath 不是可读取的普通文件")
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    form = {
        "name": require_string(payload, "name", max_length=200),
        "modality": enum_value(payload, "modality", _ASSET_MODALITIES),
        "duty": enum_value(payload, "duty", _ASSET_DUTIES),
        "sourceKind": enum_value(
            payload,
            "sourceKind",
            _SOURCE_KINDS,
            default="user_upload",
        ),
    }
    with file_path.open("rb") as stream:
        response = runtime.require_api().request(
            "POST",
            f"/api/v1/video/projects/{project_id}/assets",
            data=form,
            files={"file": (file_path.name, stream, content_type)},
        )
    return ensure_command_json_result(response)


def update_asset_rights(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"assetId", "rightsStatus"})
    asset_id = encode_id(require_string(payload, "assetId"))
    return request_json(
        runtime,
        "PATCH",
        f"/api/v1/video/assets/{asset_id}/rights",
        json={"rightsStatus": enum_value(payload, "rightsStatus", _RIGHTS_STATUSES)},
    )


def download_asset(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    """把完整素材原子写入显式文件，避免二进制进入标准输出。"""

    return _write_asset_file(runtime, payload, endpoint="content")


def preview_asset(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    """读取浏览器内联预览接口，并把完整原始字节写入显式文件。"""

    return _write_asset_file(runtime, payload, endpoint="preview")


def _write_asset_file(
    runtime: CliRuntime,
    payload: JsonObject,
    *,
    endpoint: str,
) -> JsonObject:
    require_fields(
        payload,
        required={"assetId", "outputFile"},
        allow_output_file=True,
    )
    asset_id = require_string(payload, "assetId")
    output_file = require_string(payload, "outputFile")
    response = runtime.require_api().request_bytes(
        "GET",
        f"/api/v1/video/assets/{encode_id(asset_id)}/{endpoint}",
    )
    descriptor = write_bytes(output_file, response.content, response.media_type)
    return {
        "assetId": asset_id,
        "resultFile": cast(JsonObject, dict(descriptor)),
    }


VIDEO_PROJECT_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.video.project.list",
        handler=list_projects,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.project.get",
        handler=get_project,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.project.create",
        handler=create_project,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.asset.upload",
        handler=upload_asset,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.asset.rights",
        handler=update_asset_rights,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.asset.download",
        handler=download_asset,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.asset.preview",
        handler=preview_asset,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

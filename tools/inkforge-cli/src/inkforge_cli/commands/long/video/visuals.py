"""视觉设定版本与逐镜参考绑定 CLI 命令。"""

from __future__ import annotations

import re
from typing import cast

from ....json_types import JsonObject, JsonValue
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
    string_list,
)

_NO_FILE = FileOutputSpec(kind="none")
_DATA_JSON = FileOutputSpec(kind="data_json")
_SETTING_KINDS = frozenset({"character", "location", "item"})
_CANON_DUTIES = frozenset({"identity", "costume", "scene", "prop"})
_EXPECTED_KIND_BY_DUTY = {
    "identity": "character",
    "costume": "character",
    "scene": "location",
    "prop": "item",
}
_VARIANT_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def list_canons(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(payload, required={"projectId"}, allow_output_file=True)
    project_id = encode_id(require_string(payload, "projectId"))
    return request_json(
        runtime,
        "GET",
        f"/api/v1/video/projects/{project_id}/visual-canons",
    )


def set_canon_candidate(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "projectId",
            "clientRequestId",
            "settingKind",
            "settingId",
            "duty",
            "variantKey",
            "label",
            "candidateAssetId",
        },
        optional={"includeFeatures", "excludeFeatures", "defaultStrength"},
    )
    setting_kind = enum_value(payload, "settingKind", _SETTING_KINDS)
    duty = enum_value(payload, "duty", _CANON_DUTIES)
    if _EXPECTED_KIND_BY_DUTY[duty] != setting_kind:
        raise CliInputError(
            "VISUAL_CANON_KIND_DUTY_MISMATCH",
            "视觉设定职责与文字设定类型不匹配",
        )
    variant_key = require_string(payload, "variantKey", max_length=64)
    if _VARIANT_KEY.fullmatch(variant_key) is None:
        raise CliInputError(
            "INVALID_VARIANT_KEY",
            "variantKey 必须以小写字母或数字开头，且只能包含小写字母、数字、下划线和连字符",
        )
    include_features = _feature_list(payload, "includeFeatures")
    exclude_features = _feature_list(payload, "excludeFeatures")
    project_id = encode_id(require_string(payload, "projectId"))
    body: JsonObject = {
        "clientRequestId": require_client_request_id(payload),
        "settingKind": setting_kind,
        "settingId": require_string(payload, "settingId"),
        "duty": duty,
        "variantKey": variant_key,
        "label": require_string(payload, "label", max_length=120),
        "candidateAssetId": require_string(payload, "candidateAssetId"),
        "includeFeatures": cast(list[JsonValue], include_features),
        "excludeFeatures": cast(list[JsonValue], exclude_features),
        "defaultStrength": require_int(
            payload,
            "defaultStrength",
            minimum=1,
            maximum=100,
        )
        if "defaultStrength" in payload
        else 70,
    }
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/projects/{project_id}/visual-canons",
        json=body,
    )


def approve_canon(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={
            "canonId",
            "clientRequestId",
            "expectedRevision",
            "candidateAssetId",
        },
    )
    canon_id = encode_id(require_string(payload, "canonId"))
    return request_json(
        runtime,
        "POST",
        f"/api/v1/video/visual-canons/{canon_id}/approve",
        json={
            "clientRequestId": require_client_request_id(payload),
            "expectedRevision": require_int(
                payload,
                "expectedRevision",
                minimum=1,
            ),
            "candidateAssetId": require_string(payload, "candidateAssetId"),
        },
    )


def save_references(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    require_fields(
        payload,
        required={"adaptationId", "shotId", "expectedRevision", "references"},
    )
    references = _references(payload)
    adaptation_id = encode_id(require_string(payload, "adaptationId"))
    shot_id = encode_id(require_string(payload, "shotId"))
    return request_json(
        runtime,
        "PUT",
        f"/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/visual-references",
        json={
            "expectedRevision": require_int(
                payload,
                "expectedRevision",
                minimum=0,
            ),
            "references": references,
        },
    )


def _feature_list(payload: JsonObject, name: str) -> list[str]:
    values = string_list(payload, name, max_items=20)
    if any(len(value) > 120 for value in values):
        raise CliInputError("INVALID_FIELD", f"{name} 单项长度不能超过 120")
    return values


def _references(payload: JsonObject) -> list[JsonObject]:
    raw = payload.get("references")
    if not isinstance(raw, list) or len(raw) > 20:
        raise CliInputError("INVALID_FIELD", "references 必须是最多 20 项的数组")
    result: list[JsonObject] = []
    version_ids: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CliInputError("INVALID_FIELD", "references 每一项必须是 JSON 对象")
        reference = item
        require_fields(
            reference,
            required={"canonVersionId", "strength"},
        )
        version_id = require_string(reference, "canonVersionId")
        version_ids.append(version_id)
        result.append(
            {
                "canonVersionId": version_id,
                "strength": require_int(
                    reference,
                    "strength",
                    minimum=1,
                    maximum=100,
                ),
            }
        )
    if len(set(version_ids)) != len(version_ids):
        raise CliInputError(
            "DUPLICATE_CANON_VERSION",
            "同一镜头不能重复绑定同一视觉设定版本",
        )
    return result


VIDEO_VISUAL_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.video.canon.list",
        handler=list_canons,
        inputMode="json",
        outputMode="json",
        fileOutput=_DATA_JSON,
        mutation=False,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
    CommandSpec(
        name="long.video.canon.candidate.set",
        handler=set_canon_candidate,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.canon.approve",
        handler=approve_canon,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.video.reference.save",
        handler=save_references,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=False,
    ),
)

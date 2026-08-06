from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from ...api import CoreApiError
from ...io import read_utf8_text_exact
from ...json_types import JsonObject, JsonValue
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import (
    CliInputError,
    CliRuntime,
    CoreResponseContractError,
    ensure_command_json_result,
    require_client_request_id,
)

type ArtifactDecision = Literal["approve", "revise", "discard"]

_ALLOWED_FIELDS = {
    "profile",
    "artifactId",
    "clientRequestId",
    "expectedRevision",
    "editedContent",
    "editedContentFile",
    "selectedUpdateRefs",
    "userMessage",
}
_EDIT_FIELDS = {"editedContent", "editedContentFile", "selectedUpdateRefs"}


def _require_string(payload: JsonObject, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def _require_stable_client_request_id(payload: JsonObject) -> str:
    value = require_client_request_id(payload)
    if len(value) > 128:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "clientRequestId 长度必须为 16 到 128 个字符",
        )
    return value


def _require_expected_revision(payload: JsonObject) -> int:
    value = payload.get("expectedRevision")
    if type(value) is not int or value < 1:
        raise CliInputError(
            "INVALID_EXPECTED_REVISION",
            "expectedRevision 必须是大于等于 1 的整数",
        )
    return value


def _reject_unexpected_fields(payload: JsonObject) -> None:
    unexpected = sorted(set(payload) - _ALLOWED_FIELDS)
    if unexpected:
        raise CliInputError(
            "UNEXPECTED_FIELD",
            f"命令不接受字段：{unexpected[0]}",
        )


def _edited_content(payload: JsonObject) -> str | None:
    inline = payload.get("editedContent")
    file_path = payload.get("editedContentFile")
    if inline is not None and file_path is not None:
        raise CliInputError(
            "EDITED_CONTENT_CONFLICT",
            "editedContent 与 editedContentFile 至多提供一个",
        )
    if inline is not None:
        if not isinstance(inline, str):
            raise CliInputError(
                "INVALID_EDITED_CONTENT",
                "editedContent 必须是字符串或 null",
            )
        return inline
    if file_path is not None:
        if not isinstance(file_path, str) or not file_path:
            raise CliInputError(
                "INVALID_EDITED_CONTENT_FILE",
                "editedContentFile 必须是非空字符串",
            )
        return read_utf8_text_exact(file_path)
    return None


def _require_verified_source(
    runtime: CliRuntime,
    *,
    artifact_id: str,
    artifact_path: str,
) -> None:
    response = runtime.require_api().request("GET", artifact_path)
    if not isinstance(response, dict):
        raise CoreResponseContractError("Artifact 响应不是 JSON 对象")
    status = response.get("sourceBindingStatus")
    if status == "verified":
        return
    if status in {"legacy_missing", "not_yet_supported"}:
        raise CoreApiError(
            409,
            code="SOURCE_BINDING_NOT_VERIFIED",
            message="草案缺少可验证的来源绑定，拒绝执行该决定",
            details={
                "artifactId": artifact_id,
                "sourceBindingStatus": status,
            },
        )
    raise CoreResponseContractError("Artifact 响应缺少有效 sourceBindingStatus")


def _decision_body(
    payload: JsonObject,
    *,
    decision: ArtifactDecision,
) -> JsonObject:
    _reject_unexpected_fields(payload)
    body: JsonObject = {
        "clientRequestId": _require_stable_client_request_id(payload),
        "expectedRevision": _require_expected_revision(payload),
        "decision": decision,
    }

    if decision == "discard":
        forbidden = sorted(_EDIT_FIELDS.intersection(payload))
        if forbidden:
            raise CliInputError(
                "DISCARD_EDIT_FIELDS_FORBIDDEN",
                f"discard 不接受字段：{forbidden[0]}",
            )
    else:
        edited_content = _edited_content(payload)
        if edited_content is not None:
            body["editedContent"] = edited_content
        if "selectedUpdateRefs" in payload:
            body["selectedUpdateRefs"] = payload["selectedUpdateRefs"]

    if "userMessage" in payload:
        user_message: JsonValue = payload["userMessage"]
        if user_message is not None and not isinstance(user_message, str):
            raise CliInputError(
                "INVALID_USER_MESSAGE",
                "userMessage 必须是字符串或 null",
            )
        body["userMessage"] = user_message
    if decision == "revise":
        user_message = body.get("userMessage")
        if not isinstance(user_message, str) or not user_message.strip():
            raise CliInputError(
                "USER_MESSAGE_REQUIRED",
                "revise 必须提供非空 userMessage",
            )
    return body


def _decide(
    runtime: CliRuntime,
    payload: JsonObject,
    *,
    decision: ArtifactDecision,
) -> JsonObject:
    artifact_id = _require_string(payload, "artifactId")
    artifact_path = f"/api/v1/review-artifacts/{quote(artifact_id, safe='')}"
    body = _decision_body(payload, decision=decision)
    if decision != "discard":
        _require_verified_source(
            runtime,
            artifact_id=artifact_id,
            artifact_path=artifact_path,
        )
    response = runtime.require_api().request(
        "POST",
        f"{artifact_path}/decision",
        json=body,
    )
    return ensure_command_json_result(response)


def approve(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _decide(runtime, payload, decision="approve")


def revise(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _decide(runtime, payload, decision="revise")


def discard(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    return _decide(runtime, payload, decision="discard")


_NO_FILE = FileOutputSpec(kind="none")

ARTIFACT_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.artifact.approve",
        handler=approve,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.artifact.revise",
        handler=revise,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.artifact.discard",
        handler=discard,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
)

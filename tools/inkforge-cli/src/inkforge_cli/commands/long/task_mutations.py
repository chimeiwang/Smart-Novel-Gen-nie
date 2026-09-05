from __future__ import annotations

import re
from urllib.parse import quote

from ...json_types import JsonObject, JsonValue
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result
from .workflow_input import has_complete_text

_OPERATIONS = {
    "answer_question",
    "plan_chapter",
    "write_chapter",
    "review_chapter",
    "rewrite_scene",
    "create_lore",
    "revise_lore",
    "create_outline",
    "revise_outline",
    "manage_foreshadowing",
    "rewrite_chapter_selection",
    "rewrite_outline_selection",
}
_START_FIELDS = {
    "profile",
    "clientRequestId",
    "novelId",
    "chapterId",
    "writingSessionId",
    "operation",
    "target",
    "scope",
    "selectionTarget",
    "targetWordCount",
    "userInstruction",
}
_RESUME_FIELDS = {
    "profile",
    "taskId",
    "clientRequestId",
    "writingSessionId",
    "userMessage",
}
_CANCEL_FIELDS = {"profile", "taskId", "clientRequestId"}


def _require_string(payload: JsonObject, name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise CliInputError("FIELD_REQUIRED", f"缺少字符串字段 {name}")
    return value


def _require_client_request_id(payload: JsonObject) -> str:
    value = payload.get("clientRequestId")
    if not isinstance(value, str) or not 16 <= len(value) <= 128:
        raise CliInputError(
            "CLIENT_REQUEST_ID_REQUIRED",
            "clientRequestId 长度必须为 16 到 128 个字符",
        )
    return value


def _reject_unexpected_fields(payload: JsonObject, allowed: set[str]) -> None:
    unexpected = sorted(set(payload) - allowed)
    if unexpected:
        raise CliInputError(
            "UNEXPECTED_FIELD",
            f"命令不接受字段：{unexpected[0]}",
        )


def _optional_string(
    payload: JsonObject,
    name: str,
) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise CliInputError("INVALID_FIELD", f"{name} 必须是非空字符串或 null")
    return value


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SELECTION_TARGET_FIELDS = {
    "resourceType",
    "resourceId",
    "baseUpdatedAt",
    "baseContentHash",
    "selectionStart",
    "selectionEnd",
    "selectedTextHash",
}


def _require_selection_target(
    payload: JsonObject,
    *,
    operation: str,
    chapter_id: str,
) -> JsonObject | None:
    raw = payload.get("selectionTarget")
    selection_operations = {
        "rewrite_chapter_selection",
        "rewrite_outline_selection",
    }
    if operation not in selection_operations:
        if raw is not None:
            raise CliInputError(
                "SELECTION_TARGET_FORBIDDEN",
                "普通长篇操作不能携带 selectionTarget",
            )
        return None
    if not isinstance(raw, dict):
        raise CliInputError("SELECTION_TARGET_REQUIRED", "选区操作必须携带 selectionTarget")
    unexpected = sorted(set(raw) - _SELECTION_TARGET_FIELDS)
    if unexpected:
        raise CliInputError("UNEXPECTED_FIELD", f"selectionTarget 不接受字段：{unexpected[0]}")
    for name in ("resourceType", "resourceId", "baseUpdatedAt"):
        if not isinstance(raw.get(name), str) or not raw[name]:
            raise CliInputError("INVALID_SELECTION_TARGET", f"{name} 必须是非空字符串")
    resource_type = raw["resourceType"]
    if resource_type not in {"chapter_content", "outline_content", "outline_node_content"}:
        raise CliInputError("INVALID_SELECTION_TARGET", "resourceType 无效")
    if operation == "rewrite_chapter_selection" and resource_type != "chapter_content":
        raise CliInputError("INVALID_SELECTION_TARGET", "章节选区只能指向 chapter_content")
    if operation == "rewrite_outline_selection" and resource_type not in {
        "outline_content",
        "outline_node_content",
    }:
        raise CliInputError("INVALID_SELECTION_TARGET", "大纲选区只能指向大纲正文")
    if resource_type == "chapter_content" and raw["resourceId"] != chapter_id:
        raise CliInputError("INVALID_SELECTION_TARGET", "章节选区 resourceId 必须等于 chapterId")
    for name in ("baseContentHash", "selectedTextHash"):
        value = raw.get(name)
        if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
            raise CliInputError("INVALID_SELECTION_TARGET", f"{name} 必须是 64 位小写 SHA-256")
    start = raw.get("selectionStart")
    end = raw.get("selectionEnd")
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise CliInputError("INVALID_SELECTION_TARGET", "选区必须是非空的正向码点范围")
    return raw


def _task_path(payload: JsonObject) -> str:
    return quote(_require_string(payload, "taskId"), safe="")


def start_agent(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    if "inputMode" in payload:
        return _start_natural(runtime, payload)
    _reject_unexpected_fields(payload, _START_FIELDS)
    client_request_id = _require_client_request_id(payload)
    novel_id = _require_string(payload, "novelId")
    chapter_id = _require_string(payload, "chapterId")
    operation = _require_string(payload, "operation")
    if operation not in _OPERATIONS:
        raise CliInputError(
            "INVALID_OPERATION",
            "operation 只能是 answer_question、plan_chapter、write_chapter、"
            "review_chapter、rewrite_scene、rewrite_chapter_selection、rewrite_outline_selection、"
            "create_lore、revise_lore、create_outline、revise_outline 或 manage_foreshadowing",
        )

    target = payload.get("target")
    if (
        not isinstance(target, dict)
        or target.get("type") != "chapter"
        or target.get("id") != chapter_id
    ):
        raise CliInputError(
            "INVALID_TARGET",
            "target 必须指向 chapterId 对应章节",
        )
    selection_target = _require_selection_target(
        payload,
        operation=operation,
        chapter_id=chapter_id,
    )
    scope = payload.get("scope")
    structured = operation in {
        "create_lore", "revise_lore", "create_outline", "revise_outline", "manage_foreshadowing",
    }
    if structured:
        _validate_structured_scope(scope, operation, chapter_id)
    if not structured and operation != "rewrite_outline_selection" and (
        not isinstance(scope, dict)
        or scope.get("kind") != "chapter"
        or scope.get("chapterId") != chapter_id
    ):
        raise CliInputError(
            "INVALID_SCOPE",
            "scope 必须是 chapterId 对应章节范围",
        )

    if operation == "rewrite_outline_selection":
        if not isinstance(scope, dict) or selection_target is None:
            raise CliInputError("INVALID_SCOPE", "大纲选区 scope 无效")
        expected_kind = (
            "novel"
            if selection_target["resourceType"] == "outline_content"
            else "outline_node"
        )
        if scope.get("kind") != expected_kind:
            raise CliInputError("INVALID_SCOPE", "大纲选区 scope 必须匹配资源身份")
        if (
            expected_kind == "outline_node"
            and scope.get("outlineNodeId") != selection_target["resourceId"]
        ):
            raise CliInputError(
                "INVALID_SCOPE",
                "outlineNodeId 必须匹配 selectionTarget.resourceId",
            )

    user_instruction = _require_string(payload, "userInstruction")
    if not user_instruction.strip():
        raise CliInputError("INVALID_USER_INSTRUCTION", "userInstruction 不能为空白")

    writing_session_id = payload.get("writingSessionId")
    if operation == "answer_question" and (
        not isinstance(writing_session_id, str) or not writing_session_id
    ):
        raise CliInputError(
            "WRITING_SESSION_REQUIRED",
            "answer_question 必须提供 writingSessionId",
        )
    if "writingSessionId" in payload:
        _optional_string(payload, "writingSessionId")

    body: JsonObject = {
        "clientRequestId": client_request_id,
        "workflow": "long_serial",
        "novelId": novel_id,
        "chapterId": chapter_id,
        "operation": operation,
        "target": target,
        "scope": scope,
        "userInstruction": user_instruction,
    }
    if selection_target is not None:
        body["selectionTarget"] = selection_target
    for name in ("writingSessionId", "targetWordCount"):
        if name in payload:
            body[name] = payload[name]

    response = runtime.require_api().request(
        "POST",
        "/api/v1/writing/runs",
        json=body,
    )
    return ensure_command_json_result(response)


def _validate_structured_scope(scope: JsonValue, operation: str, chapter_id: str) -> None:
    if not isinstance(scope, dict):
        raise CliInputError("INVALID_SCOPE", "scope 必须是 JSON 对象")
    kind = scope.get("kind")
    if kind == "novel":
        return
    if operation == "revise_outline" and kind == "outline_node":
        node_id = scope.get("outlineNodeId")
        if isinstance(node_id, str) and node_id:
            return
    if (operation == "manage_foreshadowing" and kind == "chapter"
            and scope.get("chapterId") == chapter_id):
        return
    raise CliInputError("INVALID_SCOPE", "scope 不符合当前结构化操作的范围要求")


def resume_task(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    if "inputMode" in payload:
        return _clarify_task(runtime, payload)
    _reject_unexpected_fields(payload, _RESUME_FIELDS)
    body: JsonObject = {"clientRequestId": _require_client_request_id(payload)}
    if "writingSessionId" in payload:
        body["writingSessionId"] = payload["writingSessionId"]
        _optional_string(body, "writingSessionId")
    if "userMessage" in payload:
        user_message: JsonValue = payload["userMessage"]
        if user_message is not None and not isinstance(user_message, str):
            raise CliInputError(
                "INVALID_FIELD",
                "userMessage 必须是字符串或 null",
            )
        body["userMessage"] = user_message

    response = runtime.require_api().request(
        "POST",
        f"/api/v1/writing/runs/{_task_path(payload)}/resume",
        json=body,
    )
    return ensure_command_json_result(response)


def _complete_message(payload: JsonObject, field: str) -> str:
    value = _require_string(payload, field)
    if not has_complete_text(value):
        raise CliInputError("INVALID_USER_INSTRUCTION", f"{field} 不能为空白")
    return value


def _start_natural(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    if payload.get("inputMode") != "natural":
        raise CliInputError("INVALID_INPUT_MODE", "自然启动的 inputMode 必须是 natural")
    _reject_unexpected_fields(payload, {
        "profile", "inputMode", "clientRequestId", "novelId", "chapterId",
        "writingSessionId", "userInstruction", "targetWordCount",
    })
    body: JsonObject = {
        "inputMode": "natural", "workflow": "long_serial",
        "clientRequestId": _require_client_request_id(payload),
        "novelId": _require_string(payload, "novelId"),
        "chapterId": _require_string(payload, "chapterId"),
        "writingSessionId": _require_string(payload, "writingSessionId"),
        "userInstruction": _complete_message(payload, "userInstruction"),
    }
    if "targetWordCount" in payload:
        count = payload["targetWordCount"]
        if type(count) is not int or not 1 <= count <= 10_000_000:
            raise CliInputError(
                "INVALID_TARGET_WORD_COUNT", "targetWordCount 必须是 1..10000000 整数"
            )
        body["targetWordCount"] = count
    return ensure_command_json_result(runtime.require_api().request(
        "POST", "/api/v1/writing/runs", json=body,
    ))


def _clarify_task(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    if payload.get("inputMode") != "clarification":
        raise CliInputError("INVALID_INPUT_MODE", "澄清回答的 inputMode 必须是 clarification")
    _reject_unexpected_fields(payload, {
        "profile", "inputMode", "taskId", "clientRequestId", "expectedRevision",
        "decisionStepId", "userMessage",
    })
    revision = payload.get("expectedRevision")
    if type(revision) is not int or revision <= 0:
        raise CliInputError("INVALID_REVISION", "expectedRevision 必须是正整数")
    body: JsonObject = {
        "clientRequestId": _require_client_request_id(payload), "expectedRevision": revision,
        "decisionStepId": _require_string(payload, "decisionStepId"),
        "userMessage": _complete_message(payload, "userMessage"),
    }
    return ensure_command_json_result(runtime.require_api().request(
        "POST", f"/api/v1/writing/runs/{_task_path(payload)}/clarification", json=body,
    ))


def cancel_task(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    _reject_unexpected_fields(payload, _CANCEL_FIELDS)
    body: JsonObject = {"clientRequestId": _require_client_request_id(payload)}
    response = runtime.require_api().request(
        "POST",
        f"/api/v1/writing/runs/{_task_path(payload)}/cancel",
        json=body,
    )
    return ensure_command_json_result(response)


_NO_FILE = FileOutputSpec(kind="none")

TASK_MUTATION_COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="long.agent.start",
        handler=start_agent,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.task.resume",
        handler=resume_task,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
    CommandSpec(
        name="long.task.cancel",
        handler=cancel_task,
        inputMode="json",
        outputMode="json",
        fileOutput=_NO_FILE,
        mutation=True,
        requiresIdentity=True,
        requiresClientRequestId=True,
    ),
)

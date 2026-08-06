from __future__ import annotations

from urllib.parse import quote

from ...json_types import JsonObject, JsonValue
from ...registry import CommandSpec, FileOutputSpec
from ...runtime import CliInputError, CliRuntime, ensure_command_json_result

_OPERATIONS = {"plan_chapter", "write_chapter", "review_chapter"}
_START_FIELDS = {
    "profile",
    "clientRequestId",
    "novelId",
    "chapterId",
    "writingSessionId",
    "operation",
    "target",
    "scope",
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


def _task_path(payload: JsonObject) -> str:
    return quote(_require_string(payload, "taskId"), safe="")


def start_agent(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    _reject_unexpected_fields(payload, _START_FIELDS)
    client_request_id = _require_client_request_id(payload)
    novel_id = _require_string(payload, "novelId")
    chapter_id = _require_string(payload, "chapterId")
    operation = _require_string(payload, "operation")
    if operation not in _OPERATIONS:
        raise CliInputError(
            "INVALID_OPERATION",
            "operation 只能是 plan_chapter、write_chapter 或 review_chapter",
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
    scope = payload.get("scope")
    if (
        not isinstance(scope, dict)
        or scope.get("kind") != "chapter"
        or scope.get("chapterId") != chapter_id
    ):
        raise CliInputError(
            "INVALID_SCOPE",
            "scope 必须是 chapterId 对应章节范围",
        )

    user_instruction = _require_string(payload, "userInstruction")
    if not user_instruction.strip():
        raise CliInputError("INVALID_USER_INSTRUCTION", "userInstruction 不能为空白")

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
    for name in ("writingSessionId", "targetWordCount"):
        if name in payload:
            body[name] = payload[name]
    if "writingSessionId" in body:
        _optional_string(body, "writingSessionId")

    response = runtime.require_api().request(
        "POST",
        "/api/v1/writing/runs",
        json=body,
    )
    return ensure_command_json_result(response)


def resume_task(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
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

from __future__ import annotations

import pytest
from inkforge_contracts import ToolCallRequest, ToolCallResult
from pydantic import BaseModel, ValidationError


def valid_tool_call_request() -> dict[str, object]:
    return {
        "protocolVersion": "1.0",
        "callId": "call-1",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "agentId": "写作",
        "toolName": "read_chapter",
        "arguments": {"chapterId": "chapter-1", "includeDraft": False},
    }


def test_valid_tool_call_request_preserves_camel_case() -> None:
    request = ToolCallRequest.model_validate(valid_tool_call_request())

    assert request.model_dump(mode="json") == valid_tool_call_request()


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (ToolCallRequest, valid_tool_call_request()),
        (
            ToolCallResult,
            {
                "protocolVersion": "1.0",
                "callId": "call-1",
                "runId": "run-1",
                "taskId": "task-1",
                "success": True,
                "result": {"content": "正文"},
                "error": None,
            },
        ),
    ],
)
def test_tool_models_reject_unknown_fields(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    payload["unknownField"] = True

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocolVersion", "2.0"),
        ("agentId", "策划"),
        ("callId", "  "),
        ("runId", "\t"),
        ("taskId", "\n"),
        ("novelId", "   "),
        ("toolName", "  "),
    ],
)
def test_tool_call_request_rejects_invalid_values(field: str, value: object) -> None:
    payload = valid_tool_call_request()
    payload[field] = value

    with pytest.raises(ValidationError):
        ToolCallRequest.model_validate(payload)


def test_tool_call_request_rejects_non_json_arguments() -> None:
    payload = valid_tool_call_request()
    payload["arguments"] = {"value": object()}

    with pytest.raises(ValidationError):
        ToolCallRequest.model_validate(payload)


def test_successful_tool_result_requires_empty_error() -> None:
    with pytest.raises(ValidationError):
        ToolCallResult(
            protocolVersion="1.0",
            callId="call-1",
            runId="run-1",
            taskId="task-1",
            success=True,
            result={"content": "正文"},
            error="不应存在错误",
        )


@pytest.mark.parametrize("error", [None, "", "   "])
def test_failed_tool_result_requires_non_blank_error(error: str | None) -> None:
    with pytest.raises(ValidationError):
        ToolCallResult(
            protocolVersion="1.0",
            callId="call-1",
            runId="run-1",
            taskId="task-1",
            success=False,
            result={"diagnostic": "超时"},
            error=error,
        )


def test_failed_tool_result_allows_structured_diagnostic_result() -> None:
    result = ToolCallResult(
        protocolVersion="1.0",
        callId="call-1",
        runId="run-1",
        taskId="task-1",
        success=False,
        result={"diagnostic": {"provider": "DeepSeek", "retryAfter": 3}},
        error="模型调用失败",
    )

    assert result.result == {"diagnostic": {"provider": "DeepSeek", "retryAfter": 3}}

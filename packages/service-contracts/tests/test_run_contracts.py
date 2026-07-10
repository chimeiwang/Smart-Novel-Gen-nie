from __future__ import annotations

import json
from typing import Literal, get_args

import pytest
from inkforge_contracts import (
    PROTOCOL_VERSION,
    CoreAgentId,
    CreativeOperationKind,
    RunAccepted,
    RunRequest,
    RunStatusResponse,
)
from pydantic import BaseModel, ValidationError


def valid_run_request() -> dict[str, object]:
    return {
        "protocolVersion": "1.0",
        "runId": "run-1",
        "taskId": "task-1",
        "novelId": "novel-1",
        "userId": "user-1",
        "operation": "write_chapter",
    }


def test_protocol_version_and_literal_sets_are_exact() -> None:
    assert PROTOCOL_VERSION == "1.0"
    assert set(get_args(CoreAgentId)) == {"设定", "剧情", "写作", "校验", "编辑"}
    assert set(get_args(CreativeOperationKind)) == {
        "answer_question",
        "create_lore",
        "revise_lore",
        "create_outline",
        "revise_outline",
        "plan_chapter",
        "write_chapter",
        "rewrite_scene",
        "review_chapter",
        "sync_lore",
        "manage_foreshadowing",
    }


def test_run_status_set_is_exact() -> None:
    status_annotation = RunStatusResponse.model_fields["status"].annotation

    assert set(get_args(status_annotation)) == {
        "queued",
        "running",
        "awaiting_user",
        "completed",
        "failed",
        "cancelled",
    }


def test_valid_run_request_preserves_camel_case_contract() -> None:
    request = RunRequest.model_validate(valid_run_request())

    assert request.resume is False
    assert request.model_dump() == {**valid_run_request(), "resume": False}
    json.dumps(request.model_dump(mode="json"), ensure_ascii=False)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("protocolVersion", "2.0"),
        ("operation", "unknown_operation"),
        ("runId", "   "),
        ("taskId", "\t"),
        ("novelId", "\n"),
        ("userId", "  "),
    ],
)
def test_run_request_rejects_invalid_fixed_values_and_blank_ids(
    field: str, value: object
) -> None:
    payload = valid_run_request()
    payload[field] = value

    with pytest.raises(ValidationError):
        RunRequest.model_validate(payload)


def test_run_request_strips_identifier_whitespace() -> None:
    payload = valid_run_request()
    payload["runId"] = "  run-1  "

    request = RunRequest.model_validate(payload)

    assert request.runId == "run-1"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (RunRequest, valid_run_request()),
        (
            RunAccepted,
            {
                "protocolVersion": "1.0",
                "runId": "run-1",
                "taskId": "task-1",
                "status": "accepted",
            },
        ),
        (
            RunStatusResponse,
            {
                "protocolVersion": "1.0",
                "runId": "run-1",
                "taskId": "task-1",
                "status": "running",
                "lastSequence": 0,
                "error": None,
            },
        ),
    ],
)
def test_run_models_reject_unknown_fields(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    payload["unknownField"] = True

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("status", ["accepted", "queued"])
def test_run_accepted_accepts_only_declared_statuses(
    status: Literal["accepted", "queued"],
) -> None:
    accepted = RunAccepted(
        protocolVersion="1.0",
        runId="run-1",
        taskId="task-1",
        status=status,
    )

    assert accepted.status == status


def test_run_status_rejects_negative_last_sequence() -> None:
    with pytest.raises(ValidationError):
        RunStatusResponse(
            protocolVersion="1.0",
            runId="run-1",
            taskId="task-1",
            status="failed",
            lastSequence=-1,
            error="执行失败",
        )

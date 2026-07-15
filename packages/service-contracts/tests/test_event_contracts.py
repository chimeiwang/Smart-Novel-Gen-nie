from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from inkforge_contracts import (
    AgentEvent,
    CheckpointCallback,
    RunCompletionCallback,
    RunFailureCallback,
)
from pydantic import BaseModel, ValidationError

OCCURRED_AT = datetime(2026, 7, 10, 8, 30, tzinfo=UTC)


def valid_event_payload() -> dict[str, object]:
    return {
        "protocolVersion": "1.1",
        "eventId": "event-1",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "sequence": 1,
        "event": "agent_started",
        "data": {"agentId": "写作", "attempt": 1},
        "occurredAt": OCCURRED_AT,
    }


def test_valid_agent_event_is_json_serializable_and_preserves_camel_case() -> None:
    event = AgentEvent.model_validate(valid_event_payload())

    dumped = event.model_dump(mode="json")
    assert dumped["protocolVersion"] == "1.1"
    assert dumped["eventId"] == "event-1"
    assert dumped["jobId"] == "job-1"
    assert dumped["occurredAt"] == "2026-07-10T08:30:00Z"
    json.dumps(dumped, ensure_ascii=False)


def test_agent_event_supports_json_round_trip() -> None:
    event = AgentEvent.model_validate(valid_event_payload())
    serialized = event.model_dump_json()

    assert AgentEvent.model_validate_json(serialized) == event
    assert AgentEvent.model_validate(json.loads(serialized)) == event


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AgentEvent, valid_event_payload()),
        (
            CheckpointCallback,
            {
                "protocolVersion": "1.1",
                "eventId": "event-1",
                "jobId": "job-1",
                "runId": "run-1",
                "taskId": "task-1",
                "sequence": 1,
                "checkpoint": {"phase": "running"},
                "occurredAt": OCCURRED_AT,
            },
        ),
        (
            RunCompletionCallback,
            {
                "protocolVersion": "1.1",
                "eventId": "event-1",
                "jobId": "job-1",
                "runId": "run-1",
                "taskId": "task-1",
                "sequence": 1,
                "result": {"artifactId": "artifact-1"},
                "occurredAt": OCCURRED_AT,
            },
        ),
        (
            RunFailureCallback,
            {
                "protocolVersion": "1.1",
                "eventId": "event-1",
                "jobId": "job-1",
                "runId": "run-1",
                "taskId": "task-1",
                "sequence": 1,
                "code": "MODEL_TIMEOUT",
                "message": "模型调用超时",
                "recoverable": True,
                "occurredAt": OCCURRED_AT,
            },
        ),
    ],
)
def test_event_models_reject_unknown_fields(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    payload["unknownField"] = True

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AgentEvent, valid_event_payload()),
        (
            CheckpointCallback,
            {
                "protocolVersion": "1.1",
                "eventId": "event-1",
                "jobId": "job-1",
                "runId": "run-1",
                "taskId": "task-1",
                "sequence": 1,
                "checkpoint": {"phase": "running"},
                "occurredAt": OCCURRED_AT,
            },
        ),
        (
            RunCompletionCallback,
            {
                "protocolVersion": "1.1",
                "eventId": "event-1",
                "jobId": "job-1",
                "runId": "run-1",
                "taskId": "task-1",
                "sequence": 1,
                "result": {},
                "occurredAt": OCCURRED_AT,
            },
        ),
        (
            RunFailureCallback,
            {
                "protocolVersion": "1.1",
                "eventId": "event-1",
                "jobId": "job-1",
                "runId": "run-1",
                "taskId": "task-1",
                "sequence": 1,
                "code": "FAILED",
                "message": "执行失败",
                "recoverable": False,
                "occurredAt": OCCURRED_AT,
            },
        ),
    ],
)
def test_event_models_require_job_id_and_protocol_1_1(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    validated = model.model_validate(payload)

    assert validated.protocolVersion == "1.1"
    assert validated.jobId == "job-1"

    missing_job_id = dict(payload)
    missing_job_id.pop("jobId")
    with pytest.raises(ValidationError):
        model.model_validate(missing_job_id)

    legacy_protocol = dict(payload)
    legacy_protocol["protocolVersion"] = "1.0"
    with pytest.raises(ValidationError):
        model.model_validate(legacy_protocol)


@pytest.mark.parametrize("sequence", [0, -1])
def test_agent_event_rejects_non_positive_sequence(sequence: int) -> None:
    payload = valid_event_payload()
    payload["sequence"] = sequence

    with pytest.raises(ValidationError):
        AgentEvent.model_validate(payload)


def test_agent_event_rejects_naive_datetime() -> None:
    payload = valid_event_payload()
    payload["occurredAt"] = datetime(2026, 7, 10, 8, 30)

    with pytest.raises(ValidationError):
        AgentEvent.model_validate(payload)


def test_agent_event_rejects_non_json_data() -> None:
    payload = valid_event_payload()
    payload["data"] = {"value": object()}

    with pytest.raises(ValidationError):
        AgentEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("eventId", "  "),
        ("runId", "\t"),
        ("taskId", "\n"),
        ("event", "   "),
    ],
)
def test_agent_event_rejects_blank_identifiers_and_event(field: str, value: object) -> None:
    payload = valid_event_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        AgentEvent.model_validate(payload)


@pytest.mark.parametrize("model", [CheckpointCallback, RunCompletionCallback, RunFailureCallback])
def test_callbacks_reject_naive_datetime(model: type[BaseModel]) -> None:
    payload: dict[str, object] = {
        "protocolVersion": "1.1",
        "eventId": "event-1",
        "jobId": "job-1",
        "runId": "run-1",
        "taskId": "task-1",
        "sequence": 1,
        "occurredAt": datetime(2026, 7, 10, 8, 30),
    }
    if model is CheckpointCallback:
        payload["checkpoint"] = {}
    elif model is RunCompletionCallback:
        payload["result"] = {}
    else:
        payload.update(code="FAILED", message="执行失败", recoverable=False)

    with pytest.raises(ValidationError):
        model.model_validate(payload)

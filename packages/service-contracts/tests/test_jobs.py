import hashlib

import pytest
from inkforge_contracts.jobs import AgentJobAccepted, AgentJobRequest
from pydantic import ValidationError


def valid_long_serial_payload() -> dict[str, object]:
    return {
        "version": 1,
        "workflow": "long_serial",
        "chapterId": "chapter-1",
        "writingSessionId": None,
        "operation": "write_chapter",
        "target": {"type": "chapter", "id": "chapter-1"},
        "scope": {"kind": "chapter", "chapterId": "chapter-1"},
        "sourceBindings": [
            {
                "resourceType": "chapter",
                "resourceId": "chapter-1",
                "exists": True,
                "updatedAt": "2026-08-05T10:00:00Z",
                "contentSha256": "c" * 64,
                "revision": None,
                "absenceSentinel": None,
            }
        ],
        "targetWordCount": 4_000,
        "userInstruction": "撰写本章",
        "resume": False,
        "resumeInput": None,
    }


def test_agent_job_contract_is_strict_and_resource_bound() -> None:
    value = AgentJobRequest.model_validate(
        {
            "protocolVersion": "1.0",
            "jobId": "job-1",
            "kind": "writing",
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "userId": "user-1",
            "priority": 10,
            "payload": {"resume": False},
            "force": False,
        }
    )
    assert value.jobId == "job-1"

    with pytest.raises(ValidationError):
        AgentJobRequest.model_validate({**value.model_dump(), "databaseUrl": "禁止"})


@pytest.mark.parametrize(
    "status",
    ["queued", "running", "completed", "failed", "cancelled"],
)
def test_agent_job_accepted_returns_actual_queue_status(status: str) -> None:
    accepted = AgentJobAccepted.model_validate(
        {
            "protocolVersion": "1.0",
            "jobId": "job-1",
            "runId": "run-1",
            "taskId": "task-1",
            "status": status,
        }
    )

    assert accepted.status == status


def test_agent_job_accepted_rejects_ambiguous_duplicate_status() -> None:
    with pytest.raises(ValidationError):
        AgentJobAccepted.model_validate(
            {
                "protocolVersion": "1.0",
                "jobId": "job-1",
                "runId": "run-1",
                "taskId": "task-1",
                "status": "duplicate",
            }
        )


def test_short_medium_writing_job_validates_structured_payload() -> None:
    outline_content = "不可变蓝图"
    value = AgentJobRequest.model_validate(
        {
            "protocolVersion": "1.0",
            "jobId": "job-1",
            "kind": "writing",
            "runId": "run-1",
            "taskId": "task-1",
            "novelId": "novel-1",
            "userId": "user-1",
            "priority": 10,
            "payload": {
                "workflow": "short_medium",
                "operation": "generate_manuscript",
                "documentType": "manuscript",
                "chapterId": "chapter-1",
                "sourceOutlineVersionId": "outline-version-1",
                "sourceOutlineContent": outline_content,
                "sourceOutlineContentHash": hashlib.sha256(
                    outline_content.encode("utf-8")
                ).hexdigest(),
                "targetTotalWordCount": 20_000,
            },
        }
    )

    assert value.payload["workflow"] == "short_medium"


def test_short_medium_writing_job_rejects_invalid_structured_payload() -> None:
    with pytest.raises(ValidationError):
        AgentJobRequest.model_validate(
            {
                "protocolVersion": "1.0",
                "jobId": "job-1",
                "kind": "writing",
                "runId": "run-1",
                "taskId": "task-1",
                "novelId": "novel-1",
                "userId": "user-1",
                "priority": 10,
                "payload": {
                    "workflow": "short_medium",
                    "operation": "generate_manuscript",
                    "documentType": "manuscript",
                    "chapterId": "chapter-1",
                },
            }
        )


def test_long_serial_writing_job_validates_structured_payload() -> None:
    value = AgentJobRequest.model_validate(
        {
            "protocolVersion": "1.0",
            "jobId": "job-long-1",
            "kind": "writing",
            "runId": "run-long-1",
            "taskId": "task-long-1",
            "novelId": "novel-1",
            "userId": "user-1",
            "priority": 10,
            "payload": valid_long_serial_payload(),
        }
    )

    assert value.payload["workflow"] == "long_serial"


@pytest.mark.parametrize(
    "payload",
    [
        {**valid_long_serial_payload(), "operation": "sync_lore"},
        {**valid_long_serial_payload(), "selectedAgents": ["写作"]},
        {**valid_long_serial_payload(), "sourceBindings": []},
    ],
)
def test_long_serial_writing_job_rejects_invalid_structured_payload(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AgentJobRequest.model_validate(
            {
                "protocolVersion": "1.0",
                "jobId": "job-long-1",
                "kind": "writing",
                "runId": "run-long-1",
                "taskId": "task-long-1",
                "novelId": "novel-1",
                "userId": "user-1",
                "priority": 10,
                "payload": payload,
            }
        )


def test_legacy_writing_job_without_workflow_remains_compatible() -> None:
    value = AgentJobRequest.model_validate(
        {
            "protocolVersion": "1.0",
            "jobId": "job-legacy-1",
            "kind": "writing",
            "runId": "run-legacy-1",
            "taskId": "task-legacy-1",
            "novelId": "novel-1",
            "userId": "user-1",
            "priority": 10,
            "payload": {"resume": False, "userMessage": "继续"},
        }
    )

    assert "workflow" not in value.payload


@pytest.mark.parametrize("workflow", ["long_seral", "long_form", 1, None])
def test_writing_job_rejects_present_but_unsupported_workflow(
    workflow: object,
) -> None:
    with pytest.raises(ValidationError):
        AgentJobRequest.model_validate(
            {
                "protocolVersion": "1.0",
                "jobId": "job-invalid-workflow",
                "kind": "writing",
                "runId": "run-invalid-workflow",
                "taskId": "task-invalid-workflow",
                "novelId": "novel-1",
                "userId": "user-1",
                "priority": 10,
                "payload": {"workflow": workflow, "resume": False},
            }
        )

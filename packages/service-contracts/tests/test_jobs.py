import pytest
from inkforge_contracts.jobs import AgentJobAccepted, AgentJobRequest
from pydantic import ValidationError


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

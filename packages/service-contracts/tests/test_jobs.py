import pytest
from inkforge_contracts.jobs import AgentJobRequest
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

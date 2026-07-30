import hashlib

import pytest
from inkforge_contracts import (
    ShortMediumWritingPlan,
    short_medium_writing_plan_sha256,
)
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
    outline_content = "不可变蓝图"
    outline_content_hash = hashlib.sha256(outline_content.encode("utf-8")).hexdigest()
    writing_plan = ShortMediumWritingPlan(
        version="1",
        targetTotalWordCount=20_000,
        scenes=[
            {
                "sceneId": "scene-1",
                "title": "完整故事",
                "summary": "主角完成一场完整冲突。",
            }
        ],
        writingUnits=[
            {
                "unitId": "unit-1",
                "order": 1,
                "title": "完整故事",
                "sceneIds": ["scene-1"],
                "entryState": "冲突尚未发生。",
                "requiredEvents": ["主角面对并解决冲突"],
                "exitState": "冲突已经解决。",
                "targetWordCount": 20_000,
            }
        ],
    )
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
                "sourceOutlineContentHash": outline_content_hash,
                "targetTotalWordCount": 20_000,
                "writingPlan": writing_plan.model_dump(mode="json"),
                "writingPlanHash": short_medium_writing_plan_sha256(
                    outline_content_hash,
                    writing_plan,
                ),
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

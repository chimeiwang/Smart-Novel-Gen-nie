from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from inkforge_agents.jobs.quality import QualityJobHandler
from inkforge_agents.queue.repository import QueueJob


class Core:
    def __init__(self) -> None:
        self.result: dict[str, Any] | None = None

    async def get_quality_context(
        self,
        resource: object,
        check_id: str,
        source_task_id: str | None,
        message: str | None,
    ) -> dict[str, Any]:
        del resource
        assert check_id == "check-1"
        assert source_task_id is None
        assert message == "检查一致性"
        return {"chapterContent": "完整章节正文", "message": "检查一致性"}

    async def complete_quality(
        self, resource: object, check_id: str, result: dict[str, Any]
    ) -> None:
        del resource, check_id
        self.result = result

    async def fail_quality(self, *args: object, **kwargs: object) -> None:
        raise AssertionError((args, kwargs))


class Runner:
    def __init__(self, workflow_log: WorkflowLog) -> None:
        self._workflow_log = workflow_log
        self.requests: list[Any] = []

    async def run(self, request: object):
        self.requests.append(request)
        assert self._workflow_log.entries[0][0] == "开始"

        class Result:
            visibleContent = "一致性良好"
            controlEvents = [
                {
                    "type": "submit_quality_report",
                    "scores": {"overall": 9, "pacing": 8},
                    "qualityGate": "pass",
                    "rewriteBrief": None,
                }
            ]

        return Result()


class WorkflowLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, object]] = []

    def start_run(self, **metadata: object) -> None:
        self.entries.append(("开始", metadata))

    def finish_run(self, run_id: str, status: str) -> None:
        self.entries.append(("结束", (run_id, status)))


@pytest.mark.asyncio
async def test_quality_job_requires_structured_report_and_returns_visible_result() -> None:
    core = Core()
    workflow_log = WorkflowLog()
    runner = Runner(workflow_log)
    handler = QualityJobHandler(core, runner, workflow_log=workflow_log)
    job = QueueJob(
        jobId="quality-check-1",
        kind="quality",
        runId="quality-check-1",
        taskId="check-1",
        novelId="novel-1",
        userId="user-1",
        priority=5,
        payload={"checkId": "check-1", "sourceTaskId": None, "message": "检查一致性"},
        createdAt=datetime.now(UTC),
    )

    await handler(job)

    assert runner.requests[0].agentId == "编辑"
    assert runner.requests[0].executionMode == "quality"
    assert runner.requests[0].operationKind is None
    assert runner.requests[0].toolContext.agentId == "编辑"

    assert core.result == {
        "result": "一致性良好",
        "scores": {"overall": 9, "pacing": 8},
        "qualityGate": "pass",
        "rewriteBrief": None,
    }
    assert workflow_log.entries == [
        (
            "开始",
            {
                "run_id": "quality-check-1",
                "task_id": "check-1",
                "run_kind": "质量检查",
                "user_id": "user-1",
                "novel_id": "novel-1",
                "chapter_id": None,
            },
        ),
        ("结束", ("quality-check-1", "完成")),
    ]

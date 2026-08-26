from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import fakeredis.aioredis
import pytest
from inkforge_agents.jobs.quality import QualityJobHandler
from inkforge_agents.providers.base import (
    ModelToolCall,
    ModelTurnRequest,
    ModelTurnResult,
    ModelUsage,
)
from inkforge_agents.queue.cancellation import RedisRunCancellation
from inkforge_agents.queue.consumer import NonRetryableJobError
from inkforge_agents.queue.repository import QueueJob, RedisRunQueue
from inkforge_agents.runtime.agent_runner import AgentRunner
from inkforge_agents.runtime.agent_runtime import AgentRuntime
from inkforge_agents.runtime.execution import QUALITY_AGENT_ID
from inkforge_agents.runtime.model_runtime import ModelRuntime
from inkforge_agents.tools.registry import build_default_registry


def quality_report() -> dict[str, Any]:
    return {
        "scores": {
            "characterConsistency": 81.0,
            "worldRuleConsistency": 82.0,
            "timelineConsistency": 83.0,
            "causalityConsistency": 84.0,
            "foreshadowingConsistency": 88.0,
        },
        "qualityGate": "pass",
        "issues": [],
        "report": "完整一致性报告",
        "rewriteBrief": None,
    }


def quality_job() -> QueueJob:
    return QueueJob(
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


class Core:
    def __init__(self) -> None:
        self.result: dict[str, Any] | None = None
        self.failure: str | None = None

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

    async def fail_quality(
        self,
        resource: object,
        check_id: str,
        message: str,
    ) -> None:
        del resource
        assert check_id == "check-1"
        self.failure = message


class Runner:
    def __init__(self, workflow_log: WorkflowLog) -> None:
        self._workflow_log = workflow_log
        self.requests: list[Any] = []

    async def run(self, request: object):
        self.requests.append(request)
        assert self._workflow_log.entries[0][0] == "开始"

        class Result:
            visibleContent = "这段可见正文不能作为报告"
            controlEvents = [
                {
                    "type": "submit_quality_report",
                    **quality_report(),
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


class TerminalQualityProvider:
    billable = False

    def __init__(self) -> None:
        self.calls = 0

    async def complete_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        self.calls += 1
        assert {tool.name for tool in request.tools} == {"submit_quality_report"}
        return ModelTurnResult(
            content="",
            toolCalls=[
                ModelToolCall(
                    id="quality-report-1",
                    name="submit_quality_report",
                    arguments=quality_report(),
                )
            ],
            finishReason="tool_calls",
            rawFinishReason="tool_calls",
            usage=ModelUsage(
                promptTokens=1,
                cachedTokens=0,
                completionTokens=1,
                totalTokens=2,
            ),
        )


@pytest.mark.asyncio
async def test_quality_job_uses_validator_and_forwards_complete_typed_report() -> None:
    core = Core()
    workflow_log = WorkflowLog()
    runner = Runner(workflow_log)
    handler = QualityJobHandler(core, runner, workflow_log=workflow_log)
    job = quality_job()

    await handler(job)

    assert runner.requests[0].agentId == QUALITY_AGENT_ID
    assert runner.requests[0].executionMode == "quality"
    assert runner.requests[0].operationKind is None
    assert runner.requests[0].toolContext.agentId == QUALITY_AGENT_ID
    assert runner.requests[0].toolContext.jobId == job.jobId
    assert QUALITY_AGENT_ID == "校验"

    assert core.result == quality_report()
    assert core.failure is None
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


@pytest.mark.asyncio
async def test_quality_job_binds_queue_job_id_for_runtime_cancellation_guard() -> None:
    queued_job = quality_job()
    queue = RedisRunQueue(
        fakeredis.aioredis.FakeRedis(),
        prefix="test:quality-job-id",
    )
    assert await queue.enqueue(queued_job) is True
    provider = TerminalQualityProvider()
    registry = build_default_registry()
    runner = AgentRunner(
        AgentRuntime(
            ModelRuntime(provider),
            registry,
            max_output_tokens=16_384,
            cancellation=RedisRunCancellation(queue),
        ),
        registry,
    )
    core = Core()

    await QualityJobHandler(core, runner)(queued_job)

    assert provider.calls == 1
    assert core.result == quality_report()
    assert core.failure is None


@pytest.mark.asyncio
async def test_quality_job_converges_explicit_non_retryable_failure() -> None:
    class ExpectedFailure(RuntimeError):
        retryable = False

    class FailingRunner:
        async def run(self, request: object) -> None:
            del request
            raise ExpectedFailure("模型授权被业务规则拒绝")

    core = Core()
    workflow_log = WorkflowLog()

    with pytest.raises(NonRetryableJobError):
        await QualityJobHandler(
            core,
            FailingRunner(),
            workflow_log=workflow_log,
        )(quality_job())

    assert core.failure == "质量检查运行失败"
    assert workflow_log.entries[-1] == ("结束", ("quality-check-1", "错误"))


@pytest.mark.asyncio
async def test_quality_job_leaves_explicit_retryable_failure_for_queue_retry() -> None:
    class RetryableFailure(RuntimeError):
        retryable = True

    failure = RetryableFailure("计费服务暂时不可用")

    class FailingRunner:
        async def run(self, request: object) -> None:
            del request
            raise failure

    core = Core()
    workflow_log = WorkflowLog()

    with pytest.raises(RetryableFailure) as caught:
        await QualityJobHandler(
            core,
            FailingRunner(),
            workflow_log=workflow_log,
        )(quality_job())

    assert caught.value is failure
    assert core.failure is None
    assert workflow_log.entries[-1] == (
        "结束",
        ("quality-check-1", "等待重试"),
    )

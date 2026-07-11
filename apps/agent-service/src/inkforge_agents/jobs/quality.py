from __future__ import annotations

import json
from typing import Any, Protocol, cast

from ..clients.core import RunResource
from ..queue.repository import QueueJob
from ..runtime.agent_runner import AgentRunner, AgentRunRequest
from ..tools.registry import ToolContext


class QualityCorePort(Protocol):
    async def get_quality_context(
        self,
        resource: RunResource,
        check_id: str,
        source_task_id: str | None,
        message: str | None,
    ) -> dict[str, Any]: ...

    async def complete_quality(
        self,
        resource: RunResource,
        check_id: str,
        result: dict[str, Any],
    ) -> None: ...

    async def fail_quality(
        self,
        resource: RunResource,
        check_id: str,
        message: str,
    ) -> None: ...


class RunnerPort(Protocol):
    async def run(self, request: AgentRunRequest) -> Any: ...


class QualityJobHandler:
    def __init__(self, core: QualityCorePort, runner: RunnerPort | AgentRunner) -> None:
        self._core = core
        self._runner = runner

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "quality":
            raise ValueError("质量检查处理器收到错误任务类型")
        check_id = job.payload.get("checkId")
        if not isinstance(check_id, str) or not check_id:
            raise ValueError("质量检查任务缺少检查标识")
        resource = RunResource(
            userId=job.userId,
            novelId=job.novelId,
            taskId=job.taskId,
            runId=job.runId,
        )
        source_task_id = job.payload.get("sourceTaskId")
        requested_message = job.payload.get("message")
        context = await self._core.get_quality_context(
            resource,
            check_id,
            source_task_id if isinstance(source_task_id, str) else None,
            requested_message if isinstance(requested_message, str) else None,
        )
        message = context.get("message") or job.payload.get("message") or "检查本章一致性"
        if not isinstance(message, str):
            raise ValueError("质量检查请求无效")
        try:
            result = await self._runner.run(
                AgentRunRequest(
                    agentId="编辑",
                    userMessage=message,
                    contextMessages=[
                        "质量检查完整上下文："
                        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
                    ],
                    conversationMessages=[],
                    toolContext=ToolContext(
                        userId=job.userId,
                        novelId=job.novelId,
                        taskId=job.taskId,
                        runId=job.runId,
                        agentId="编辑",
                    ),
                )
            )
            events = cast(list[dict[str, Any]], result.controlEvents)
            report = next(
                (event for event in events if event.get("type") == "submit_quality_report"),
                None,
            )
            if report is None:
                raise RuntimeError("编辑智能体未提交结构化质量报告")
            await self._core.complete_quality(
                resource,
                check_id,
                {
                    "result": str(result.visibleContent),
                    "scores": report.get("scores", {}),
                    "qualityGate": report["qualityGate"],
                    "rewriteBrief": report.get("rewriteBrief"),
                },
            )
        except Exception as exc:
            await self._core.fail_quality(resource, check_id, str(exc))
            raise

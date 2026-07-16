from __future__ import annotations

import json
from typing import Any, Protocol, cast

from ..clients.core import RunResource
from ..queue.repository import QueueJob
from ..runtime.agent_runner import AgentRunner, AgentRunRequest
from ..runtime.execution import QUALITY_AGENT_ID
from ..tools.registry import ToolContext
from .workflow_log import WorkflowLogPort


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
    def __init__(
        self,
        core: QualityCorePort,
        runner: RunnerPort | AgentRunner,
        *,
        workflow_log: WorkflowLogPort | None = None,
    ) -> None:
        self._core = core
        self._runner = runner
        self._workflow_log = workflow_log

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
        if self._workflow_log is not None:
            self._workflow_log.start_run(
                run_id=job.runId,
                task_id=job.taskId,
                run_kind="质量检查",
                user_id=job.userId,
                novel_id=job.novelId,
                chapter_id=None,
            )
        try:
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
            result = await self._runner.run(
                AgentRunRequest(
                    agentId=QUALITY_AGENT_ID,
                    executionMode="quality",
                    operationKind=None,
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
                        agentId=QUALITY_AGENT_ID,
                    ),
                )
            )
            events = cast(list[dict[str, Any]], result.controlEvents)
            report = next(
                (event for event in events if event.get("type") == "submit_quality_report"),
                None,
            )
            if report is None:
                raise RuntimeError(f"{QUALITY_AGENT_ID}智能体未提交结构化质量报告")
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
            try:
                await self._core.fail_quality(resource, check_id, str(exc))
            finally:
                self._finish_log(job.runId, "错误")
            raise
        self._finish_log(job.runId, "完成")

    def _finish_log(self, run_id: str, status: str) -> None:
        if self._workflow_log is not None:
            self._workflow_log.finish_run(run_id, status)

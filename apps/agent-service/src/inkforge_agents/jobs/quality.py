from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol, cast

from ..clients.core import RunResource
from ..queue.consumer import NonRetryableJobError
from ..queue.repository import QueueJob
from ..runtime.agent_runner import AgentRunner, AgentRunRequest
from ..runtime.execution import QUALITY_AGENT_ID
from ..tools.control import QualityReportArgs
from ..tools.registry import ToolContext
from .workflow_log import WorkflowLogPort

logger = logging.getLogger(__name__)


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
                        jobId=job.jobId,
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
            validated_report = QualityReportArgs.model_validate(
                {key: value for key, value in report.items() if key != "type"}
            )
            await self._core.complete_quality(
                resource,
                check_id,
                validated_report.model_dump(),
            )
        except Exception as exc:
            retryable = _retry_decision(exc)
            if retryable is True:
                _log_failure(job, check_id, exc, phase="run", retryable=True)
                self._finish_log(job.runId, "等待重试")
                raise
            try:
                # Core 只保存稳定失败状态，不需要也不应接收可能包含第三方正文的异常消息。
                await self._core.fail_quality(resource, check_id, "质量检查运行失败")
            except Exception as callback_error:
                callback_retryable = _retry_decision(callback_error)
                _log_failure(
                    job,
                    check_id,
                    callback_error,
                    phase="failure_callback",
                    retryable=callback_retryable,
                )
                self._finish_log(
                    job.runId,
                    "等待重试" if callback_retryable is True else "错误",
                )
                raise
            else:
                self._finish_log(job.runId, "错误")
            _log_failure(job, check_id, exc, phase="run", retryable=retryable)
            if retryable is False:
                raise NonRetryableJobError("质量检查运行失败已上报核心服务") from exc
            # 未声明重试语义的异常仍应触发消费者监督器，不能被业务失败回调静默吞掉。
            raise
        self._finish_log(job.runId, "完成")

    def _finish_log(self, run_id: str, status: str) -> None:
        if self._workflow_log is not None:
            self._workflow_log.finish_run(run_id, status)


def _retry_decision(error: Exception) -> bool | None:
    retryable = getattr(error, "retryable", None)
    if isinstance(retryable, bool):
        return retryable
    recoverable = getattr(error, "recoverable", None)
    return recoverable if isinstance(recoverable, bool) else None


def _safe_failure_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code):
        return code
    value = type(error).__name__
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value) else "UnknownError"


def _log_failure(
    job: QueueJob,
    check_id: str,
    error: Exception,
    *,
    phase: str,
    retryable: bool | None,
) -> None:
    # 默认 Uvicorn 格式不展示 LogRecord.extra，因此把同一组脱敏分类直接放入消息；
    # 禁止输出 str(error)。
    logger.warning(
        "质量检查任务失败 job_id=%s task_id=%s run_id=%s check_id=%s phase=%s "
        "failure_code=%s exception_type=%s retryable=%s",
        job.jobId,
        job.taskId,
        job.runId,
        check_id,
        phase,
        _safe_failure_code(error),
        type(error).__name__,
        retryable,
    )

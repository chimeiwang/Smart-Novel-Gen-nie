from __future__ import annotations

import json
from typing import Any, Protocol, cast

from pydantic import JsonValue

from ..clients.core import RunResource
from ..graph.snapshots import deserialize_snapshot, serialize_snapshot, to_typescript_snapshot
from ..graph.state import GraphState, create_initial_state
from ..queue.consumer import NonRetryableJobError
from ..queue.repository import QueueJob
from .workflow_log import WorkflowLogPort


class CoreClientPort(Protocol):
    async def call_tool(
        self,
        resource: RunResource,
        agent_id: str,
        tool_name: str,
        arguments: dict[str, JsonValue],
    ) -> dict[str, Any]: ...

    async def send_event(
        self,
        resource: RunResource,
        *,
        sequence: int,
        event: str,
        data: dict[str, Any],
    ) -> None: ...

    async def save_checkpoint(
        self,
        resource: RunResource,
        *,
        sequence: int,
        checkpoint: dict[str, Any],
    ) -> None: ...

    async def complete(
        self,
        resource: RunResource,
        *,
        sequence: int,
        result: dict[str, Any],
    ) -> None: ...

    async def fail(
        self,
        resource: RunResource,
        *,
        sequence: int,
        code: str,
        message: str,
        recoverable: bool = True,
    ) -> None: ...


class GraphPort(Protocol):
    async def ainvoke(self, value: GraphState) -> dict[str, Any]: ...


class WritingJobHandler:
    def __init__(
        self,
        core: CoreClientPort,
        *,
        parent_graph: GraphPort,
        operation_graph: GraphPort,
        workflow_log: WorkflowLogPort | None = None,
    ) -> None:
        self._core = core
        self._parent_graph = parent_graph
        self._operation_graph = operation_graph
        self._workflow_log = workflow_log

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "writing":
            raise ValueError("写作处理器收到非写作任务")
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
                run_kind="恢复运行" if job.payload.get("resume") is True else "初次运行",
                user_id=job.userId,
                novel_id=job.novelId,
                chapter_id=(
                    str(job.payload["chapterId"])
                    if isinstance(job.payload.get("chapterId"), str)
                    else None
                ),
            )
        context = await self._core.call_tool(resource, "写作", "get_writing_context", {})
        state, graph = self._prepare_state(job, context)
        self._record_state(
            job.runId,
            "准备运行",
            {"阶段": state.get("phase"), "操作阶段": state.get("operationStage")},
        )
        sequence = int(state.get("eventSequence", 0)) + 1
        await self._core.send_event(
            resource,
            sequence=sequence,
            event="agent_start",
            data={"phase": "active"},
        )
        try:
            result = await graph.ainvoke(state)
        except Exception as exc:
            self._record_state(job.runId, "运行异常", {"错误": str(exc) or "智能体运行失败"})
            self._finish_log(job.runId, "错误")
            try:
                await self._core.fail(
                    resource,
                    sequence=sequence + 1,
                    code="AGENT_RUN_FAILED",
                    message=str(exc) or "智能体运行失败",
                    recoverable=True,
                )
            finally:
                raise NonRetryableJobError("写作运行失败已上报核心服务") from exc

        stable = cast(
            GraphState,
            {key: value for key, value in result.items() if key != "__interrupt__"},
        )
        interrupt_artifact_id = _artifact_id_from_interrupt(result.get("__interrupt__"))
        if interrupt_artifact_id is not None:
            stable["activeArtifactId"] = interrupt_artifact_id
            stable["artifactStatus"] = "awaiting_user"
            stable["phase"] = "waiting_user"
            stable["operationStep"] = "await_user_decision"
            stable["operationStage"] = "等待用户决策"
        waiting_for_user = "__interrupt__" in result or stable.get("phase") == "waiting_user"
        artifact_id = stable.get("activeArtifactId")
        checkpoint_sequence = sequence + 1
        if waiting_for_user and isinstance(artifact_id, str) and artifact_id:
            active_agent = stable.get("activeAgent")
            await self._core.send_event(
                resource,
                sequence=checkpoint_sequence,
                event="artifact_awaiting_user_approval",
                data={
                    "agentId": active_agent if isinstance(active_agent, str) else "系统",
                    "artifactId": artifact_id,
                },
            )
            checkpoint_sequence += 1
        stable["eventSequence"] = checkpoint_sequence
        checkpoint = to_typescript_snapshot(serialize_snapshot(stable))
        self._record_state(
            job.runId,
            "保存稳定快照",
            {"阶段": checkpoint.get("phase"), "操作阶段": checkpoint.get("operationStage")},
        )
        await self._core.save_checkpoint(
            resource,
            sequence=checkpoint_sequence,
            checkpoint=checkpoint,
        )
        if stable.get("phase") == "error":
            message = str(stable.get("errorMessage") or "智能体运行失败")
            self._finish_log(job.runId, "错误")
            try:
                await self._core.fail(
                    resource,
                    sequence=checkpoint_sequence + 1,
                    code="AGENT_RUN_FAILED",
                    message=message,
                    recoverable=True,
                )
            finally:
                raise NonRetryableJobError("写作运行失败已上报核心服务")
        if waiting_for_user:
            self._finish_log(job.runId, "等待用户确认")
            return
        await self._core.complete(
            resource,
            sequence=sequence + 2,
            result={"finalResponse": str(stable.get("finalResponse", ""))},
        )
        self._finish_log(job.runId, "完成")

    def _record_state(self, run_id: str, node: str, changes: dict[str, Any]) -> None:
        if self._workflow_log is not None:
            self._workflow_log.record_state(run_id, node, changes)

    def _finish_log(self, run_id: str, status: str) -> None:
        if self._workflow_log is not None:
            self._workflow_log.finish_run(run_id, status)

    def _prepare_state(
        self,
        job: QueueJob,
        context: dict[str, Any],
    ) -> tuple[GraphState, GraphPort]:
        planning = context.get("planning")
        if not isinstance(planning, dict):
            raise ValueError("核心服务缺少写作规划上下文")
        snapshot = planning.get("graphState")
        is_resume = job.payload.get("resume") is True
        if is_resume:
            if not isinstance(snapshot, dict):
                raise ValueError("恢复写作任务缺少稳定快照")
            state = deserialize_snapshot(snapshot)
            resume_input = job.payload.get("resumeInput")
            if isinstance(resume_input, dict):
                state["resumeDecision"] = dict(resume_input)
                message = resume_input.get("userMessage")
                if isinstance(message, str) and message:
                    state["userMessage"] = message
            return state, self._operation_graph

        chapter_id = planning.get("chapterId")
        user_message = planning.get("userMessage")
        target_word_count = planning.get("targetWordCount", 4000)
        if not isinstance(chapter_id, str) or not chapter_id:
            raise ValueError("写作上下文缺少章节标识")
        if not isinstance(user_message, str) or not user_message:
            raise ValueError("写作上下文缺少用户请求")
        if isinstance(target_word_count, bool) or not isinstance(target_word_count, int):
            raise ValueError("写作上下文目标字数无效")
        state = create_initial_state(
            task_id=job.taskId,
            user_id=job.userId,
            novel_id=job.novelId,
            chapter_id=chapter_id,
            user_message=user_message,
            target_word_count=target_word_count,
        )
        history = planning.get("conversationHistory")
        if isinstance(history, list):
            state["conversationHistory"] = [
                dict(item) for item in history if isinstance(item, dict)
            ]
        state["contextMessages"] = [
            "核心服务权威写作上下文："
            + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        ]
        return state, self._parent_graph


def _artifact_id_from_interrupt(interrupts: object) -> str | None:
    if not isinstance(interrupts, (list, tuple)):
        return None
    for interrupt_value in interrupts:
        value = getattr(interrupt_value, "value", interrupt_value)
        if not isinstance(value, dict) or value.get("type") != "artifact_review":
            continue
        artifact_id = value.get("artifactId")
        if isinstance(artifact_id, str) and artifact_id:
            return artifact_id
    return None

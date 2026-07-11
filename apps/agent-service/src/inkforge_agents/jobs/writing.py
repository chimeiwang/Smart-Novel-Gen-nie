from __future__ import annotations

import json
from typing import Any, Protocol, cast

from pydantic import JsonValue

from ..clients.core import RunResource
from ..graph.snapshots import deserialize_snapshot, serialize_snapshot, to_typescript_snapshot
from ..graph.state import GraphState, create_initial_state
from ..queue.repository import QueueJob


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
    ) -> None:
        self._core = core
        self._parent_graph = parent_graph
        self._operation_graph = operation_graph

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "writing":
            raise ValueError("写作处理器收到非写作任务")
        resource = RunResource(
            userId=job.userId,
            novelId=job.novelId,
            taskId=job.taskId,
            runId=job.runId,
        )
        context = await self._core.call_tool(resource, "写作", "get_writing_context", {})
        state, graph = self._prepare_state(job, context)
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
            await self._core.fail(
                resource,
                sequence=sequence + 1,
                code="AGENT_RUN_FAILED",
                message=str(exc) or "智能体运行失败",
                recoverable=True,
            )
            raise

        stable = cast(
            GraphState,
            {key: value for key, value in result.items() if key != "__interrupt__"},
        )
        stable["eventSequence"] = sequence + 1
        checkpoint = to_typescript_snapshot(serialize_snapshot(stable))
        await self._core.save_checkpoint(
            resource,
            sequence=sequence + 1,
            checkpoint=checkpoint,
        )
        if checkpoint.get("phase") == "awaiting_user_review" or "__interrupt__" in result:
            return
        await self._core.complete(
            resource,
            sequence=sequence + 2,
            result={"finalResponse": str(stable.get("finalResponse", ""))},
        )

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

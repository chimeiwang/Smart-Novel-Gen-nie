from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

from inkforge_contracts.jobs import WritingJobPayload
from pydantic import JsonValue

from ..clients.core import RunResource
from ..graph.snapshots import deserialize_snapshot, serialize_snapshot, to_typescript_snapshot
from ..graph.state import GraphState, create_initial_state
from ..operations.contracts import CreativeOperation
from ..operations.definitions import OPERATION_DEFINITIONS
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


class ArtifactHydrationPort(Protocol):
    def hydrate(
        self,
        resource: RunResource,
        state: Mapping[str, Any],
        active_artifact: Mapping[str, Any],
    ) -> None: ...

    def release(self, artifact_id: str, resource: RunResource) -> None: ...


class WritingJobHandler:
    def __init__(
        self,
        core: CoreClientPort,
        *,
        parent_graph: GraphPort,
        operation_graph: GraphPort,
        artifacts: ArtifactHydrationPort,
        workflow_log: WorkflowLogPort | None = None,
    ) -> None:
        self._core = core
        self._parent_graph = parent_graph
        self._operation_graph = operation_graph
        self._artifacts = artifacts
        self._workflow_log = workflow_log

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "writing":
            raise ValueError("写作处理器收到非写作任务")
        payload = _job_payload(job)
        resource = _resource(job)
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
        _validate_job_context_identity(job, payload, context)
        current_job_state = _current_job_snapshot(job, context)
        owned_artifact_id: str | None = None
        if current_job_state is not None:
            _validate_stable_identity(
                current_job_state,
                payload,
                current_command_id=job.jobId,
            )
            current_job_state = _attach_runtime_context(
                current_job_state,
                context,
                resource,
            )
            owned_artifact_id = self._hydrate_for_state(
                resource,
                current_job_state,
                context,
            )
            if await self._settle_recovered_state(
                resource,
                job.runId,
                current_job_state,
                owned_artifact_id,
            ):
                return
        state, graph = self._prepare_state(
            job,
            context,
            current_job_state=current_job_state,
            payload=payload,
        )
        if current_job_state is None:
            owned_artifact_id = self._hydrate_for_state(resource, state, context)
        input_artifact_id = state.get("activeArtifactId")
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
            data={"agentId": "写作", "agentName": "作家"},
        )
        try:
            result = await graph.ainvoke(state)
        except Exception as exc:
            self._record_state(job.runId, "运行异常", {"错误": str(exc) or "智能体运行失败"})
            self._finish_log(job.runId, "错误")
            await self._core.fail(
                resource,
                sequence=sequence + 1,
                code="AGENT_RUN_FAILED",
                message=str(exc) or "智能体运行失败",
                recoverable=True,
            )
            self._release(owned_artifact_id, resource)
            raise NonRetryableJobError("写作运行失败已上报核心服务") from exc

        stable = cast(
            GraphState,
            {
                key: value
                for key, value in result.items()
                if key not in {"__interrupt__", "runtimeContext"}
            },
        )
        interrupt_artifact_id = _artifact_id_from_interrupt(result.get("__interrupt__"))
        if interrupt_artifact_id is not None:
            stable["activeArtifactId"] = interrupt_artifact_id
            stable["artifactStatus"] = "awaiting_user"
            stable["phase"] = "waiting_user"
            stable["operationStep"] = "await_user_decision"
            stable["operationStage"] = "等待用户决策"
        stable_artifact_id = stable.get("activeArtifactId")
        if (
            owned_artifact_id is None
            and not isinstance(input_artifact_id, str)
            and isinstance(stable_artifact_id, str)
            and stable_artifact_id
        ):
            owned_artifact_id = stable_artifact_id
        waiting_for_user = "__interrupt__" in result or stable.get("phase") == "waiting_user"
        artifact_id = stable.get("activeArtifactId")
        next_sequence = sequence + 1
        has_review_event = waiting_for_user and isinstance(artifact_id, str) and bool(artifact_id)
        if has_review_event:
            active_agent = stable.get("activeAgent")
            await self._core.send_event(
                resource,
                sequence=next_sequence,
                event="artifact_awaiting_user_approval",
                data={
                    "agentId": active_agent if isinstance(active_agent, str) else "系统",
                    "artifactId": artifact_id,
                },
            )
            next_sequence += 1
        stable["eventSequence"] = next_sequence
        checkpoint = to_typescript_snapshot(serialize_snapshot(stable))
        self._record_state(
            job.runId,
            "保存稳定快照",
            {"阶段": checkpoint.get("phase"), "操作阶段": checkpoint.get("operationStage")},
        )
        await self._core.save_checkpoint(
            resource,
            sequence=next_sequence,
            checkpoint=checkpoint,
        )
        if stable.get("phase") == "error":
            message = str(stable.get("errorMessage") or "智能体运行失败")
            self._finish_log(job.runId, "错误")
            await self._core.fail(
                resource,
                sequence=next_sequence + 1,
                code="AGENT_RUN_FAILED",
                message=message,
                recoverable=True,
            )
            self._release(owned_artifact_id, resource)
            raise NonRetryableJobError("写作运行失败已上报核心服务")
        if waiting_for_user:
            self._finish_log(job.runId, "等待用户确认")
            self._release(owned_artifact_id, resource)
            return
        await self._core.complete(
            resource,
            sequence=next_sequence + 1,
            result={"finalResponse": str(stable.get("finalResponse", ""))},
        )
        self._release(owned_artifact_id, resource)
        self._finish_log(job.runId, "完成")

    def _record_state(self, run_id: str, node: str, changes: dict[str, Any]) -> None:
        if self._workflow_log is not None:
            self._workflow_log.record_state(run_id, node, changes)

    def _finish_log(self, run_id: str, status: str) -> None:
        if self._workflow_log is not None:
            self._workflow_log.finish_run(run_id, status)

    async def _settle_recovered_state(
        self,
        resource: RunResource,
        run_id: str,
        state: GraphState,
        owned_artifact_id: str | None = None,
    ) -> bool:
        phase = state.get("phase")
        sequence = int(state.get("eventSequence", 0)) + 1
        if phase == "completed":
            self._record_state(run_id, "重放完成回调", {"阶段": phase})
            await self._core.complete(
                resource,
                sequence=sequence,
                result={"finalResponse": str(state.get("finalResponse", ""))},
            )
            self._release(owned_artifact_id, resource)
            self._finish_log(run_id, "完成")
            return True
        if phase == "error":
            message = str(state.get("errorMessage") or "智能体运行失败")
            self._record_state(run_id, "重放失败回调", {"阶段": phase})
            await self._core.fail(
                resource,
                sequence=sequence,
                code="AGENT_RUN_FAILED",
                message=message,
                recoverable=True,
            )
            self._release(owned_artifact_id, resource)
            self._finish_log(run_id, "错误")
            raise NonRetryableJobError("写作运行失败已上报核心服务")
        if phase == "waiting_user":
            self._release(owned_artifact_id, resource)
            self._finish_log(run_id, "等待用户确认")
            return True
        return False

    def _hydrate_for_state(
        self,
        resource: RunResource,
        state: GraphState,
        context: dict[str, Any],
    ) -> str | None:
        artifact_id = state.get("activeArtifactId")
        if not isinstance(artifact_id, str) or not artifact_id:
            return None
        decision = state.get("resumeDecision")
        decision_value = decision.get("decision") if isinstance(decision, dict) else None
        if decision_value in {"approve", "discard"} or state.get("artifactStatus") in {
            "applied",
            "discarded",
        }:
            return None
        planning = context.get("planning")
        active_artifact = planning.get("activeArtifact") if isinstance(planning, dict) else None
        if (
            not isinstance(active_artifact, dict)
            or active_artifact.get("id") != artifact_id
        ):
            raise RuntimeError(
                "ACTIVE_ARTIFACT_CONTEXT_MISSING：当前恢复状态缺少匹配的 Core 权威草案"
            )
        self._artifacts.hydrate(resource, state, active_artifact)
        return artifact_id

    def _release(self, artifact_id: str | None, resource: RunResource) -> None:
        if artifact_id is not None:
            self._artifacts.release(artifact_id, resource)

    def _prepare_state(
        self,
        job: QueueJob,
        context: dict[str, Any],
        *,
        current_job_state: GraphState | None = None,
        payload: WritingJobPayload,
    ) -> tuple[GraphState, GraphPort]:
        planning = context.get("planning")
        if not isinstance(planning, dict):
            raise ValueError("核心服务缺少写作规划上下文")
        snapshot = planning.get("graphState")
        if current_job_state is not None:
            _apply_planning_history(current_job_state, planning)
            _apply_command_identity(current_job_state, payload, job.jobId)
            return (
                _attach_runtime_context(current_job_state, context, _resource(job)),
                self._operation_graph,
            )
        is_resume = job.payload.get("resume") is True
        if is_resume:
            if not isinstance(snapshot, dict):
                raise ValueError("恢复写作任务缺少稳定快照")
            state = deserialize_snapshot(snapshot)
            _validate_stable_identity(state, payload)
            resume_input = job.payload.get("resumeInput")
            if isinstance(resume_input, dict):
                state["resumeDecision"] = dict(resume_input)
                message = resume_input.get("userMessage")
                if isinstance(message, str) and message:
                    state["userMessage"] = message
            _apply_planning_history(state, planning)
            _apply_command_identity(state, payload, job.jobId)
            return (
                _attach_runtime_context(state, context, _resource(job)),
                self._operation_graph,
            )

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
            workflow_kind=payload.workflowKind,
            explicit_operation=payload.operation,
            command_id=job.jobId,
            target_total_word_count=payload.targetTotalWordCount,
            command_source=(
                payload.source.model_dump(mode="json")
                if payload.source is not None
                else None
            ),
        )
        _apply_planning_history(state, planning)
        if payload.operation == "write_short_story":
            raise ValueError(
                "SHORT_STORY_WORKFLOW_NOT_IMPLEMENTED：中短篇整稿专用串行审核尚未接入"
            )
        if payload.operation is not None:
            state["currentOperation"] = _explicit_operation(
                payload.operation,
                user_message,
            ).model_dump(mode="json")
            state["activeAgent"] = OPERATION_DEFINITIONS[payload.operation].primaryAgent
            return (
                _attach_runtime_context(state, context, _resource(job)),
                self._operation_graph,
            )
        return (
            _attach_runtime_context(state, context, _resource(job)),
            self._parent_graph,
        )


def _current_job_snapshot(
    job: QueueJob,
    context: dict[str, Any],
) -> GraphState | None:
    planning = context.get("planning")
    if not isinstance(planning, dict):
        return None
    snapshot = planning.get("graphState")
    if not isinstance(snapshot, dict) or snapshot.get("callbackJobId") != job.jobId:
        return None
    return deserialize_snapshot(snapshot)


def _resource(job: QueueJob) -> RunResource:
    return RunResource(
        userId=job.userId,
        novelId=job.novelId,
        taskId=job.taskId,
        runId=job.runId,
        jobId=job.jobId,
    )


def _attach_runtime_context(
    state: GraphState,
    context: dict[str, Any],
    resource: RunResource,
) -> GraphState:
    state["runtimeContext"] = {
        "coreContext": context,
        "runResource": resource.model_dump(),
    }
    return state


def _apply_planning_history(
    state: GraphState,
    planning: dict[str, Any],
) -> None:
    history = planning.get("conversationHistory")
    if isinstance(history, list):
        state["conversationHistory"] = [
            dict(item) for item in history if isinstance(item, dict)
        ]


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


def _job_payload(job: QueueJob) -> WritingJobPayload:
    try:
        return WritingJobPayload.model_validate(job.payload)
    except ValueError as exc:
        raise ValueError("WRITING_JOB_PAYLOAD_INVALID：写作队列载荷身份无效") from exc


def _validate_job_context_identity(
    job: QueueJob,
    payload: WritingJobPayload,
    context: dict[str, Any],
) -> None:
    planning = context.get("planning")
    workspace = context.get("workspace")
    if not isinstance(planning, dict) or not isinstance(workspace, dict):
        raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：Core 上下文结构无效")
    short = payload.workflowKind == "short_medium"
    required = {
        "taskId": job.taskId,
        "novelId": job.novelId,
        "chapterId": payload.chapterId,
    }
    if any(planning.get(key) != value for key, value in required.items()):
        raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：任务资源身份不一致")
    command_id = planning.get("commandId")
    if command_id is not None and command_id != job.jobId:
        raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：持久命令身份不一致")
    if short and command_id != job.jobId:
        raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：中短篇缺少持久命令身份")
    identity_values = {
        "workflowKind": payload.workflowKind,
        "operation": payload.operation,
        "targetTotalWordCount": payload.targetTotalWordCount,
        "source": (
            payload.source.model_dump(mode="json") if payload.source is not None else None
        ),
    }
    for key, expected in identity_values.items():
        actual = planning.get(key)
        if short or key in planning:
            if actual != expected:
                raise ValueError(f"WRITING_JOB_IDENTITY_MISMATCH：{key} 不一致")
    bible = workspace.get("writingBible")
    if short:
        if (
            not isinstance(bible, dict)
            or bible.get("storyLengthProfile") != "short_medium"
            or bible.get("targetTotalWordCount") != payload.targetTotalWordCount
        ):
            raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：作品圣经与中短篇命令不一致")
    elif isinstance(bible, dict) and bible.get("storyLengthProfile") != "long_serial":
        raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：作品圣经与长篇命令不一致")


def _validate_stable_identity(
    state: Mapping[str, Any],
    payload: WritingJobPayload,
    *,
    current_command_id: str | None = None,
) -> None:
    workflow = state.get("workflowKind")
    explicit = state.get("explicitOperation")
    if workflow != payload.workflowKind and (
        workflow is not None or payload.workflowKind == "short_medium"
    ):
        raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：稳定快照篇幅身份不一致")
    if explicit != payload.operation and (
        explicit is not None or payload.workflowKind == "short_medium"
    ):
        raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：稳定快照显式 Operation 不一致")
    if payload.workflowKind == "short_medium":
        expected_source = (
            payload.source.model_dump(mode="json")
            if payload.source is not None
            else None
        )
        if (
            state.get("targetTotalWordCount") != payload.targetTotalWordCount
            or state.get("commandSource") != expected_source
        ):
            raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：稳定快照中短篇来源不一致")
        if (
            current_command_id is not None
            and state.get("commandId") != current_command_id
        ):
            raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：稳定快照持久命令不一致")
    if payload.workflowKind == "short_medium" or payload.operation is not None:
        operation = state.get("currentOperation")
        kind = operation.get("kind") if isinstance(operation, dict) else None
        if kind != payload.operation:
            raise ValueError("WRITING_JOB_IDENTITY_MISMATCH：稳定快照当前 Operation 不一致")


def _apply_command_identity(
    state: GraphState,
    payload: WritingJobPayload,
    command_id: str,
) -> None:
    state["workflowKind"] = payload.workflowKind
    state["explicitOperation"] = payload.operation
    state["commandId"] = command_id
    state["targetTotalWordCount"] = payload.targetTotalWordCount
    state["commandSource"] = (
        payload.source.model_dump(mode="json") if payload.source is not None else None
    )


def _explicit_operation(kind: str, user_message: str) -> CreativeOperation:
    definition = OPERATION_DEFINITIONS[kind]  # type: ignore[index]
    return CreativeOperation(
        kind=definition.kind,
        targetType=definition.targetType,
        userGoal=user_message,
        primaryAgent=definition.primaryAgent,
        reviewers=list(definition.reviewers),
        outputKind=definition.outputKind,
        requiresArtifact=definition.requiresArtifact,
        requiresUserApproval=definition.requiresUserApproval,
        confidence=1,
        reasoning="由 Core 持久命令显式指定，不经过关键词或模型分类。",
    )

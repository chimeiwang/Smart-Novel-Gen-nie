from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

from inkforge_contracts.long_serial import (
    LONG_SERIAL_RUN_PAYLOAD_ADAPTER,
    PUBLIC_LONG_SERIAL_OPERATIONS,
    LongSerialResumeInput,
    LongSerialRunPayload,
)
from pydantic import JsonValue, ValidationError

from ..clients.core import RunResource
from ..graph.snapshots import deserialize_snapshot, serialize_snapshot, to_typescript_snapshot
from ..graph.state import GraphState, create_initial_state
from ..operations.contracts import CreativeOperation, CreativeOperationKind
from ..operations.definitions import OPERATION_DEFINITIONS, OperationDefinition
from ..queue.cancellation import JobCancelledError, RunCancellationPort
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
        cancellation: RunCancellationPort | None = None,
    ) -> None:
        self._core = core
        self._parent_graph = parent_graph
        self._operation_graph = operation_graph
        self._artifacts = artifacts
        self._workflow_log = workflow_log
        self._cancellation = cancellation

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "writing":
            raise ValueError("写作处理器收到非写作任务")
        resource = _resource(job)
        await self._ensure_active(resource)
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
        await self._ensure_active(resource)
        context = await self._core.call_tool(resource, "写作", "get_writing_context", {})
        await self._ensure_active(resource)
        current_job_state = _current_job_snapshot(job, context)
        owned_artifact_id: str | None = None
        if current_job_state is not None:
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
        await self._ensure_active(resource)
        await self._core.send_event(
            resource,
            sequence=sequence,
            event="agent_start",
            data={"agentId": "写作", "agentName": "作家"},
        )
        try:
            await self._ensure_active(resource)
            result = await graph.ainvoke(state)
            await self._ensure_active(resource)
        except JobCancelledError:
            self._release(owned_artifact_id, resource)
            self._finish_log(job.runId, "已取消")
            raise
        except Exception as exc:
            self._record_state(job.runId, "运行异常", {"错误": str(exc) or "智能体运行失败"})
            self._finish_log(job.runId, "错误")
            await self._ensure_active(resource)
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
        next_sequence = sequence + 1
        stable["eventSequence"] = next_sequence
        checkpoint = to_typescript_snapshot(serialize_snapshot(stable))
        self._record_state(
            job.runId,
            "保存稳定快照",
            {"阶段": checkpoint.get("phase"), "操作阶段": checkpoint.get("operationStage")},
        )
        await self._ensure_active(resource)
        await self._core.save_checkpoint(
            resource,
            sequence=next_sequence,
            checkpoint=checkpoint,
        )
        if stable.get("phase") == "error":
            message = str(stable.get("errorMessage") or "智能体运行失败")
            self._finish_log(job.runId, "错误")
            await self._ensure_active(resource)
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
        await self._ensure_active(resource)
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
        await self._ensure_active(resource)
        phase = state.get("phase")
        sequence = int(state.get("eventSequence", 0)) + 1
        if phase == "completed":
            self._record_state(run_id, "重放完成回调", {"阶段": phase})
            await self._ensure_active(resource)
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
            await self._ensure_active(resource)
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

    async def _ensure_active(self, resource: RunResource) -> None:
        if self._cancellation is not None:
            await self._cancellation.ensure_active(resource.jobId)

    def _prepare_state(
        self,
        job: QueueJob,
        context: dict[str, Any],
        *,
        current_job_state: GraphState | None = None,
    ) -> tuple[GraphState, GraphPort]:
        explicit_payload = _explicit_long_serial_payload(job)
        planning = context.get("planning")
        if not isinstance(planning, dict):
            raise ValueError("核心服务缺少写作规划上下文")
        snapshot = planning.get("graphState")
        if current_job_state is not None:
            if explicit_payload is not None:
                _require_snapshot_matches_explicit_payload(
                    current_job_state,
                    explicit_payload,
                )
            _apply_planning_history(current_job_state, planning)
            return (
                _attach_runtime_context(current_job_state, context, _resource(job)),
                self._operation_graph,
            )
        is_resume = job.payload.get("resume") is True
        if is_resume:
            if not isinstance(snapshot, dict):
                raise ValueError("恢复写作任务缺少稳定快照")
            state = deserialize_snapshot(snapshot)
            if explicit_payload is not None:
                _require_snapshot_matches_explicit_payload(state, explicit_payload)
                explicit_resume_input = explicit_payload.resumeInput
                if explicit_resume_input is None:
                    raise ValueError("显式长篇恢复任务缺少恢复输入")
                if (
                    explicit_resume_input.artifactId is not None
                    and explicit_resume_input.decision is not None
                ):
                    state["resumeDecision"] = explicit_resume_input.model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                message = explicit_resume_input.userMessage
                if message:
                    state["userMessage"] = message
            else:
                resume_input = job.payload.get("resumeInput")
                if (
                    state.get("workflow") == "long_serial"
                    and isinstance(resume_input, dict)
                    and "artifactId" not in resume_input
                    and "decision" not in resume_input
                ):
                    try:
                        ordinary_resume = LongSerialResumeInput.model_validate(
                            resume_input
                        )
                    except ValidationError as exc:
                        raise ValueError("显式长篇恢复输入无效") from exc
                    if ordinary_resume.userMessage:
                        state["userMessage"] = ordinary_resume.userMessage
                elif isinstance(resume_input, dict):
                    state["resumeDecision"] = dict(resume_input)
                    legacy_message = resume_input.get("userMessage")
                    if isinstance(legacy_message, str) and legacy_message:
                        state["userMessage"] = legacy_message
            _apply_planning_history(state, planning)
            return (
                _attach_runtime_context(state, context, _resource(job)),
                self._operation_graph,
            )

        if explicit_payload is not None:
            state = _create_explicit_long_serial_state(job, explicit_payload)
            _apply_planning_history(state, planning)
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
        )
        _apply_planning_history(state, planning)
        return (
            _attach_runtime_context(state, context, _resource(job)),
            self._parent_graph,
        )


def _explicit_long_serial_payload(job: QueueJob) -> LongSerialRunPayload | None:
    if job.payload.get("workflow") != "long_serial":
        return None
    try:
        payload = LONG_SERIAL_RUN_PAYLOAD_ADAPTER.validate_python(job.payload)
    except ValidationError as exc:
        raise ValueError("显式长篇任务载荷无效") from exc
    _explicit_operation_definition(payload.operation)
    if payload.chapterId != payload.target.id:
        raise ValueError("显式长篇任务的章节锚点与目标不一致")
    if payload.scope.kind not in PUBLIC_LONG_SERIAL_OPERATIONS[
        payload.operation
    ].allowedScopeKinds:
        raise ValueError("显式长篇任务的执行范围未开放")
    if (
        payload.scope.kind == "chapter"
        and payload.scope.chapterId != payload.target.id
    ):
        raise ValueError("显式长篇任务的章节范围与目标不一致")
    if payload.operation in {
        "rewrite_chapter_selection",
        "rewrite_outline_selection",
    } and (payload.selectionTarget is None or payload.selectionSnapshot is None):
        raise ValueError("选区长篇任务缺少冻结的选区快照")
    return payload


def _explicit_operation_definition(operation: str) -> OperationDefinition:
    public = PUBLIC_LONG_SERIAL_OPERATIONS.get(operation)
    if public is None:
        raise ValueError(f"显式长篇 Operation 未开放：{operation}")
    definition = OPERATION_DEFINITIONS.get(cast(CreativeOperationKind, operation))
    if definition is None or definition.to_public_definition() != public:
        raise ValueError(f"显式长篇 Operation 定义无效：{operation}")
    return definition


def _create_explicit_long_serial_state(
    job: QueueJob,
    payload: LongSerialRunPayload,
) -> GraphState:
    definition = _explicit_operation_definition(payload.operation)
    state = create_initial_state(
        task_id=job.taskId,
        user_id=job.userId,
        novel_id=job.novelId,
        chapter_id=payload.chapterId,
        user_message=payload.userInstruction,
        target_word_count=payload.targetWordCount,
    )
    state["workflow"] = "long_serial"
    state["target"] = payload.target.model_dump(mode="json")
    state["scope"] = payload.scope.model_dump(mode="json")
    state["sourceBindings"] = [
        binding.model_dump(mode="json") for binding in payload.sourceBindings
    ]
    if payload.selectionTarget is not None:
        state["selectionTarget"] = payload.selectionTarget.model_dump(mode="json")
    if payload.selectionSnapshot is not None:
        state["selectionSnapshot"] = payload.selectionSnapshot.model_dump(mode="json")
    state["currentOperation"] = CreativeOperation(
        kind=definition.kind,
        targetType=definition.targetType,
        targetId=payload.target.id,
        userGoal=payload.userInstruction,
        primaryAgent=definition.primaryAgent,
        reviewers=list(definition.reviewers),
        outputKind=definition.outputKind,
        requiresArtifact=definition.requiresArtifact,
        requiresUserApproval=definition.requiresUserApproval,
        confidence=1.0,
        reasoning="显式长篇任务按服务端 Operation 定义执行。",
    ).model_dump(mode="json")
    return state


def _require_snapshot_matches_explicit_payload(
    state: GraphState,
    payload: LongSerialRunPayload,
) -> None:
    expected = {
        "workflow": "long_serial",
        "chapterId": payload.chapterId,
        "target": payload.target.model_dump(mode="json"),
        "scope": payload.scope.model_dump(mode="json"),
        "sourceBindings": [
            binding.model_dump(mode="json") for binding in payload.sourceBindings
        ],
    }
    if payload.selectionTarget is not None:
        expected["selectionTarget"] = payload.selectionTarget.model_dump(mode="json")
    if payload.selectionSnapshot is not None:
        expected["selectionSnapshot"] = payload.selectionSnapshot.model_dump(mode="json")
    for field, value in expected.items():
        if state.get(field) != value:
            raise ValueError(f"显式长篇恢复快照的 {field} 与任务载荷不一致")
    operation = state.get("currentOperation")
    if not isinstance(operation, dict) or operation.get("kind") != payload.operation:
        raise ValueError("显式长篇恢复快照的 Operation 与任务载荷不一致")


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

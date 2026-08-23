from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol, Self, cast

from inkforge_contracts.long_serial import (
    ChapterTarget,
    LongSerialScope,
    SelectionSnapshot,
    SelectionTarget,
    SourceBinding,
)
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, model_validator

from ..artifacts.patch import PatchApplicationError, TextReplacePatch
from ..clients.core import CoreServiceError
from ..definitions.agents import AgentId
from ..graph.context import build_operation_context
from ..graph.state import GraphState
from ..queue.cancellation import JobCancelledError, RunCancellationPort
from ..runtime.execution import AgentExecutionMode
from .artifact_contract import (
    has_artifact_terminal_event,
    validate_artifact_submission,
)
from .contracts import CreativeOperation, CreativeOperationKind
from .definitions import OPERATION_DEFINITIONS, OperationDefinition

_LONG_SERIAL_SCOPE_ADAPTER: TypeAdapter[LongSerialScope] = TypeAdapter(LongSerialScope)
_SOURCE_BINDINGS_ADAPTER: TypeAdapter[list[SourceBinding]] = TypeAdapter(
    list[SourceBinding]
)


class AgentExecutorPort(Protocol):
    async def run(
        self,
        agent_id: str,
        state: dict[str, Any],
        *,
        execution_mode: AgentExecutionMode,
        operation_kind: CreativeOperationKind,
    ) -> dict[str, Any]: ...


class ArtifactPort(Protocol):
    async def submit(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        content: str,
    ) -> str: ...

    async def revise(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        content: str,
    ) -> str: ...

    async def patch(
        self,
        state: dict[str, Any],
        artifact_id: str,
        patches: list[TextReplacePatch],
    ) -> str: ...

    async def mark_awaiting_user(self, artifact_id: str) -> None: ...

    async def apply(self, artifact_id: str) -> None: ...

    async def discard(self, artifact_id: str) -> None: ...

    def review_context(self, artifact_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class OperationDependencies:
    agentExecutor: AgentExecutorPort
    artifacts: ArtifactPort
    cancellation: RunCancellationPort | None = None


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: AgentId
    verdict: Literal["pass", "revise", "block"]
    summary: str
    requiredChanges: str | None = None
    revisionMode: Literal["patch", "rewrite"] | None = None
    patches: list[TextReplacePatch] | None = None
    iteration: int = 0

    @model_validator(mode="after")
    def validate_revision_combination(self) -> Self:
        _validate_review_revision_combination(self.verdict, self.revisionMode, self.patches)
        return self


class ReviewOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["pass", "revise", "block"]
    reviewer: AgentId
    summary: str
    requiredChanges: str | None = None
    revisionMode: Literal["patch", "rewrite"] | None = None
    patches: list[TextReplacePatch] | None = None

    @model_validator(mode="after")
    def validate_revision_combination(self) -> Self:
        _validate_review_revision_combination(self.verdict, self.revisionMode, self.patches)
        return self


def _validate_review_revision_combination(
    verdict: Literal["pass", "revise", "block"],
    revision_mode: Literal["patch", "rewrite"] | None,
    patches: list[TextReplacePatch] | None,
) -> None:
    if verdict in {"pass", "block"}:
        if revision_mode is not None or patches is not None:
            raise ValueError("通过或阻断结论不得携带 revisionMode 或 patches")
        return
    if revision_mode is None:
        raise ValueError("revise 结论必须声明 revisionMode")
    if revision_mode == "patch":
        if patches is None or not 1 <= len(patches) <= 20:
            raise ValueError("patch 模式必须携带 1 到 20 个 patch")
    elif patches is not None:
        raise ValueError("rewrite 模式不得携带 patches")


def decide_review_outcome(
    results: list[ReviewResult],
    *,
    reviewer_order: tuple[AgentId, ...] | list[AgentId] | None = None,
) -> ReviewOutcome:
    ordered = _ordered_review_results(results, reviewer_order)
    blockers = [result for result in ordered if result.verdict == "block"]
    if blockers:
        return _outcome_from("block", blockers)
    revisers = [result for result in ordered if result.verdict == "revise"]
    if revisers:
        revision_mode: Literal["patch", "rewrite"] = (
            "rewrite"
            if any(result.revisionMode == "rewrite" for result in revisers)
            else "patch"
        )
        return _outcome_from("revise", revisers, revision_mode)
    passed = ordered or [ReviewResult(reviewer="编辑", verdict="pass", summary="审核通过")]
    return _outcome_from("pass", passed)


def validate_review_results(
    results: list[ReviewResult], reviewer_order: tuple[AgentId, ...] | list[AgentId]
) -> list[ReviewResult]:
    """在复审聚合入口校验结果身份和数量，并按 Operation 顺序返回。"""

    if len(set(reviewer_order)) != len(reviewer_order):
        raise ValueError("Operation reviewer 配置不得重复")
    reviewers = [result.reviewer for result in results]
    if len(set(reviewers)) != len(reviewers):
        raise ValueError("Reviewer 结果包含重复 reviewer")
    declared = set(reviewer_order)
    undeclared = sorted(set(reviewers) - declared)
    if undeclared:
        raise ValueError("Reviewer 结果包含未声明 reviewer")
    if len(results) != len(reviewer_order):
        raise ValueError("Reviewer 结果数量与 Operation 声明不一致")
    missing = [reviewer for reviewer in reviewer_order if reviewer not in set(reviewers)]
    if missing:
        raise ValueError("Reviewer 结果缺少声明 reviewer")
    order = {reviewer: index for index, reviewer in enumerate(reviewer_order)}
    return sorted(results, key=lambda result: order[result.reviewer])


def _ordered_review_results(
    results: list[ReviewResult], reviewer_order: tuple[AgentId, ...] | list[AgentId] | None
) -> list[ReviewResult]:
    if reviewer_order is None:
        return list(results)
    order = {reviewer: index for index, reviewer in enumerate(reviewer_order)}
    return sorted(results, key=lambda result: order.get(result.reviewer, len(order)))


def _outcome_from(
    verdict: Literal["pass", "revise", "block"],
    results: list[ReviewResult],
    revision_mode: Literal["patch", "rewrite"] | None = None,
) -> ReviewOutcome:
    patches = (
        [patch for result in results for patch in (result.patches or [])]
        if revision_mode == "patch"
        else None
    )
    return ReviewOutcome(
        verdict=verdict,
        reviewer=results[0].reviewer,
        summary="\n".join(f"{result.reviewer}：{result.summary}" for result in results),
        requiredChanges="\n".join(
            f"{result.reviewer}：{result.requiredChanges or result.summary}" for result in results
        ),
        revisionMode=revision_mode,
        patches=patches,
    )


def build_operation_graph(
    dependencies: OperationDependencies,
    *,
    checkpointer: Any | None = None,
) -> Any:
    async def ensure_active(state: GraphState) -> None:
        if dependencies.cancellation is None:
            return
        runtime_context = state.get("runtimeContext")
        resource = (
            runtime_context.get("runResource")
            if isinstance(runtime_context, dict)
            else None
        )
        job_id = resource.get("jobId") if isinstance(resource, dict) else None
        await dependencies.cancellation.ensure_active(
            job_id if isinstance(job_id, str) else None
        )

    async def prepare(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        operation = _operation(state)
        definition = _operation_definition(operation)
        runtime_context = state.get("runtimeContext")
        if not isinstance(runtime_context, dict):
            raise ValueError("图状态缺少仅运行时上下文")
        source = runtime_context.get("coreContext")
        if not isinstance(source, dict):
            raise ValueError("仅运行时上下文缺少 Core 聚合上下文")
        context_source = {
            **source,
            "selectionTarget": state.get("selectionTarget"),
            "selectionSnapshot": state.get("selectionSnapshot"),
        }
        projection = build_operation_context(definition, context_source)
        return {
            "contextMessages": [
                json.dumps(projection, ensure_ascii=False, separators=(",", ":"))
            ],
            "operationStep": "prepare_context",
            "operationStage": "准备操作上下文",
            "phase": "active",
        }

    def route_from_start(state: GraphState) -> str:
        _operation(state)
        return (
            "resumeUserDecision"
            if state.get("resumeDecision") and state.get("activeArtifactId")
            else "prepareOperationContext"
        )

    async def execute(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        operation = _operation(state)
        result = await dependencies.agentExecutor.run(
            operation.primaryAgent,
            dict(state),
            execution_mode="primary",
            operation_kind=operation.kind,
        )
        outputs = dict(state.get("agentOutputs", {}))
        outputs[operation.primaryAgent] = result
        return {
            "activeAgent": operation.primaryAgent,
            "agentOutputs": outputs,
            "operationStep": "execute_operation",
            "operationStage": "执行创作操作",
        }

    async def submit_or_respond(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        operation = _operation(state)
        definition = _operation_definition(operation)
        output = state.get("agentOutputs", {}).get(operation.primaryAgent, {})
        outputs = dict(state.get("agentOutputs", {}))
        visible = str(output.get("visibleContent", ""))
        control_events = _control_events(output.get("controlEvents", []))
        if not definition.requiresArtifact:
            return {
                "finalResponse": visible,
                "operationStep": "direct_response",
                "operationStage": "直接回复",
            }
        is_revision = bool(
            state.get("activeArtifactId")
            and state.get("artifactIteration", 0) > 0
        )
        authoritative_artifact: dict[str, Any] | None = None
        if is_revision:
            artifact_id = state.get("activeArtifactId")
            if not isinstance(artifact_id, str) or not artifact_id:
                raise ValueError("ARTIFACT_REVISION_IDENTITY_MISMATCH：返工缺少草案标识")
            authoritative_artifact = dependencies.artifacts.review_context(artifact_id)

        if not has_artifact_terminal_event(control_events):
            retry_state = dict(state)
            retry_state["executionInstructions"] = [
                *state.get("executionInstructions", []),
                _artifact_retry_instruction(definition),
            ]
            retry_output = await dependencies.agentExecutor.run(
                operation.primaryAgent,
                retry_state,
                execution_mode="reviser" if is_revision else "primary",
                operation_kind=operation.kind,
            )
            retry_visible = str(retry_output.get("visibleContent", ""))
            if _has_builder_events(control_events):
                visible = "\n\n".join(part for part in (visible, retry_visible) if part)
            else:
                visible = retry_visible
            control_events = [
                *control_events,
                *_control_events(retry_output.get("controlEvents", [])),
            ]
            output = {
                **retry_output,
                "visibleContent": visible,
                "controlEvents": control_events,
            }
            outputs[operation.primaryAgent] = output
        submission = validate_artifact_submission(
            definition=definition,
            events=control_events,
            visible_content=visible,
            authoritative_artifact=authoritative_artifact,
            task_id=_required_state_text(state, "taskId"),
            operation_kind=operation.kind,
            selection_snapshot=(
                state.get("selectionSnapshot")
                if isinstance(state.get("selectionSnapshot"), dict)
                else None
            ),
        )
        artifact_id = (
            await dependencies.artifacts.revise(
                dict(state), submission.event, submission.content
            )
            if is_revision
            else await dependencies.artifacts.submit(
                dict(state), submission.event, submission.content
            )
        )
        return {
            "agentOutputs": outputs,
            "activeArtifactId": artifact_id,
            "artifactStatus": "draft_submitted",
            "operationStep": "submit_artifact",
            "operationStage": "提交待审核草案",
        }

    def route_after_submit(state: GraphState) -> str:
        if state.get("errorMessage"):
            return "suggestNextAction"
        operation = _operation(state)
        return "reviewArtifact" if operation.reviewers else "markArtifactAwaitingUser"

    async def review_artifact(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        return {
            "artifactStatus": "reviewing",
            "operationStep": "review_artifact",
            "operationStage": "复审待审核草案",
        }

    def route_review_workers(state: GraphState) -> list[Send] | str:
        reviewers = _operation(state).reviewers
        if not reviewers:
            return "mergeArtifactReviews"
        return [
            Send(
                "reviewArtifactWorker",
                {**dict(state), "reviewWorkerAgent": reviewer},
            )
            for reviewer in reviewers
        ]

    async def review_worker(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        reviewer = state.get("reviewWorkerAgent")
        if reviewer not in {"设定", "剧情", "写作", "校验", "编辑"}:
            raise ValueError("复审智能体无效")
        reviewer_id = cast(AgentId, reviewer)
        try:
            result = await dependencies.agentExecutor.run(
                reviewer_id,
                dict(state),
                execution_mode="reviewer",
                operation_kind=_operation(state).kind,
            )
        except JobCancelledError:
            raise
        except Exception:
            review = ReviewResult(
                reviewer=reviewer_id,
                verdict="block",
                summary="复审智能体暂时不可用",
                requiredChanges="请由用户审核当前草案，或稍后重新发起复审。",
                iteration=state.get("artifactIteration", 0),
            )
            return {"reviewResults": [review.model_dump()]}
        event = _evaluation_event(result.get("controlEvents", []))
        if event is None:
            review = ReviewResult(
                reviewer=reviewer_id,
                verdict="block",
                summary="复审智能体未提交结构化结论",
                requiredChanges="请重新发起复审。",
                iteration=state.get("artifactIteration", 0),
            )
        else:
            try:
                review = ReviewResult.model_validate(
                    {
                        "reviewer": reviewer_id,
                        "verdict": event.get("verdict"),
                        "summary": event.get("summary"),
                        "requiredChanges": event.get("requiredChanges"),
                        "revisionMode": event.get("revisionMode"),
                        "patches": event.get("patches"),
                        "iteration": state.get("artifactIteration", 0),
                    }
                )
                if (
                    review.revisionMode == "patch"
                    and _operation_definition(_operation(state)).textArtifactKind
                    != "chapter_draft"
                ):
                    raise ValueError("局部 patch 仅支持章节文本草案")
            except (ValidationError, ValueError):
                review = ReviewResult(
                    reviewer=reviewer_id,
                    verdict="block",
                    summary="复审结论不符合当前产物契约",
                    requiredChanges="请由用户审核当前草案，或重新发起复审。",
                    iteration=state.get("artifactIteration", 0),
                )
        return {"reviewResults": [review.model_dump()]}

    async def merge_reviews(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        iteration = state.get("artifactIteration", 0)
        current = [
            ReviewResult.model_validate(result)
            for result in state.get("reviewResults", [])
            if result.get("iteration") == iteration
        ]
        reviewer_order = list(_operation(state).reviewers)
        current = validate_review_results(current, reviewer_order)
        outcome = decide_review_outcome(
            current,
            reviewer_order=reviewer_order,
        )
        pending = outcome.model_dump() if outcome.verdict == "revise" else None
        return {
            "pendingRevision": pending,
            "artifactStatus": "blocked" if outcome.verdict == "block" else "reviewed",
            "operationStep": "merge_artifact_reviews",
            "operationStage": "合并复审结论",
        }

    def route_after_review(state: GraphState) -> str:
        pending = state.get("pendingRevision")
        if pending and state.get("artifactIteration", 0) < state.get("maxArtifactIterations", 5):
            if pending.get("revisionMode") == "patch":
                return "applyArtifactPatch"
            return "reviseArtifact"
        return "markArtifactAwaitingUser"

    async def apply_artifact_patch(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        artifact_id = state.get("activeArtifactId")
        pending = state.get("pendingRevision")
        failure_code: str | None = None
        if not isinstance(artifact_id, str) or not artifact_id:
            failure_code = "PATCH_ARTIFACT_UNSUPPORTED"
        elif not isinstance(pending, dict):
            failure_code = "PATCH_ARTIFACT_UNSUPPORTED"
        else:
            try:
                outcome = ReviewOutcome.model_validate(pending)
                patches = outcome.patches
                if outcome.revisionMode != "patch" or not patches:
                    raise PatchApplicationError("PATCH_ARTIFACT_UNSUPPORTED")
                await dependencies.artifacts.patch(dict(state), artifact_id, patches)
            except PatchApplicationError as exc:
                failure_code = exc.code
            except CoreServiceError as exc:
                failure_code = (
                    "ARTIFACT_REVISION_CONFLICT"
                    if exc.code == "ARTIFACT_REVISION_CONFLICT"
                    else "PATCH_CORE_ERROR"
                )
            except (ValidationError, ValueError):
                failure_code = "PATCH_ARTIFACT_UNSUPPORTED"
        if failure_code is not None:
            return {
                "patchFailureCode": failure_code,
                "errorMessage": _patch_failure_message(failure_code),
                "artifactStatus": "blocked",
                "pendingRevision": None,
                "operationStep": "apply_artifact_patch",
                "operationStage": "局部修订失败",
            }
        return {
            "artifactIteration": state.get("artifactIteration", 0) + 1,
            "pendingRevision": None,
            "patchFailureCode": None,
            "artifactStatus": "patched",
            "operationStep": "apply_artifact_patch",
            "operationStage": "应用局部修订",
        }

    async def revise(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        operation = _operation(state)
        iteration = state.get("artifactIteration", 0) + 1
        revision_state = {
            **dict(state),
            "artifactIteration": iteration,
            "artifactStatus": "revision_requested",
            "operationStep": "revise_artifact",
            "operationStage": "返工待审核草案",
        }
        result = await dependencies.agentExecutor.run(
            operation.primaryAgent,
            revision_state,
            execution_mode="reviser",
            operation_kind=operation.kind,
        )
        outputs = dict(state.get("agentOutputs", {}))
        outputs[operation.primaryAgent] = result
        return {
            "activeAgent": operation.primaryAgent,
            "agentOutputs": outputs,
            "artifactIteration": iteration,
            "artifactStatus": "revision_requested",
            "operationStep": "revise_artifact",
            "operationStage": "返工待审核草案",
        }

    async def mark_awaiting_user(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        artifact_id = state.get("activeArtifactId")
        if artifact_id:
            await dependencies.artifacts.mark_awaiting_user(artifact_id)
        return {
            "artifactStatus": (
                "blocked"
                if artifact_id and state.get("patchFailureCode")
                else "awaiting_user" if artifact_id else "none"
            ),
            "phase": "waiting_user" if artifact_id else state.get("phase", "active"),
            "operationStep": "mark_awaiting_user",
            "operationStage": "等待用户决策",
        }

    async def await_user(
        state: GraphState,
    ) -> Command[Literal["reviseArtifact", "suggestNextAction"]]:
        await ensure_active(state)
        artifact_id = state.get("activeArtifactId")
        if not artifact_id:
            return Command(goto="suggestNextAction")
        decision = interrupt(
            {
                "type": "artifact_review",
                "artifactId": artifact_id,
                "operation": state.get("currentOperation"),
                "actions": ["approve", "revise", "discard"],
            }
        )
        selected = decision.get("decision") if isinstance(decision, dict) else decision
        if selected == "approve":
            await dependencies.artifacts.apply(artifact_id)
            return Command(
                update={"userDecision": "approve", "artifactStatus": "applied"},
                goto="suggestNextAction",
            )
        if selected == "discard":
            await dependencies.artifacts.discard(artifact_id)
            return Command(
                update={"userDecision": "discard", "artifactStatus": "discarded"},
                goto="suggestNextAction",
            )
        if selected == "revise":
            feedback = (
                decision.get("feedback", "请根据用户意见继续修改。")
                if isinstance(decision, dict)
                else "请继续修改。"
            )
            return Command(
                update={
                    "userDecision": "revise",
                    "pendingRevision": {
                        "verdict": "revise",
                        "revisionMode": "rewrite",
                        "requiredChanges": feedback,
                    },
                },
                goto="reviseArtifact",
            )
        raise ValueError("用户草案决策无效")

    async def resume_user_decision(
        state: GraphState,
    ) -> Command[Literal["reviseArtifact", "suggestNextAction"]]:
        await ensure_active(state)
        artifact_id = state.get("activeArtifactId")
        decision = state.get("resumeDecision")
        if not artifact_id or not isinstance(decision, dict):
            raise ValueError("稳定恢复缺少草案或用户决策")
        selected = decision.get("decision")
        if selected == "approve":
            return Command(
                update={
                    "resumeDecision": None,
                    "userDecision": "approve",
                    "artifactStatus": "applied",
                },
                goto="suggestNextAction",
            )
        if selected == "discard":
            return Command(
                update={
                    "resumeDecision": None,
                    "userDecision": "discard",
                    "artifactStatus": "discarded",
                },
                goto="suggestNextAction",
            )
        if selected == "revise":
            return Command(
                update={
                    "resumeDecision": None,
                    "userDecision": "revise",
                    "pendingRevision": {
                        "verdict": "revise",
                        "revisionMode": "rewrite",
                        "requiredChanges": decision.get("userMessage", "请根据用户意见继续修改。"),
                    },
                },
                goto="reviseArtifact",
            )
        raise ValueError("稳定恢复的用户草案决策无效")

    async def suggest(state: GraphState) -> dict[str, Any]:
        await ensure_active(state)
        phase = "error" if state.get("errorMessage") else "completed"
        return {
            "phase": phase,
            "operationStep": "completed",
            "operationStage": "建议下一步",
        }

    builder = StateGraph(GraphState)
    builder.add_node("prepareOperationContext", prepare)
    builder.add_node("executeOperation", execute)
    builder.add_node("submitArtifactOrRespond", submit_or_respond)
    builder.add_node("reviewArtifact", review_artifact)
    builder.add_node("reviewArtifactWorker", review_worker)
    builder.add_node("mergeArtifactReviews", merge_reviews)
    builder.add_node("applyArtifactPatch", apply_artifact_patch)
    builder.add_node("reviseArtifact", revise)
    builder.add_node("markArtifactAwaitingUser", mark_awaiting_user)
    builder.add_node("awaitUserDecision", await_user)
    builder.add_node("resumeUserDecision", resume_user_decision)
    builder.add_node("suggestNextAction", suggest)
    builder.add_conditional_edges(
        START,
        route_from_start,
    )
    builder.add_edge("prepareOperationContext", "executeOperation")
    builder.add_edge("executeOperation", "submitArtifactOrRespond")
    builder.add_conditional_edges("submitArtifactOrRespond", route_after_submit)
    builder.add_conditional_edges("reviewArtifact", route_review_workers)
    builder.add_edge("reviewArtifactWorker", "mergeArtifactReviews")
    builder.add_conditional_edges("mergeArtifactReviews", route_after_review)
    builder.add_conditional_edges(
        "applyArtifactPatch",
        lambda state: "markArtifactAwaitingUser"
        if state.get("patchFailureCode")
        else "reviewArtifact",
    )
    builder.add_edge("reviseArtifact", "submitArtifactOrRespond")
    builder.add_edge("markArtifactAwaitingUser", "awaitUserDecision")
    builder.add_edge("suggestNextAction", END)
    return builder.compile(checkpointer=checkpointer)


def _operation(state: GraphState) -> CreativeOperation:
    operation = state.get("currentOperation")
    if operation is None:
        raise ValueError("图状态缺少当前创作操作")
    validated = CreativeOperation.model_validate(operation)
    has_long_serial_controls = any(
        field in state for field in ("workflow", "target", "scope", "sourceBindings")
    )
    if has_long_serial_controls and state.get("workflow") != "long_serial":
        raise ValueError("显式长篇图状态缺少有效工作流标识")
    if has_long_serial_controls:
        _validate_explicit_long_serial_state(state, validated)
    return validated


def _validate_explicit_long_serial_state(
    state: GraphState,
    operation: CreativeOperation,
) -> None:
    definition = _operation_definition(operation)
    try:
        public = definition.to_public_definition()
    except ValueError as exc:
        raise ValueError("显式长篇 Operation 未开放") from exc

    raw_target = state.get("target")
    try:
        target = ChapterTarget.model_validate(raw_target)
    except ValidationError as exc:
        raise ValueError("显式长篇目标无效") from exc
    if (
        target.type != public.targetKind
        or target.id != state.get("chapterId")
        or operation.targetType != public.targetKind
        or operation.targetId != target.id
    ):
        raise ValueError("显式长篇目标与 Operation 不一致")

    raw_scope = state.get("scope")
    try:
        scope = _LONG_SERIAL_SCOPE_ADAPTER.validate_python(raw_scope)
    except ValidationError as exc:
        raise ValueError("显式长篇执行范围无效") from exc
    if scope.kind not in public.allowedScopeKinds:
        raise ValueError("显式长篇执行范围超出 Operation 授权")
    if scope.kind == "chapter" and scope.chapterId != target.id:
        raise ValueError("显式长篇章节范围与目标不一致")

    raw_bindings = state.get("sourceBindings")
    try:
        bindings = _SOURCE_BINDINGS_ADAPTER.validate_python(raw_bindings)
    except ValidationError as exc:
        raise ValueError("显式长篇来源绑定无效") from exc
    if not bindings:
        raise ValueError("显式长篇来源绑定不能为空")

    if operation.primaryAgent != definition.primaryAgent:
        raise ValueError("显式长篇主责智能体与 Operation 定义不一致")
    if operation.reviewers != list(definition.reviewers):
        raise ValueError("显式长篇复审智能体与 Operation 定义不一致")
    if operation.outputKind != definition.outputKind:
        raise ValueError("显式长篇输出类型与 Operation 定义不一致")
    if (
        operation.requiresArtifact != definition.requiresArtifact
        or operation.requiresUserApproval != definition.requiresUserApproval
    ):
        raise ValueError("显式长篇产物策略与 Operation 定义不一致")
    selection_operations = {
        "rewrite_chapter_selection",
        "rewrite_outline_selection",
    }
    raw_selection_target = state.get("selectionTarget")
    raw_selection_snapshot = state.get("selectionSnapshot")
    if operation.kind in selection_operations:
        try:
            selection_target = SelectionTarget.model_validate(raw_selection_target)
            selection_snapshot = SelectionSnapshot.model_validate(raw_selection_snapshot)
        except ValidationError as exc:
            raise ValueError("显式长篇选区冻结快照无效") from exc
        if (
            selection_snapshot.resourceType != selection_target.resourceType
            or selection_snapshot.resourceId != selection_target.resourceId
            or selection_snapshot.baseUpdatedAt != selection_target.baseUpdatedAt
            or selection_snapshot.baseContentHash != selection_target.baseContentHash
            or selection_snapshot.selectionStart != selection_target.selectionStart
            or selection_snapshot.selectionEnd != selection_target.selectionEnd
            or selection_snapshot.selectedTextHash != selection_target.selectedTextHash
        ):
            raise ValueError("显式长篇选区快照与 selectionTarget 身份不一致")
        expected_types = (
            {"chapter_content"}
            if operation.kind == "rewrite_chapter_selection"
            else {"outline_content", "outline_node_content"}
        )
        if selection_target.resourceType not in expected_types:
            raise ValueError("显式长篇选区资源类型与 Operation 不一致")
        if operation.kind == "rewrite_chapter_selection":
            if scope.kind != "chapter" or scope.chapterId != target.id:
                raise ValueError("选区 scope 与章节 selectionTarget 身份不一致")
        elif selection_target.resourceType == "outline_content":
            if scope.kind != "novel":
                raise ValueError("选区 scope 与总纲 selectionTarget 身份不一致")
        elif (
            scope.kind != "outline_node"
            or scope.outlineNodeId != selection_target.resourceId
        ):
            raise ValueError("选区 scope 与大纲节点 selectionTarget 身份不一致")
    elif raw_selection_target is not None or raw_selection_snapshot is not None:
        raise ValueError("普通长篇操作不得携带选区冻结快照")


def _operation_definition(operation: CreativeOperation) -> OperationDefinition:
    if operation.kind == "sync_lore":
        raise ValueError("同步设定流程已移除，历史任务不能继续执行")
    definition = OPERATION_DEFINITIONS.get(operation.kind)
    if definition is None:
        raise ValueError(f"不支持的创作操作：{operation.kind}")
    return definition


def _evaluation_event(events: object) -> dict[str, Any] | None:
    if not isinstance(events, list):
        return None
    return next(
        (
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "submit_evaluation"
        ),
        None,
    )


def _control_events(events: object) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _has_builder_events(events: list[dict[str, Any]]) -> bool:
    return any(
        event.get("type")
        in {
            "start_update_builder",
            "append_update_batch",
            "append_outline_tree",
            "put_update_text_block",
            "put_update_item_text_block",
            "put_update_item_text_blocks",
            "finish_update_builder",
        }
        for event in events
    )


def _artifact_retry_instruction(definition: OperationDefinition) -> str:
    if definition.kind in {"rewrite_chapter_selection", "rewrite_outline_selection"}:
        tool_requirement = (
            "调用 begin_artifact_output，提交结构化 replacement 及冻结选区身份（包括"
            "baseUpdatedAt，必须与 Core 快照完全一致）；"
            "禁止 content 或完整章节/大纲"
        )
    elif definition.kind == "plan_chapter":
        tool_requirement = "调用 submit_beat_plan"
    elif definition.artifactPolicy == "agent_updates":
        tool_requirement = (
            "短小更新调用 propose_updates；批量更新必须完整执行一次 "
            "start_update_builder → 一个或多个 append/put → finish_update_builder，"
            "全程使用同一个 artifactKey，完成后立即停止"
        )
    else:
        tool_requirement = "调用 begin_artifact_output"
    return (
        "上一次响应缺少待审核草案控制事件。本次必须提交待审核草案控制事件："
        f"{tool_requirement}；不能只返回普通文本。"
    )


def _required_state_text(state: GraphState, key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"图状态缺少 {key}")
    return value


def _patch_failure_message(code: str) -> str:
    messages = {
        "PATCH_TARGET_NOT_FOUND": "局部修订目标未找到，请确认草案内容后重试。",
        "PATCH_TARGET_AMBIGUOUS": "局部修订目标不唯一，请确认草案内容后重试。",
        "PATCH_OVERLAP": "局部修订范围发生重叠，请重新提交修改。",
        "PATCH_ARTIFACT_UNSUPPORTED": "当前草案不支持局部修订，请改用完整返工。",
        "ARTIFACT_REVISION_CONFLICT": "草案已被其他操作修改，请重新审核当前草案。",
        "PATCH_CORE_ERROR": "局部修订未能保存，请重新审核当前草案。",
    }
    return messages.get(code, "局部修订未能应用，请重新审核当前草案。")

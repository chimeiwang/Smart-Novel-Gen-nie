from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from pydantic import BaseModel, ConfigDict, Field

from ..artifacts.builder import resolve_builder_artifact
from ..artifacts.updates import extract_artifact_content
from ..definitions.agents import AgentId
from ..graph.context import build_operation_context
from ..graph.state import GraphState
from .contracts import CreativeOperation
from .definitions import OPERATION_DEFINITIONS, OperationDefinition


class AgentExecutorPort(Protocol):
    async def run(self, agent_id: str, state: dict[str, Any]) -> dict[str, Any]: ...


class ArtifactPort(Protocol):
    async def submit(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        content: str,
    ) -> str: ...

    async def apply_patch(
        self,
        artifact_id: str,
        patches: list[dict[str, Any]],
    ) -> None: ...

    async def revise(
        self,
        state: dict[str, Any],
        event: dict[str, Any],
        content: str,
    ) -> str: ...

    async def mark_awaiting_user(self, artifact_id: str) -> None: ...

    async def apply(self, artifact_id: str) -> None: ...

    async def discard(self, artifact_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class OperationDependencies:
    agentExecutor: AgentExecutorPort
    artifacts: ArtifactPort


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: AgentId
    verdict: Literal["pass", "revise", "block"]
    summary: str
    requiredChanges: str | None = None
    revisionMode: Literal["patch", "rewrite"] = "rewrite"
    patches: list[dict[str, Any]] = Field(default_factory=list)
    iteration: int = 0


class ReviewOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["pass", "revise", "block"]
    reviewer: AgentId
    summary: str
    requiredChanges: str | None = None
    revisionMode: Literal["patch", "rewrite"] = "rewrite"
    patches: list[dict[str, Any]] = Field(default_factory=list)


def decide_review_outcome(results: list[ReviewResult]) -> ReviewOutcome:
    blockers = [result for result in results if result.verdict == "block"]
    if blockers:
        return _outcome_from("block", blockers, "rewrite")
    revisers = [result for result in results if result.verdict == "revise"]
    if revisers:
        can_patch = all(result.revisionMode == "patch" and result.patches for result in revisers)
        return _outcome_from(
            "revise",
            revisers,
            "patch" if can_patch else "rewrite",
        )
    passed = results or [ReviewResult(reviewer="编辑", verdict="pass", summary="审核通过")]
    return _outcome_from("pass", passed, "rewrite")


def _outcome_from(
    verdict: Literal["pass", "revise", "block"],
    results: list[ReviewResult],
    revision_mode: Literal["patch", "rewrite"],
) -> ReviewOutcome:
    return ReviewOutcome(
        verdict=verdict,
        reviewer=results[0].reviewer,
        summary="\n".join(f"{result.reviewer}：{result.summary}" for result in results),
        requiredChanges="\n".join(
            f"{result.reviewer}：{result.requiredChanges or result.summary}" for result in results
        ),
        revisionMode=revision_mode,
        patches=(
            [patch for result in results for patch in result.patches]
            if revision_mode == "patch"
            else []
        ),
    )


def build_operation_graph(
    dependencies: OperationDependencies,
    *,
    checkpointer: Any | None = None,
) -> Any:
    async def prepare(state: GraphState) -> dict[str, Any]:
        operation = _operation(state)
        definition = _operation_definition(operation)
        source = {
            "taskId": state["taskId"],
            "novelId": state["novelId"],
            "chapterId": state["chapterId"],
            "targetWordCount": state["targetWordCount"],
            "userMessage": state["userMessage"],
        }
        return {
            "contextMessages": [
                *state.get("contextMessages", []),
                *build_operation_context(definition, source),
            ],
            "operationStep": "prepare_context",
            "operationStage": "准备操作上下文",
            "phase": "active",
        }

    async def execute(state: GraphState) -> dict[str, Any]:
        operation = _operation(state)
        result = await dependencies.agentExecutor.run(
            operation.primaryAgent,
            dict(state),
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
        operation = _operation(state)
        definition = _operation_definition(operation)
        output = state.get("agentOutputs", {}).get(operation.primaryAgent, {})
        visible = str(output.get("visibleContent", ""))
        control_events = _control_events(output.get("controlEvents", []))
        preferred_artifact_type = (
            "submit_beat_plan" if definition.kind == "plan_chapter" else None
        )
        if not definition.requiresArtifact:
            return {
                "finalResponse": visible,
                "operationStep": "direct_response",
                "operationStage": "直接回复",
            }
        event = _artifact_event(
            control_events,
            visible,
            preferred_type=preferred_artifact_type,
        )
        if event is None:
            retry_state = dict(state)
            retry_state["contextMessages"] = [
                *state.get("contextMessages", []),
                _artifact_retry_instruction(definition),
            ]
            retry_output = await dependencies.agentExecutor.run(
                operation.primaryAgent,
                retry_state,
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
            outputs = dict(state.get("agentOutputs", {}))
            outputs[operation.primaryAgent] = output
            event = _artifact_event(
                control_events,
                visible,
                preferred_type=preferred_artifact_type,
            )
            if event is None:
                return {
                    "agentOutputs": outputs,
                    "errorMessage": "主责智能体未提交待审核草案控制事件",
                    "phase": "error",
                    "operationStep": "submit_artifact",
                }
        content = (
            extract_artifact_content(visible)
            if event["type"] == "begin_artifact_output"
            else visible
        )
        artifact_id = (
            await dependencies.artifacts.revise(dict(state), event, content)
            if state.get("activeArtifactId") and state.get("artifactIteration", 0) > 0
            else await dependencies.artifacts.submit(dict(state), event, content)
        )
        return {
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
        reviewer = state.get("reviewWorkerAgent")
        if reviewer not in {"设定", "剧情", "写作", "校验", "编辑"}:
            raise ValueError("复审智能体无效")
        reviewer_id = cast(AgentId, reviewer)
        try:
            result = await dependencies.agentExecutor.run(reviewer_id, dict(state))
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
            review = ReviewResult(
                reviewer=reviewer_id,
                verdict=event["verdict"],
                summary=event["summary"],
                requiredChanges=event.get("requiredChanges"),
                revisionMode=event.get("revisionMode", "rewrite"),
                patches=event.get("patches", []),
                iteration=state.get("artifactIteration", 0),
            )
        return {"reviewResults": [review.model_dump()]}

    async def merge_reviews(state: GraphState) -> dict[str, Any]:
        iteration = state.get("artifactIteration", 0)
        current = [
            ReviewResult.model_validate(result)
            for result in state.get("reviewResults", [])
            if result.get("iteration") == iteration
        ]
        outcome = decide_review_outcome(current)
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
            return (
                "applyArtifactPatch" if pending.get("revisionMode") == "patch" else "reviseArtifact"
            )
        return "markArtifactAwaitingUser"

    async def apply_patch(state: GraphState) -> dict[str, Any]:
        artifact_id = state.get("activeArtifactId")
        pending = state.get("pendingRevision") or {}
        patches = pending.get("patches", [])
        if not artifact_id or not patches:
            return {"pendingRevision": {**pending, "revisionMode": "rewrite"}}
        try:
            await dependencies.artifacts.apply_patch(artifact_id, patches)
            return {
                "artifactIteration": state.get("artifactIteration", 0) + 1,
                "pendingRevision": None,
                "artifactStatus": "reviewing",
                "operationStep": "apply_artifact_patch",
            }
        except Exception as exc:
            return {
                "pendingRevision": {
                    **pending,
                    "revisionMode": "rewrite",
                    "requiredChanges": str(exc),
                }
            }

    def route_after_patch(state: GraphState) -> str:
        pending = state.get("pendingRevision")
        return "reviseArtifact" if pending else "reviewArtifact"

    async def revise(state: GraphState) -> dict[str, Any]:
        return {
            "artifactIteration": state.get("artifactIteration", 0) + 1,
            "artifactStatus": "revision_requested",
            "operationStep": "revise_artifact",
            "operationStage": "返工待审核草案",
        }

    async def mark_awaiting_user(state: GraphState) -> dict[str, Any]:
        artifact_id = state.get("activeArtifactId")
        if artifact_id:
            await dependencies.artifacts.mark_awaiting_user(artifact_id)
        return {
            "artifactStatus": "awaiting_user" if artifact_id else "none",
            "phase": "waiting_user" if artifact_id else state.get("phase", "active"),
            "operationStep": "mark_awaiting_user",
            "operationStage": "等待用户决策",
        }

    async def await_user(
        state: GraphState,
    ) -> Command[Literal["reviseArtifact", "suggestNextAction"]]:
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
        artifact_id = state.get("activeArtifactId")
        decision = state.get("resumeDecision")
        if not artifact_id or not isinstance(decision, dict):
            raise ValueError("稳定恢复缺少草案或用户决策")
        selected = decision.get("decision")
        if selected == "approve":
            await dependencies.artifacts.apply(artifact_id)
            return Command(
                update={
                    "resumeDecision": None,
                    "userDecision": "approve",
                    "artifactStatus": "applied",
                },
                goto="suggestNextAction",
            )
        if selected == "discard":
            await dependencies.artifacts.discard(artifact_id)
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
    builder.add_node("applyArtifactPatch", apply_patch)
    builder.add_node("reviseArtifact", revise)
    builder.add_node("markArtifactAwaitingUser", mark_awaiting_user)
    builder.add_node("awaitUserDecision", await_user)
    builder.add_node("resumeUserDecision", resume_user_decision)
    builder.add_node("suggestNextAction", suggest)
    builder.add_conditional_edges(
        START,
        lambda state: (
            "resumeUserDecision"
            if state.get("resumeDecision") and state.get("activeArtifactId")
            else "prepareOperationContext"
        ),
    )
    builder.add_edge("prepareOperationContext", "executeOperation")
    builder.add_edge("executeOperation", "submitArtifactOrRespond")
    builder.add_conditional_edges("submitArtifactOrRespond", route_after_submit)
    builder.add_conditional_edges("reviewArtifact", route_review_workers)
    builder.add_edge("reviewArtifactWorker", "mergeArtifactReviews")
    builder.add_conditional_edges("mergeArtifactReviews", route_after_review)
    builder.add_conditional_edges("applyArtifactPatch", route_after_patch)
    builder.add_edge("reviseArtifact", "executeOperation")
    builder.add_edge("markArtifactAwaitingUser", "awaitUserDecision")
    builder.add_edge("suggestNextAction", END)
    return builder.compile(checkpointer=checkpointer)


def _operation(state: GraphState) -> CreativeOperation:
    operation = state.get("currentOperation")
    if operation is None:
        raise ValueError("图状态缺少当前创作操作")
    return CreativeOperation.model_validate(operation)


def _operation_definition(operation: CreativeOperation) -> OperationDefinition:
    if operation.kind == "sync_lore":
        raise ValueError("同步设定流程已移除，历史任务不能继续执行")
    definition = OPERATION_DEFINITIONS.get(operation.kind)
    if definition is None:
        raise ValueError(f"不支持的创作操作：{operation.kind}")
    return definition


def _artifact_event(
    events: object,
    visible_content: str,
    *,
    preferred_type: str | None = None,
) -> dict[str, Any] | None:
    typed_events = _control_events(events)
    if preferred_type is not None:
        preferred = next(
            (event for event in typed_events if event.get("type") == preferred_type),
            None,
        )
        if preferred is not None:
            return preferred
    builder = resolve_builder_artifact(typed_events, visible_content)
    if builder is not None:
        return builder
    accepted = {
        "propose_updates",
        "begin_artifact_output",
        "submit_beat_plan",
    }
    return next(
        (event for event in typed_events if event.get("type") in accepted),
        None,
    )


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
    if definition.kind == "plan_chapter":
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

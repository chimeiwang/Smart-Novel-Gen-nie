from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from inkforge_contracts import (
    ShortStoryChapterDraft,
    ShortStoryDraftMetadata,
    count_short_story_text_length,
)
from langgraph.graph import END, START, StateGraph

from ..definitions.agents import AgentId
from ..graph.state import GraphState
from ..runtime.execution import AgentExecutionMode

_OUTPUT_START = "ARTIFACT_OUTPUT_START"
_OUTPUT_END = "ARTIFACT_OUTPUT_END"
_COMPLETE_OUTPUT = re.compile(
    rf"\A\s*{re.escape(_OUTPUT_START)}\r?\n(?P<content>.*?)"
    rf"\r?\n{re.escape(_OUTPUT_END)}\s*\Z",
    re.DOTALL,
)
_REVIEWERS: tuple[AgentId, AgentId] = ("编辑", "校验")


class ShortStoryAgentExecutorPort(Protocol):
    async def run(
        self,
        agent_id: str,
        state: dict[str, Any],
        *,
        execution_mode: AgentExecutionMode,
        operation_kind: Literal["write_short_story"],
    ) -> dict[str, Any]: ...


class ShortStoryArtifactPort(Protocol):
    async def save_short_story(
        self,
        state: dict[str, Any],
        draft: ShortStoryChapterDraft,
        *,
        user_request: str | None,
    ) -> str: ...

    async def submit_evaluation(
        self,
        state: dict[str, Any],
        artifact_id: str,
        evaluator: str,
        event: dict[str, Any],
    ) -> None: ...

    async def mark_awaiting_user(self, artifact_id: str) -> None: ...

    def review_context(self, artifact_id: str) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ShortStoryGraphDependencies:
    agentExecutor: ShortStoryAgentExecutorPort
    artifacts: ShortStoryArtifactPort


def extract_complete_short_story(value: str) -> str:
    """从唯一、独占行边界中提取完整正文。"""

    if value.count(_OUTPUT_START) != 1 or value.count(_OUTPUT_END) != 1:
        raise ValueError(
            "SHORT_STORY_OUTPUT_BOUNDARY_INVALID：完整正文边界必须各出现一次"
        )
    matched = _COMPLETE_OUTPUT.fullmatch(value)
    if matched is None:
        raise ValueError(
            "SHORT_STORY_OUTPUT_BOUNDARY_INVALID：边界必须独占一行且前后只能有空白"
        )
    content = matched.group("content")
    if not content.strip():
        raise ValueError("SHORT_STORY_OUTPUT_BOUNDARY_INVALID：边界内正文不能为空")
    return content


def build_short_story_graph(
    dependencies: ShortStoryGraphDependencies,
    *,
    checkpointer: Any | None = None,
) -> Any:
    async def prepare(state: GraphState) -> dict[str, Any]:
        _require_short_story_operation(state)
        planning = _planning(state)
        short_context = _short_story_context(planning)
        decision = state.get("resumeDecision")
        selected = decision.get("decision") if isinstance(decision, dict) else None
        if selected not in {None, "approve", "revise", "discard"}:
            raise ValueError("SHORT_STORY_DECISION_INVALID：用户草案决定无效")

        result: dict[str, Any] = {
            "phase": "active",
            "activeAgent": "写作",
            "agentOutputs": {},
            "finalResponse": "",
            "contextMessages": [
                "中短篇整稿权威上下文："
                + json.dumps(short_context, ensure_ascii=False, separators=(",", ":"))
            ],
            "operationStep": "prepare_short_story",
            "operationStage": "准备中短篇整稿上下文",
            "shortStoryDecision": selected,
        }
        if selected in {"approve", "discard"}:
            return result
        _validate_generation_context(state, short_context)

        run_artifact = planning.get("shortStoryRunArtifact")
        if run_artifact is None:
            if selected == "revise":
                raise ValueError(
                    "SHORT_STORY_RUN_ARTIFACT_MISSING：用户改稿缺少权威正文草案"
                )
            result.update(
                {
                    "shortStoryNeedsGeneration": True,
                    "shortStoryAutomaticRewriteCount": 0,
                    "shortStoryGenerationReason": "user_request",
                    "shortStoryUserRequest": _required_raw_text(state, "userMessage"),
                    "shortStoryReviews": [],
                    "shortStoryArtifactRevision": None,
                }
            )
            return result
        if not isinstance(run_artifact, Mapping):
            raise ValueError(
                "SHORT_STORY_RUN_ARTIFACT_INVALID：持久正文草案结构无效"
            )

        artifact = _validate_run_artifact(state, short_context, run_artifact)
        artifact_id = _required_mapping_text(run_artifact, "id")
        revision = _required_positive_int(run_artifact, "revision")
        metadata = artifact.metadata
        current_command = _required_text(state, "commandId")
        result.update(
            {
                "activeArtifactId": artifact_id,
                "shortStoryArtifactRevision": revision,
                "shortStoryAutomaticRewriteCount": metadata.automaticRewriteCount,
            }
        )
        if metadata.generationCommandId == current_command:
            result.update(
                {
                    "shortStoryNeedsGeneration": False,
                    "shortStoryGenerationReason": metadata.generationReason,
                    "shortStoryUserRequest": None,
                    "shortStoryReviews": _current_revision_reviews(
                        run_artifact, revision
                    ),
                    "resumeDecision": None,
                }
            )
            return result
        if selected != "revise":
            raise ValueError(
                "SHORT_STORY_COMMAND_IDENTITY_MISMATCH：持久正文不属于当前生成命令"
            )
        feedback = _decision_feedback(decision)
        result.update(
            {
                "shortStoryNeedsGeneration": True,
                "shortStoryAutomaticRewriteCount": 0,
                "shortStoryGenerationReason": "user_request",
                "shortStoryUserRequest": feedback,
                "shortStoryReviews": [],
                "pendingRevision": {
                    "verdict": "revise",
                    "revisionMode": "rewrite",
                    "requiredChanges": feedback,
                },
            }
        )
        return result

    def route_after_prepare(state: GraphState) -> str:
        decision = state.get("shortStoryDecision")
        if decision in {"approve", "discard"}:
            return "finishShortStoryDecision"
        if state.get("shortStoryNeedsGeneration"):
            return "generateShortStory"
        reviews = _reviews_by_agent(state)
        if "编辑" not in reviews:
            return "reviewShortStoryByEditor"
        if "校验" not in reviews:
            return "reviewShortStoryByValidator"
        return "mergeShortStoryReviews"

    async def generate(state: GraphState) -> dict[str, Any]:
        automatic_count = state.get("shortStoryAutomaticRewriteCount")
        if automatic_count not in {0, 1}:
            raise ValueError("SHORT_STORY_REWRITE_COUNT_INVALID：自动返工计数无效")
        reason = state.get("shortStoryGenerationReason")
        if reason not in {"user_request", "automatic_rewrite"}:
            raise ValueError("SHORT_STORY_GENERATION_REASON_INVALID：正文生成原因无效")
        artifact_id = state.get("activeArtifactId")
        execution_mode: AgentExecutionMode = (
            "reviser" if isinstance(artifact_id, str) and artifact_id else "primary"
        )
        generation_state = dict(state)
        generation_state["activeAgent"] = "写作"
        if execution_mode == "reviser" and not isinstance(
            generation_state.get("pendingRevision"), dict
        ):
            generation_state["pendingRevision"] = {
                "verdict": "revise",
                "revisionMode": "rewrite",
                "requiredChanges": state.get("shortStoryUserRequest")
                or "根据当前用户要求完整重写中短篇正文。",
            }
        turn = await dependencies.agentExecutor.run(
            "写作",
            generation_state,
            execution_mode=execution_mode,
            operation_kind="write_short_story",
        )
        if turn.get("finishReason") != "completed":
            raise RuntimeError(
                "SHORT_STORY_GENERATION_INCOMPLETE：模型未确认完整结束，整轮正文作废"
            )
        if turn.get("controlEvents") or turn.get("toolCalls"):
            raise RuntimeError(
                "SHORT_STORY_GENERATION_PROTOCOL_INVALID：整稿生成不得调用工具"
            )
        content = extract_complete_short_story(str(turn.get("visibleContent", "")))
        draft = _build_draft(
            state,
            content,
            automatic_rewrite_count=cast(Literal[0, 1], automatic_count),
            generation_reason=cast(
                Literal["user_request", "automatic_rewrite"], reason
            ),
        )
        raw_user_request = state.get("shortStoryUserRequest")
        user_request = (
            raw_user_request
            if reason == "user_request"
            and isinstance(raw_user_request, str)
            and raw_user_request.strip()
            else None
        )
        saved_id = await dependencies.artifacts.save_short_story(
            dict(state), draft, user_request=user_request
        )
        authority = dependencies.artifacts.review_context(saved_id)
        revision = _required_positive_int(authority, "revision")
        return {
            "activeArtifactId": saved_id,
            "activeAgent": "写作",
            "artifactStatus": "under_review",
            "shortStoryArtifactRevision": revision,
            "shortStoryNeedsGeneration": False,
            "shortStoryReviews": [],
            "shortStoryUserRequest": None,
            "pendingRevision": None,
            "resumeDecision": None,
            "agentOutputs": {},
            "finalResponse": "",
            "operationStep": "generate_short_story",
            "operationStage": "生成完整中短篇正文",
        }

    async def review_editor(state: GraphState) -> dict[str, Any]:
        return await _run_reviewer(dependencies, state, "编辑")

    async def review_validator(state: GraphState) -> dict[str, Any]:
        return await _run_reviewer(dependencies, state, "校验")

    async def merge_reviews(state: GraphState) -> dict[str, Any]:
        reviews = _reviews_by_agent(state)
        if set(reviews) != set(_REVIEWERS):
            raise ValueError(
                "SHORT_STORY_REVIEWS_INCOMPLETE：当前正文修订尚未完成双审核"
            )
        issues = [
            reviews[reviewer]
            for reviewer in _REVIEWERS
            if reviews[reviewer]["verdict"] != "pass"
        ]
        automatic_count = state.get("shortStoryAutomaticRewriteCount")
        if automatic_count not in {0, 1}:
            raise ValueError("SHORT_STORY_REWRITE_COUNT_INVALID：自动返工计数无效")
        if issues and automatic_count == 0:
            required_changes = "\n".join(
                f"{item['evaluatorAgent']}："
                f"{item.get('requiredChanges') or item['summary']}"
                for item in issues
            )
            return {
                "shortStoryNeedsGeneration": True,
                "shortStoryAutomaticRewriteCount": 1,
                "shortStoryGenerationReason": "automatic_rewrite",
                "shortStoryUserRequest": None,
                "shortStoryReviews": [],
                "pendingRevision": {
                    "verdict": "revise",
                    "revisionMode": "rewrite",
                    "requiredChanges": required_changes,
                },
                "artifactStatus": "revision_requested",
                "operationStep": "request_automatic_short_story_rewrite",
                "operationStage": "执行唯一一次自动整稿返工",
            }
        return {
            "shortStoryNeedsGeneration": False,
            "pendingRevision": None,
            "operationStep": "merge_short_story_reviews",
            "operationStage": "合并中短篇全稿审核结论",
        }

    def route_after_merge(state: GraphState) -> str:
        return (
            "generateShortStory"
            if state.get("shortStoryNeedsGeneration")
            else "markShortStoryAwaitingUser"
        )

    async def mark_awaiting(state: GraphState) -> dict[str, Any]:
        reviews = _reviews_by_agent(state)
        if set(reviews) != set(_REVIEWERS):
            raise ValueError(
                "SHORT_STORY_REVIEWS_INCOMPLETE：双审核完成前不得交给用户"
            )
        artifact_id = _required_text(state, "activeArtifactId")
        await dependencies.artifacts.mark_awaiting_user(artifact_id)
        return {
            "artifactStatus": "awaiting_user",
            "phase": "waiting_user",
            "activeAgent": "写作",
            "agentOutputs": {},
            "finalResponse": "",
            "operationStep": "mark_short_story_awaiting_user",
            "operationStage": "等待用户确认完整正文",
        }

    async def finish_decision(state: GraphState) -> dict[str, Any]:
        selected = state.get("shortStoryDecision")
        if selected not in {"approve", "discard"}:
            raise ValueError("SHORT_STORY_DECISION_INVALID：终态决定无效")
        return {
            "resumeDecision": None,
            "userDecision": selected,
            "artifactStatus": "applied" if selected == "approve" else "discarded",
            "phase": "completed",
            "agentOutputs": {},
            "finalResponse": "",
            "operationStep": "complete_short_story_decision",
            "operationStage": "完成中短篇正文决策",
        }

    builder = StateGraph(GraphState)
    builder.add_node("prepareShortStory", prepare)
    builder.add_node("generateShortStory", generate)
    builder.add_node("reviewShortStoryByEditor", review_editor)
    builder.add_node("reviewShortStoryByValidator", review_validator)
    builder.add_node("mergeShortStoryReviews", merge_reviews)
    builder.add_node("markShortStoryAwaitingUser", mark_awaiting)
    builder.add_node("finishShortStoryDecision", finish_decision)
    builder.add_edge(START, "prepareShortStory")
    builder.add_conditional_edges("prepareShortStory", route_after_prepare)
    builder.add_edge("generateShortStory", "reviewShortStoryByEditor")
    builder.add_edge("reviewShortStoryByEditor", "reviewShortStoryByValidator")
    builder.add_edge("reviewShortStoryByValidator", "mergeShortStoryReviews")
    builder.add_conditional_edges("mergeShortStoryReviews", route_after_merge)
    builder.add_edge("markShortStoryAwaitingUser", END)
    builder.add_edge("finishShortStoryDecision", END)
    return builder.compile(checkpointer=checkpointer)


async def _run_reviewer(
    dependencies: ShortStoryGraphDependencies,
    state: GraphState,
    reviewer: AgentId,
) -> dict[str, Any]:
    artifact_id = _required_text(state, "activeArtifactId")
    revision = state.get("shortStoryArtifactRevision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ValueError("SHORT_STORY_ARTIFACT_REVISION_INVALID：正文修订号无效")
    event: dict[str, Any]
    try:
        turn = await dependencies.agentExecutor.run(
            reviewer,
            dict(state),
            execution_mode="reviewer",
            operation_kind="write_short_story",
        )
    except Exception:
        event = {
            "type": "submit_evaluation",
            "verdict": "block",
            "summary": f"{reviewer}复审智能体暂时不可用",
            "requiredChanges": "请由用户审核当前完整正文，或稍后重新发起复审。",
        }
        await dependencies.artifacts.submit_evaluation(
            dict(state), artifact_id, reviewer, event
        )
    else:
        submitted_event = _evaluation_event(turn.get("controlEvents"))
        if submitted_event is None:
            event = {
                "type": "submit_evaluation",
                "verdict": "block",
                "summary": f"{reviewer}复审智能体未提交结构化结论",
                "requiredChanges": "请重新发起完整正文复审。",
            }
            await dependencies.artifacts.submit_evaluation(
                dict(state), artifact_id, reviewer, event
            )
        else:
            event = submitted_event
            await dependencies.artifacts.submit_evaluation(
                dict(state), artifact_id, reviewer, event
            )
    review = {
        "revision": revision,
        "evaluatorAgent": reviewer,
        "verdict": event["verdict"],
        "summary": event["summary"],
        "requiredChanges": event.get("requiredChanges"),
    }
    reviews = [
        item
        for item in state.get("shortStoryReviews", [])
        if isinstance(item, dict) and item.get("evaluatorAgent") != reviewer
    ]
    reviews.append(review)
    return {
        "activeAgent": reviewer,
        "shortStoryReviews": reviews,
        "operationStep": f"review_short_story_by_{'editor' if reviewer == '编辑' else 'validator'}",
        "operationStage": f"{reviewer}审核完整中短篇正文",
    }


def _evaluation_event(value: object) -> dict[str, Any] | None:
    if not isinstance(value, list):
        return None
    candidates = [
        item
        for item in value
        if isinstance(item, dict) and item.get("type") == "submit_evaluation"
    ]
    if len(candidates) != 1:
        return None
    event = dict(candidates[0])
    if event.get("verdict") not in {"pass", "revise", "block"}:
        return None
    summary = event.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    event["summary"] = summary.strip()
    required = event.get("requiredChanges")
    if required is not None and (
        not isinstance(required, str) or not required.strip()
    ):
        return None
    if isinstance(required, str):
        event["requiredChanges"] = required.strip()
    if event["verdict"] == "revise" and not event.get("requiredChanges"):
        return None
    return event


def _build_draft(
    state: Mapping[str, Any],
    content: str,
    *,
    automatic_rewrite_count: Literal[0, 1],
    generation_reason: Literal["user_request", "automatic_rewrite"],
) -> ShortStoryChapterDraft:
    source = state.get("commandSource")
    if not isinstance(source, Mapping) or source.get("kind") != "approved_short_outline":
        raise ValueError("SHORT_STORY_SOURCE_INVALID：整稿生成缺少已批准大纲来源")
    planning = _planning(state)
    short_context = _short_story_context(planning)
    target_chapter = short_context.get("targetChapter")
    if not isinstance(target_chapter, Mapping):
        raise ValueError("SHORT_STORY_TARGET_INVALID：整稿上下文缺少目标正文")
    target_word_count = state.get("targetTotalWordCount")
    if target_word_count is not None and (
        isinstance(target_word_count, bool)
        or not isinstance(target_word_count, int)
        or not 6000 <= target_word_count <= 80000
    ):
        raise ValueError("SHORT_STORY_TARGET_INVALID：中短篇篇幅参考无效")
    return ShortStoryChapterDraft(
        content=content,
        metadata=ShortStoryDraftMetadata(
            sourceOutlineArtifactId=_required_mapping_text(
                source, "outlineArtifactId"
            ),
            sourceOutlineRevision=_required_positive_int(source, "outlineRevision"),
            sourceOutlineHash=_required_mapping_text(source, "outlineHash"),
            targetWordCount=target_word_count,
            actualWordCount=count_short_story_text_length(content),
            targetChapterId=_required_text(state, "chapterId"),
            baseChapterHash=_required_mapping_text(
                target_chapter, "baseContentHash"
            ),
            generationCommandId=_required_text(state, "commandId"),
            automaticRewriteCount=automatic_rewrite_count,
            generationReason=generation_reason,
        ),
    )


def _validate_run_artifact(
    state: Mapping[str, Any],
    short_context: Mapping[str, Any],
    run_artifact: Mapping[str, Any],
) -> ShortStoryChapterDraft:
    payload = ShortStoryChapterDraft.model_validate(run_artifact.get("payload"))
    source = state.get("commandSource")
    target_chapter = short_context.get("targetChapter")
    if not isinstance(source, Mapping) or not isinstance(target_chapter, Mapping):
        raise ValueError("SHORT_STORY_RUN_ARTIFACT_INVALID：权威来源上下文缺失")
    metadata = payload.metadata
    expected = (
        _required_mapping_text(source, "outlineArtifactId"),
        _required_positive_int(source, "outlineRevision"),
        _required_mapping_text(source, "outlineHash"),
        state.get("targetTotalWordCount"),
        _required_text(state, "chapterId"),
        _required_mapping_text(target_chapter, "baseContentHash"),
    )
    actual = (
        metadata.sourceOutlineArtifactId,
        metadata.sourceOutlineRevision,
        metadata.sourceOutlineHash,
        metadata.targetWordCount,
        metadata.targetChapterId,
        metadata.baseChapterHash,
    )
    if actual != expected:
        raise ValueError(
            "SHORT_STORY_RUN_ARTIFACT_INVALID：持久正文来源或目标身份已过期"
        )
    return payload


def _validate_generation_context(
    state: Mapping[str, Any], short_context: Mapping[str, Any]
) -> None:
    source = state.get("commandSource")
    approved_outline = short_context.get("approvedOutline")
    target_chapter = short_context.get("targetChapter")
    if (
        not isinstance(source, Mapping)
        or source.get("kind") != "approved_short_outline"
        or not isinstance(approved_outline, Mapping)
        or not isinstance(target_chapter, Mapping)
    ):
        raise ValueError(
            "SHORT_STORY_CONTEXT_IDENTITY_MISMATCH：整稿权威来源结构无效"
        )
    expected_outline = (
        _required_mapping_text(source, "outlineArtifactId"),
        _required_positive_int(source, "outlineRevision"),
        _required_mapping_text(source, "outlineHash"),
    )
    actual_outline = (
        _required_mapping_text(approved_outline, "artifactId"),
        _required_positive_int(approved_outline, "revision"),
        _required_mapping_text(approved_outline, "hash"),
    )
    if expected_outline != actual_outline:
        raise ValueError(
            "SHORT_STORY_CONTEXT_IDENTITY_MISMATCH：批准大纲与持久命令不一致"
        )
    target_word_count = state.get("targetTotalWordCount")
    if (
        short_context.get("targetTotalWordCount") != target_word_count
        or target_chapter.get("id") != state.get("chapterId")
    ):
        raise ValueError(
            "SHORT_STORY_CONTEXT_IDENTITY_MISMATCH：目标正文或目标字数不一致"
        )
    base_hash = target_chapter.get("baseContentHash")
    if (
        not isinstance(base_hash, str)
        or len(base_hash) != 64
        or any(character not in "0123456789abcdef" for character in base_hash)
    ):
        raise ValueError(
            "SHORT_STORY_CONTEXT_IDENTITY_MISMATCH：目标正文基线哈希无效"
        )


def _current_revision_reviews(
    artifact: Mapping[str, Any], revision: int
) -> list[dict[str, Any]]:
    raw = artifact.get("evaluations")
    if not isinstance(raw, list):
        return []
    by_agent: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping) or item.get("revision") != revision:
            continue
        evaluator = item.get("evaluatorAgent")
        verdict = item.get("verdict")
        summary = item.get("summary")
        if (
            evaluator not in _REVIEWERS
            or verdict not in {"pass", "revise", "block"}
            or not isinstance(summary, str)
            or not summary.strip()
        ):
            continue
        by_agent[cast(str, evaluator)] = {
            "revision": revision,
            "evaluatorAgent": evaluator,
            "verdict": verdict,
            "summary": summary.strip(),
            "requiredChanges": item.get("requiredChanges"),
        }
    return [by_agent[reviewer] for reviewer in _REVIEWERS if reviewer in by_agent]


def _reviews_by_agent(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    revision = state.get("shortStoryArtifactRevision")
    result: dict[str, dict[str, Any]] = {}
    for item in state.get("shortStoryReviews", []):
        if (
            isinstance(item, dict)
            and item.get("revision") == revision
            and item.get("evaluatorAgent") in _REVIEWERS
        ):
            result[str(item["evaluatorAgent"])] = item
    return result


def _decision_feedback(decision: object) -> str:
    if not isinstance(decision, Mapping):
        raise ValueError("SHORT_STORY_DECISION_INVALID：改稿决定结构无效")
    value = decision.get("userMessage")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SHORT_STORY_DECISION_INVALID：改稿必须保留用户原始要求")
    return value


def _planning(state: Mapping[str, Any]) -> Mapping[str, Any]:
    runtime = state.get("runtimeContext")
    core = runtime.get("coreContext") if isinstance(runtime, Mapping) else None
    planning = core.get("planning") if isinstance(core, Mapping) else None
    if not isinstance(planning, Mapping):
        raise ValueError("SHORT_STORY_CONTEXT_INVALID：缺少 Core 规划上下文")
    return planning


def _short_story_context(planning: Mapping[str, Any]) -> Mapping[str, Any]:
    value = planning.get("shortStoryContext")
    if not isinstance(value, Mapping):
        raise ValueError("SHORT_STORY_CONTEXT_INVALID：缺少中短篇整稿上下文")
    return value


def _require_short_story_operation(state: Mapping[str, Any]) -> None:
    operation = state.get("currentOperation")
    if (
        state.get("workflowKind") != "short_medium"
        or state.get("explicitOperation") != "write_short_story"
        or not isinstance(operation, Mapping)
        or operation.get("kind") != "write_short_story"
    ):
        raise ValueError("SHORT_STORY_OPERATION_INVALID：中短篇整稿 Operation 身份无效")


def _required_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"SHORT_STORY_CONTEXT_INVALID：缺少有效字段 {key}")
    return item.strip()


def _required_raw_text(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"SHORT_STORY_CONTEXT_INVALID：缺少有效字段 {key}")
    return item


def _required_mapping_text(value: Mapping[str, Any], key: str) -> str:
    return _required_text(value, key)


def _required_positive_int(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < 1:
        raise ValueError(f"SHORT_STORY_CONTEXT_INVALID：缺少有效字段 {key}")
    return item

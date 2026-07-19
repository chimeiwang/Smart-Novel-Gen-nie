from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class RuntimeContext(TypedDict):
    coreContext: dict[str, Any]
    runResource: dict[str, Any]


class GraphState(TypedDict, total=False):
    taskId: str
    userId: str
    novelId: str
    chapterId: str
    targetWordCount: int | None
    workflowKind: Literal["long_serial", "short_medium"]
    explicitOperation: str | None
    commandId: str
    targetTotalWordCount: int | None
    commandSource: dict[str, Any] | None
    phase: Literal["idle", "active", "waiting_user", "completed", "error"]
    userMessage: str
    currentOperation: dict[str, Any] | None
    operationStep: str
    operationStage: str | None
    contextMessages: list[str]
    executionInstructions: list[str]
    runtimeContext: RuntimeContext
    conversationHistory: list[dict[str, Any]]
    activeAgent: str | None
    agentOutputs: dict[str, dict[str, Any]]
    activeArtifactId: str | None
    artifactStatus: str
    reviewResults: Annotated[list[dict[str, Any]], operator.add]
    pendingRevision: dict[str, Any] | None
    artifactIteration: int
    maxArtifactIterations: int
    userDecision: str | None
    resumeDecision: dict[str, Any] | None
    errorMessage: str | None
    finalResponse: str
    eventSequence: int
    shortStoryDecision: str | None
    shortStoryNeedsGeneration: bool
    shortStoryAutomaticRewriteCount: int
    shortStoryGenerationReason: str | None
    shortStoryUserRequest: str | None
    shortStoryArtifactRevision: int | None
    shortStoryReviews: list[dict[str, Any]]


def create_initial_state(
    *,
    task_id: str,
    user_id: str,
    novel_id: str,
    chapter_id: str,
    user_message: str,
    target_word_count: int | None = 4000,
    workflow_kind: Literal["long_serial", "short_medium"] = "long_serial",
    explicit_operation: str | None = None,
    command_id: str = "legacy-command",
    target_total_word_count: int | None = None,
    command_source: dict[str, Any] | None = None,
) -> GraphState:
    return GraphState(
        taskId=task_id,
        userId=user_id,
        novelId=novel_id,
        chapterId=chapter_id,
        targetWordCount=target_word_count,
        workflowKind=workflow_kind,
        explicitOperation=explicit_operation,
        commandId=command_id,
        targetTotalWordCount=target_total_word_count,
        commandSource=command_source,
        phase="idle",
        userMessage=user_message,
        currentOperation=None,
        operationStep="init",
        operationStage=None,
        contextMessages=[],
        executionInstructions=[],
        conversationHistory=[],
        activeAgent=None,
        agentOutputs={},
        activeArtifactId=None,
        artifactStatus="none",
        reviewResults=[],
        pendingRevision=None,
        artifactIteration=0,
        maxArtifactIterations=5,
        userDecision=None,
        resumeDecision=None,
        errorMessage=None,
        finalResponse="",
        eventSequence=0,
    )

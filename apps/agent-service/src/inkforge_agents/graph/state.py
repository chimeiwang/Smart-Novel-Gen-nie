from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


class GraphState(TypedDict, total=False):
    taskId: str
    userId: str
    novelId: str
    chapterId: str
    targetWordCount: int
    phase: Literal["idle", "active", "waiting_user", "completed", "error"]
    userMessage: str
    currentOperation: dict[str, Any] | None
    operationStep: str
    operationStage: str | None
    contextMessages: list[str]
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


def create_initial_state(
    *,
    task_id: str,
    user_id: str,
    novel_id: str,
    chapter_id: str,
    user_message: str,
    target_word_count: int = 4000,
) -> GraphState:
    return GraphState(
        taskId=task_id,
        userId=user_id,
        novelId=novel_id,
        chapterId=chapter_id,
        targetWordCount=target_word_count,
        phase="idle",
        userMessage=user_message,
        currentOperation=None,
        operationStep="init",
        operationStage=None,
        contextMessages=[],
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

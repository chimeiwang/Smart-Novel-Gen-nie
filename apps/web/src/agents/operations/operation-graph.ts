/**
 * 创作操作图。
 *
 * LangGraph 在这里表达业务步骤，而不是围绕 Agent 身份编排。
 */

import { END, START, Send, StateGraph, getWriter } from "@langchain/langgraph";
import type { WritingState, AgentOutput, CoreAgentId, ArtifactReviewResult, OperationStep } from "@/agents/graph/state";
import { AGENT_NAMES, AGENT_TO_OUTPUT_FIELD, getArtifactReviewState, patchArtifactReviewState } from "@/agents/graph/state";
import type { GraphState, WritingStateAnnotation } from "@/agents/graph/graph-definition";
import { emit } from "@/agents/graph/sse-adapter";
import { addAgentMessage } from "@/agents/graph/context-manager";
import { getCreativeOperationLabel, type CreativeOperationKind } from "@/shared/contracts/creative-operation";
import { getOperationDefinition } from "./operation-definition";
import { executeCreativeOperation } from "./operation-executor";
import {
  applyArtifactEvaluationPatch,
  markArtifactAwaitingUser,
  submitArtifactEvaluation,
  toReviewArtifactDto,
} from "@/agents/artifacts/artifact-service";
import { markTaskAwaitingUserReview } from "@/agents/graph/task-state";
import { createArtifactReviewInterrupt } from "@/shared/contracts/user-decision";
import { interrupt as langGraphInterrupt } from "@langchain/langgraph";
import { prisma } from "@/shared/db/prisma";
import { traceWorkflowExecution } from "@/agents/lib/langsmith-tracer";
import { aggregateNovelContextForWriting } from "@/shared/lib/context-aggregator";
import { resolveChapterDraftTarget } from "./chapter-target-resolver";
import { logger } from "@/shared/lib/logger";

type OperationAgentRunner<T> = (state: WritingState) => Promise<T>;

export function buildOperationGraph(annotation: typeof WritingStateAnnotation) {
  return new StateGraph(annotation)
    .addNode("prepareOperationContext", withOperationTrace("prepare_context", prepareOperationContextNode))
    .addNode("executeOperation", withOperationTrace("execute_operation", executeOperationNode))
    .addNode("submitArtifactOrRespond", withOperationTrace("submit_or_respond", submitArtifactOrRespondNode))
    .addNode("reviewArtifact", withOperationTrace("review_artifact", reviewArtifactNode))
    .addNode("reviewArtifactWorker", withOperationTrace("review_artifact_worker", reviewArtifactWorkerNode))
    .addNode("mergeArtifactReviews", withOperationTrace("merge_artifact_reviews", mergeArtifactReviewsNode))
    .addNode("applyArtifactPatch", withOperationTrace("apply_artifact_patch", applyArtifactPatchNode))
    .addNode("reviseArtifact", withOperationTrace("revise_artifact", reviseArtifactNode))
    .addNode("awaitUserDecision", withOperationTrace("await_user_decision", awaitUserDecisionNode))
    .addNode("suggestNextAction", withOperationTrace("suggest_next_action", suggestNextActionNode))
    .addEdge(START, "prepareOperationContext")
    .addEdge("prepareOperationContext", "executeOperation")
    .addConditionalEdges("executeOperation", routeAfterExecute, OPERATION_EXECUTE_ROUTES)
    .addConditionalEdges("submitArtifactOrRespond", routeAfterSubmit, OPERATION_SUBMIT_ROUTES)
    .addConditionalEdges("reviewArtifact", routeReviewWorkers)
    .addEdge("reviewArtifactWorker", "mergeArtifactReviews")
    .addConditionalEdges("mergeArtifactReviews", routeAfterReview, OPERATION_REVIEW_ROUTES)
    .addConditionalEdges("applyArtifactPatch", routeAfterPatch, OPERATION_PATCH_ROUTES)
    .addEdge("reviseArtifact", "executeOperation")
    .addEdge("awaitUserDecision", "suggestNextAction")
    .addEdge("suggestNextAction", END)
    .compile();
}

export const OPERATION_EXECUTE_ROUTES = {
  executeOperation: "executeOperation",
  awaitUserDecision: "awaitUserDecision",
  submitArtifactOrRespond: "submitArtifactOrRespond",
} as const;

export const OPERATION_SUBMIT_ROUTES = {
  reviewArtifact: "reviewArtifact",
  suggestNextAction: "suggestNextAction",
} as const;

export const OPERATION_REVIEW_ROUTES = {
  applyArtifactPatch: "applyArtifactPatch",
  reviseArtifact: "reviseArtifact",
  awaitUserDecision: "awaitUserDecision",
  suggestNextAction: "suggestNextAction",
} as const;

export const OPERATION_PATCH_ROUTES = {
  reviewArtifact: "reviewArtifact",
  reviseArtifact: "reviseArtifact",
  awaitUserDecision: "awaitUserDecision",
  suggestNextAction: "suggestNextAction",
} as const;

export function createOperationTraceMetadata(
  state: GraphState,
  operationStage: string
): Record<string, unknown> {
  return {
    taskId: state.taskId,
    userId: state.userId,
    novelId: state.novelId,
    chapterId: state.chapterId,
    operationKind: state.currentOperation?.kind,
    operationLabel: state.currentOperation ? getCreativeOperationLabel(state.currentOperation.kind) : undefined,
    operationStage,
    primaryAgent: state.currentOperation?.primaryAgent,
    activeAgent: state.activeAgent,
    activeArtifactId: getArtifactReviewState(state).activeArtifactId,
    artifactIteration: getArtifactReviewState(state).iteration,
    service: "inkforge",
  };
}

function withOperationTrace<T extends Record<string, unknown>>(
  operationStage: string,
  node: (state: GraphState) => Promise<T>
): (state: GraphState) => Promise<T> {
  return (state) => traceWorkflowExecution(
    `operation:${operationStage}`,
    createOperationTraceMetadata(state, operationStage),
    () => node(state)
  );
}

async function prepareOperationContextNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const label = operation ? getCreativeOperationLabel(operation.kind) : "回答问题";
  emit(writer, "operation_stage", {
    stage: "准备操作上下文",
    label,
    message: `正在准备${label}所需的上下文。`,
  });
  if (operation && shouldUseWritingContext(operation.kind)) {
    const target = operation.kind === "write_chapter" || operation.kind === "rewrite_scene" || operation.kind === "plan_chapter"
      ? await resolveChapterDraftTarget({
          novelId: state.novelId,
          chapterId: state.chapterId,
          userMessage: operation.userGoal || state.userMessage,
          allowNewChapterTarget: operation.kind !== "plan_chapter",
          confirmedDecision: state.runtime?.chapterTargetDecision,
        })
      : null;
    const novelData = await aggregateNovelContextForWriting(
      state.novelId,
      target?.contextChapterId ?? state.chapterId,
      target ? {
        chapterId: target.target.mode === "existing_chapter" ? target.target.chapterId : null,
        order: target.targetOrder,
        title: target.targetTitle,
        contextAnchorChapterId: target.contextAnchorChapterId,
      } : undefined
    );
    const patchedNovelData = target
      ? {
          ...novelData,
          chapterId: target.target.mode === "existing_chapter" ? target.target.chapterId : state.chapterId,
          chapterTitle: target.targetTitle,
          chapterContent: target.targetContent,
        }
      : novelData;
    return {
      operationStage: "准备操作上下文",
      operationStep: "prepare_context" as OperationStep,
      chapterDraftTarget: target?.target ?? null,
      novelData: { ...patchedNovelData, novelId: state.novelId } as GraphState["novelData"],
    };
  }
  return { operationStage: "准备操作上下文", operationStep: "prepare_context" as OperationStep };
}

function shouldUseWritingContext(kind: CreativeOperationKind): boolean {
  return kind === "plan_chapter" ||
    kind === "write_chapter" ||
    kind === "rewrite_scene" ||
    kind === "review_chapter";
}

async function executeOperationNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const label = operation ? getCreativeOperationLabel(operation.kind) : "回答问题";
  emit(writer, "operation_stage", {
    stage: "执行创作操作",
    label,
    message: `正在执行${label}。`,
  });

  const activeAgent = state.pendingAgentCall?.toAgent ?? operation?.primaryAgent ?? state.activeAgent ?? "编辑";
  const result = await runOperationAgentWithLifecycle(
    state,
    activeAgent,
    writer,
    (stateWithLifecycle) => executeCreativeOperation(stateWithLifecycle, {
      emitEvent: (type, payload) => emit(writer, type, payload),
    })
  );
  const output = result.output;
  const history = output && !result.statePatch.conversationHistory
    ? addAgentMessage(
        { ...state, conversationHistory: state.conversationHistory } as unknown as WritingState,
        output,
        false
      ).conversationHistory
    : result.statePatch.conversationHistory ?? state.conversationHistory;

  const currentReview = getArtifactReviewState(state);
  const artifactId = result.artifact?.id ?? result.statePatch.activeArtifactId ?? currentReview.activeArtifactId;
  const artifactPatch = artifactId
    ? patchArtifactReviewState(state, {
        status: "draft_submitted",
        activeArtifactId: artifactId,
        reviewerAgent: result.statePatch.reviewerAgent ?? currentReview.reviewerAgent,
      })
    : {};
  if (result.artifact) {
    emit(writer, "artifact_submitted", {
      agentId: activeAgent,
      artifact: result.artifact,
      artifactId: result.artifact.id,
      status: result.artifact.status,
      revision: result.artifact.revision,
    });
  }

  return {
    ...result.statePatch,
    ...artifactPatch,
    conversationHistory: history,
    activeAgent,
    activeArtifactId: artifactId,
    operationStep: "execute_operation" as OperationStep,
    operationStage: "执行创作操作",
  };
}

function routeAfterExecute(state: GraphState): keyof typeof OPERATION_EXECUTE_ROUTES {
  const review = getArtifactReviewState(state);
  if (review.status === "awaiting_user" && review.activeArtifactId) return "awaitUserDecision";
  return "submitArtifactOrRespond";
}

async function submitArtifactOrRespondNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  if (!operation) return { operationStage: "整理结果", operationStep: "submit_artifact" as OperationStep };

  const def = getOperationDefinition(operation.kind);
  const label = getCreativeOperationLabel(operation.kind);
  if (!def.requiresArtifact) {
    emit(writer, "operation_stage", {
      stage: "直接回复",
      label,
      message: `${label}已完成。`,
    });
    return { operationStage: "直接回复", operationStep: "submit_artifact" as OperationStep };
  }

  emit(writer, "operation_stage", {
    stage: "提交待审核草案",
    label,
    artifactId: getArtifactReviewState(state).activeArtifactId,
    message: `${label}已生成待审核草案。`,
  });
  return { operationStage: "提交待审核草案", operationStep: "submit_artifact" as OperationStep };
}

function routeAfterSubmit(state: GraphState): keyof typeof OPERATION_SUBMIT_ROUTES {
  const operation = state.currentOperation;
  if (!operation) return "suggestNextAction";
  const def = getOperationDefinition(operation.kind);
  if (def.requiresArtifact && getArtifactReviewState(state).activeArtifactId && def.reviewers.length > 0) {
    return "reviewArtifact";
  }
  return "suggestNextAction";
}

async function reviewArtifactNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  const activeArtifactId = review.activeArtifactId;
  if (!operation || !activeArtifactId) return { operationStage: "整理结果", operationStep: "review_artifact" as OperationStep };

  const def = getOperationDefinition(operation.kind);
  if (def.reviewers.length === 0) {
    return {
      operationStage: "整理结果",
      operationStep: "review_artifact" as OperationStep,
      ...patchArtifactReviewState(state, { reviewerAgent: null }),
    };
  }
  const label = getCreativeOperationLabel(operation.kind);
  for (const reviewer of def.reviewers) {
    emit(writer, "artifact_review_started", {
      fromAgent: def.primaryAgent,
      toAgent: reviewer,
      artifactId: activeArtifactId,
      artifactKey: `${state.taskId}:${operation.kind}`,
      revision: review.iteration + 1,
      depth: review.iteration + 1,
    });
  }
  emit(writer, "operation_stage", {
    stage: "审核草案",
    label,
    message: `${def.reviewers.map((reviewer) => AGENT_NAMES[reviewer]).join("、")}正在并行审核${label}。`,
  });

  return {
    operationStage: "审核草案",
    operationStep: "review_artifact" as OperationStep,
    reviewWorkerAgent: null,
    ...patchArtifactReviewState(state, {
      status: "reviewing",
      reviewerAgent: null,
      reviserAgent: null,
      pendingRevision: null,
    }),
  };
}

export function routeReviewWorkers(
  state: GraphState
): Array<Send<"reviewArtifactWorker", Partial<GraphState>>> | "suggestNextAction" | "awaitUserDecision" {
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  if (!operation || !review.activeArtifactId) return "suggestNextAction";

  const reviewers = getOperationDefinition(operation.kind).reviewers;
  if (reviewers.length === 0) return "awaitUserDecision";

  return reviewers.map((reviewer) => new Send("reviewArtifactWorker", {
    ...state,
    reviewWorkerAgent: reviewer,
  }));
}

async function reviewArtifactWorkerNode(state: GraphState) {
  const writer = getWriter();
  const reviewer = state.reviewWorkerAgent;
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  const activeArtifactId = review.activeArtifactId;
  if (!reviewer || !operation || !activeArtifactId) {
    return { artifactReviewResults: [] as ArtifactReviewResult[] };
  }

  const reviewPatch = await runOperationAgentWithLifecycle(
    state,
    reviewer,
    writer,
    (stateWithLifecycle) => runReviewer(reviewer, stateWithLifecycle as unknown as GraphState)
  );
  const structuredEvaluation = readEvaluationEvent(reviewPatch);
  const requiredEvaluation = requireStructuredEvaluation(structuredEvaluation, reviewPatch, reviewer, state);
  const verdict = requiredEvaluation.verdict;
  const summary = requiredEvaluation.summary;
  if (!structuredEvaluation) {
    emit(writer, "agent_status", {
      agentId: reviewer,
      status: "error",
      message: summary,
    });
  }
  const requiredChanges = structuredEvaluation?.requiredChanges ?? (verdict === "pass" ? undefined : summary);
  const revisionMode = verdict === "revise" ? structuredEvaluation?.revisionMode ?? "rewrite" : "rewrite";
  const patches = verdict === "revise" ? structuredEvaluation?.patches : undefined;

  return {
    artifactReviewResults: [{
      artifactId: activeArtifactId,
      operationKind: operation.kind,
      iteration: review.iteration,
      reviewer,
      output: readReviewerOutput(reviewPatch, reviewer),
      verdict,
      summary,
      requiredChanges,
      revisionMode,
      patches,
      structured: Boolean(structuredEvaluation),
    } satisfies ArtifactReviewResult],
  };
}

async function mergeArtifactReviewsNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  const activeArtifactId = review.activeArtifactId;
  if (!operation || !activeArtifactId) return { operationStage: "整理结果", operationStep: "review_artifact" as OperationStep };

  const def = getOperationDefinition(operation.kind);
  const results = collectCurrentReviewResults(state, def.reviewers);
  const decision = decideReviewOutcome(results);
  const outputPatch = buildReviewerOutputPatch(results);
  const nextIteration = review.iteration + 1;
  const reachedMaxRevision = decision.verdict === "revise" && nextIteration >= review.maxIterations;
  const finalSummary = reachedMaxRevision
    ? decision.summary + `\n已达到最大复审轮次（${review.maxIterations}），流程停止，避免把未通过草案提交给用户确认。`
    : decision.summary;

  const lastPassIndex = decision.verdict === "pass"
    ? results.map((result) => result.verdict).lastIndexOf("pass")
    : -1;
  let artifactId = activeArtifactId;
  for (const [index, result] of results.entries()) {
    const artifact = await submitArtifactEvaluation({
      artifactId,
      evaluatorAgent: result.reviewer,
      verdict: result.verdict,
      summary: result.summary,
      requiredChanges: result.requiredChanges,
      deferPassStatus: result.verdict === "pass" && index !== lastPassIndex,
    });
    artifactId = artifact.id;
    emit(writer, "workflow_evaluation_submitted", {
      agentId: result.reviewer,
      artifactId: artifact.id,
      verdict: result.verdict,
      summary: result.summary,
    });
  }

  return {
    ...outputPatch,
    activeAgent: decision.reviewer,
    ...patchArtifactReviewState(state, {
      status: decision.verdict === "revise" && !reachedMaxRevision
        ? (decision.revisionMode === "patch" ? "patching" : "revision_requested")
        : decision.verdict === "block" || reachedMaxRevision
          ? "revision_requested"
          : "reviewing",
      activeArtifactId: artifactId,
      reviewerAgent: decision.reviewer,
      reviserAgent: decision.verdict === "revise" && decision.revisionMode === "rewrite" && !reachedMaxRevision
        ? def.primaryAgent
        : null,
      pendingRevision: decision.verdict === "revise" && !reachedMaxRevision
        ? {
            summary: finalSummary,
            requiredChanges: decision.requiredChanges,
            revisionMode: decision.revisionMode,
            patches: decision.patches,
          }
        : null,
      iteration: nextIteration,
    }),
    activeArtifactId: artifactId,
    reviewWorkerAgent: null,
    operationStep: "review_artifact" as OperationStep,
    operationStage: "审核草案",
    errorMessage: decision.verdict === "block" || reachedMaxRevision ? finalSummary : null,
    controlEvents: undefined,
  };
}

function collectCurrentReviewResults(
  state: GraphState,
  reviewers: CoreAgentId[]
): ArtifactReviewResult[] {
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  const byReviewer = new Map<CoreAgentId, ArtifactReviewResult>();
  for (const result of state.artifactReviewResults ?? []) {
    if (
      operation &&
      result.artifactId === review.activeArtifactId &&
      result.operationKind === operation.kind &&
      result.iteration === review.iteration &&
      reviewers.includes(result.reviewer)
    ) {
      byReviewer.set(result.reviewer, result);
    }
  }

  return reviewers.map((reviewer) => byReviewer.get(reviewer) ?? {
    artifactId: review.activeArtifactId ?? "",
    operationKind: operation?.kind ?? "answer_question",
    iteration: review.iteration,
    reviewer,
    output: null,
    verdict: "block",
    summary: `${AGENT_NAMES[reviewer]}没有返回复审结果，流程停止。`,
    requiredChanges: `${AGENT_NAMES[reviewer]}没有返回复审结果，需重新发起审核。`,
    revisionMode: "rewrite",
    structured: false,
  });
}

type ReviewOutcome = {
  verdict: "pass" | "revise" | "block";
  reviewer: CoreAgentId;
  summary: string;
  requiredChanges?: string;
  revisionMode: "patch" | "rewrite";
  patches?: ArtifactReviewResult["patches"];
};

export function decideReviewOutcome(results: ArtifactReviewResult[]): ReviewOutcome {
  const blockers = results.filter((result) => result.verdict === "block");
  if (blockers.length > 0) {
    return {
      verdict: "block",
      reviewer: blockers[0].reviewer,
      summary: formatReviewSummaries(blockers),
      requiredChanges: formatRequiredChanges(blockers),
      revisionMode: "rewrite",
    };
  }

  const revisers = results.filter((result) => result.verdict === "revise");
  if (revisers.length > 0) {
    const patchCandidates = revisers.filter((result) => result.revisionMode === "patch" && result.patches?.length);
    const canPatch = patchCandidates.length === revisers.length;
    return {
      verdict: "revise",
      reviewer: revisers[0].reviewer,
      summary: formatReviewSummaries(revisers),
      requiredChanges: formatRequiredChanges(revisers),
      revisionMode: canPatch ? "patch" : "rewrite",
      patches: canPatch ? patchCandidates.flatMap((result) => result.patches ?? []) : undefined,
    };
  }

  const last = results[results.length - 1];
  return {
    verdict: "pass",
    reviewer: last?.reviewer ?? "编辑",
    summary: formatReviewSummaries(results) || "所有复审 Agent 均已通过。",
    revisionMode: "rewrite",
  };
}

function formatReviewSummaries(results: ArtifactReviewResult[]): string {
  return results.map((result) => `${AGENT_NAMES[result.reviewer]}：${result.summary}`).join("\n");
}

function formatRequiredChanges(results: ArtifactReviewResult[]): string {
  return results.map((result) => `${AGENT_NAMES[result.reviewer]}：${result.requiredChanges ?? result.summary}`).join("\n");
}

function buildReviewerOutputPatch(results: ArtifactReviewResult[]): Partial<WritingState> {
  const patch: Partial<WritingState> = { agentOutputs: {} };
  for (const result of results) {
    if (!result.output) continue;
    patch[AGENT_TO_OUTPUT_FIELD[result.reviewer]] = result.output;
    patch.agentOutputs = { ...(patch.agentOutputs ?? {}), [result.reviewer]: result.output };
  }
  return patch;
}

export function routeAfterReview(state: GraphState): keyof typeof OPERATION_REVIEW_ROUTES {
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  if (state.errorMessage) return "suggestNextAction";
  if (review.pendingRevision?.revisionMode === "patch") return "applyArtifactPatch";
  if (review.reviserAgent && review.iteration < review.maxIterations) {
    return "reviseArtifact";
  }
  if (!operation) return "suggestNextAction";
  return "awaitUserDecision";
}

async function applyArtifactPatchNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  const pending = review.pendingRevision;
  const label = operation ? getCreativeOperationLabel(operation.kind) : "待审核草案";
  emit(writer, "operation_stage", {
    stage: "应用小修",
    label,
    message: `正在应用${label}的小修补丁。`,
  });

  if (!review.activeArtifactId || !pending?.patches?.length) {
    emit(writer, "operation_stage", {
      stage: "应用小修",
      label,
      message: "小修补丁缺失，改为交回主责 Agent 返工。",
    });
    return {
      operationStage: "应用小修",
      operationStep: "apply_artifact_patch" as OperationStep,
      ...patchArtifactReviewState(state, {
        status: "revision_requested",
        pendingRevision: null,
        reviserAgent: operation?.primaryAgent ?? review.reviserAgent,
      }),
    };
  }

  const result = await applyArtifactEvaluationPatch({
    artifactId: review.activeArtifactId,
    evaluatorAgent: state.activeAgent ?? review.reviewerAgent ?? "编辑",
    summary: pending.summary,
    patches: pending.patches,
    novelData: state.novelData,
  });

  if (!result.success) {
    emit(writer, "operation_stage", {
      stage: "应用小修",
      label,
      message: `小修补丁无法安全应用：${result.reason}。改为交回主责 Agent 返工。`,
    });
    return {
      operationStage: "应用小修",
      operationStep: "apply_artifact_patch" as OperationStep,
      ...patchArtifactReviewState(state, {
        status: "revision_requested",
        pendingRevision: null,
        reviserAgent: operation?.primaryAgent ?? review.reviserAgent,
      }),
    };
  }

  emit(writer, "artifact_submitted", {
    agentId: state.activeAgent ?? review.reviewerAgent ?? operation?.primaryAgent ?? "编辑",
    artifact: result.artifact,
    artifactId: result.artifact.id,
    status: result.artifact.status,
    revision: result.artifact.revision,
  });

  return {
    ...patchArtifactReviewState(state, {
      status: "reviewing",
      activeArtifactId: result.artifact.id,
      pendingRevision: null,
      reviserAgent: null,
    }),
    activeArtifactId: result.artifact.id,
    operationStep: "apply_artifact_patch" as OperationStep,
    operationStage: "应用小修",
  };
}

export function routeAfterPatch(state: GraphState): keyof typeof OPERATION_PATCH_ROUTES {
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  if (state.errorMessage) return "suggestNextAction";
  if (review.reviserAgent && review.iteration < review.maxIterations) {
    return "reviseArtifact";
  }
  if (operation && review.activeArtifactId && getOperationDefinition(operation.kind).reviewers.length > 0) {
    return "reviewArtifact";
  }
  return "awaitUserDecision";
}

async function reviseArtifactNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const review = getArtifactReviewState(state);
  const label = operation ? getCreativeOperationLabel(operation.kind) : "待审核草案";
  emit(writer, "operation_stage", {
    stage: "返工草案",
    label,
    message: `正在根据审核意见返工${label}。`,
  });
  return {
    operationStage: "返工草案",
    operationStep: "revise_artifact" as OperationStep,
    ...patchArtifactReviewState(state, {
      status: "revision_requested",
      reviserAgent: null,
      pendingRevision: null,
    }),
    pendingAgentCall: operation
      ? {
          fromAgent: state.activeAgent ?? "编辑",
          toAgent: operation.primaryAgent,
          reason: `${label}需要继续修改`,
          specificQuestion: review.pendingRevision?.requiredChanges ??
            review.pendingRevision?.summary ??
            state.editorOutput?.content ??
            state.validatorOutput?.content ??
            "请根据审核意见继续修改草案。",
          timestamp: Date.now(),
        }
      : state.pendingAgentCall,
    activeAgent: operation?.primaryAgent ?? state.activeAgent,
  };
}

async function awaitUserDecisionNode(state: GraphState) {
  const writer = getWriter();
  const review = getArtifactReviewState(state);
  const activeArtifactId = review.activeArtifactId;
  if (!activeArtifactId || !state.currentOperation) return { operationStage: "整理结果", operationStep: "await_user_decision" as OperationStep };
  const label = getCreativeOperationLabel(state.currentOperation.kind);
  await markArtifactAwaitingUser({ artifactId: activeArtifactId });
  const awaitingState = {
    ...state,
    ...patchArtifactReviewState(state, {
      status: "awaiting_user",
      activeArtifactId,
      pendingRevision: null,
      reviserAgent: null,
    }),
    operationStep: "await_user_decision" as OperationStep,
    operationStage: "等待用户决策",
  } as GraphState;
  await markTaskAwaitingUserReview({
    taskId: state.taskId,
    artifactId: activeArtifactId,
    state: awaitingState,
    operationStage: "等待用户决策",
  });
  const artifactRecord = await prisma.reviewArtifact.findUnique({
    where: { id: activeArtifactId },
    include: { evaluations: { orderBy: { createdAt: "desc" } } },
  });
  const artifact = artifactRecord ? toReviewArtifactDto(artifactRecord) : undefined;
  emit(writer, "operation_stage", {
    stage: "等待用户决策",
    label,
    artifactId: activeArtifactId,
    message: `${label}已通过审核，等待你确认。`,
  });
  const dedupKey = artifactRecord
    ? state.taskId + ":artifact_awaiting_user:" + artifactRecord.id + ":rev" + artifactRecord.revision
    : state.taskId + ":artifact_awaiting_user:" + activeArtifactId;
  emit(writer, "artifact_awaiting_user_approval", {
    agentId: state.activeAgent ?? state.currentOperation.primaryAgent,
    artifactId: activeArtifactId,
    dedupKey,
    artifact,
  });
  langGraphInterrupt(createArtifactReviewInterrupt({
    artifactId: activeArtifactId,
    artifact,
    summary: `${label}已通过审核，请决定是否应用到项目。`,
    content: `${label}已生成待审核草案。`,
  }));
  return awaitingState;
}

async function suggestNextActionNode(state: GraphState) {
  const writer = getWriter();
  const label = state.currentOperation ? getCreativeOperationLabel(state.currentOperation.kind) : "创作操作";
  emit(writer, "operation_stage", {
    stage: "建议下一步",
    label,
    message: `${label}流程已整理完成。`,
  });
  return { operationStage: "建议下一步", operationStep: "completed" as OperationStep, phase: "completed" };
}

async function runReviewer(reviewer: CoreAgentId, state: GraphState): Promise<Partial<WritingState>> {
  const nodes = await import("@/agents/graph/nodes");
  const map: Record<CoreAgentId, keyof typeof nodes> = {
    "设定": "loreAdvisorNode",
    "剧情": "plotAdvisorNode",
    "写作": "authorNode",
    "校验": "validatorNode",
    "编辑": "editorNode",
  };
  const node = nodes[map[reviewer]] as (s: WritingState) => Promise<Partial<WritingState>>;
  return node({
    ...state,
    activeAgent: reviewer,
    operationMode: "operation_graph",
    pendingAgentCall: {
      fromAgent: state.currentOperation?.primaryAgent ?? "编辑",
      toAgent: reviewer,
      reason: "请审核待审核草案",
      specificQuestion: "请读取当前待审核草案，给出是否可以提交给用户确认的审核结论。",
      timestamp: Date.now(),
    },
  } as unknown as WritingState);
}

function inferReviewVerdict(
  patch: Partial<WritingState>,
  reviewer: CoreAgentId
): "pass" | "revise" | "block" {
  const output = readReviewerOutput(patch, reviewer);
  const text = output?.content ?? "";
  if (/阻塞|无法通过|严重冲突/.test(text)) return "block";
  if (/需要修改|继续修改|返工|不通过|未通过|问题/.test(text)) return "revise";
  return "pass";
}

function inferReviewSummary(
  patch: Partial<WritingState>,
  reviewer: CoreAgentId
): string {
  const output = readReviewerOutput(patch, reviewer);
  const text = output?.content?.trim();
  return text ? text.slice(0, 1000) : `${AGENT_NAMES[reviewer]}审核通过。`;
}

function readReviewerOutput(
  patch: Partial<WritingState>,
  reviewer: CoreAgentId
): AgentOutput | null {
  if (reviewer === "校验") return patch.validatorOutput ?? null;
  if (reviewer === "编辑") return patch.editorOutput ?? null;
  if (reviewer === "设定") return patch.loreAdvisorOutput ?? null;
  if (reviewer === "剧情") return patch.plotAdvisorOutput ?? null;
  return patch.writerOutput ?? null;
}

export function readEvaluationEvent(
  patch: Partial<WritingState>
): {
  verdict: "pass" | "revise" | "block";
  summary: string;
  requiredChanges?: string;
  revisionMode?: "patch" | "rewrite";
  patches?: NonNullable<WritingState["pendingArtifactRevision"]>["patches"];
} | null {
  const event = patch.controlEvents?.find((item) => item.type === "submit_evaluation");
  if (!event || event.type !== "submit_evaluation") return null;
  return {
    verdict: event.verdict,
    summary: event.summary,
    requiredChanges: event.requiredChanges,
    revisionMode: event.revisionMode,
    patches: event.patches,
  };
}

export function requireStructuredEvaluation(
  evaluation: ReturnType<typeof readEvaluationEvent>,
  patch: Partial<WritingState>,
  reviewer: CoreAgentId,
  state?: Pick<GraphState, "taskId" | "activeArtifactId" | "currentOperation" | "artifactIteration">
): NonNullable<ReturnType<typeof readEvaluationEvent>> {
  if (evaluation) return evaluation;
  const proseSummary = inferReviewSummary(patch, reviewer);
  logger.warn("OPERATION_WORKFLOW", "复审 Agent 未提交 submit_evaluation，停止正文推断", {
    taskId: state?.taskId,
    artifactId: state?.activeArtifactId,
    reviewer,
    operationKind: state?.currentOperation?.kind,
    artifactIteration: state?.artifactIteration,
  });
  return {
    verdict: "block",
    summary: `复审未完成：${AGENT_NAMES[reviewer]}没有调用 submit_evaluation 提交结构化审核结论。请重新发起审核或让复审 Agent 补交 pass/revise/block 结论。${proseSummary ? `\n\n原始报告摘要：${proseSummary}` : ""}`,
  };
}

export async function runOperationAgentWithLifecycle<T>(
  state: GraphState,
  agentId: CoreAgentId,
  writer: ((chunk: unknown) => void) | undefined,
  run: OperationAgentRunner<T>
): Promise<T> {
  const startTime = Date.now();
  const agentName = AGENT_NAMES[agentId];
  const directStreamCallback = state.streamCallbacks?.[agentId];
  const directEventCallback = state.eventCallbacks?.[agentId];
  const workflowTrace = state.runtime?.workflowTrace;
  const agentCallId = workflowTrace?.allocateAgentCallId(agentId);
  const stateRef = workflowTrace?.captureState(state, `${agentCallId ?? agentId} 输入状态`);

  const sendEvent = (type: string, payload: Record<string, unknown>) => {
    if (directEventCallback) {
      directEventCallback(type, payload);
      return;
    }
    emit(writer, type, { agentId, ...payload });
  };

  sendEvent("agent_start", { agentId, agentName, agentCallId, stateRef });

  const stateWithCallbacks = {
    ...state,
    activeAgent: agentId,
    runtime: state.runtime ? {
      ...state.runtime,
      workflowTrace: workflowTrace ? {
        ...workflowTrace,
        agentCallId,
        stateRef,
      } : undefined,
    } : undefined,
    streamCallbacks: {
      ...state.streamCallbacks,
      [agentId]: (chunk: string) => {
        if (directStreamCallback) {
          directStreamCallback(chunk);
          return;
        }
        emit(writer, "agent_chunk", { agentId, chunk });
      },
    },
    eventCallbacks: {
      ...state.eventCallbacks,
      [agentId]: (type: string, payload: Record<string, unknown>) => {
        sendEvent(type, payload);
      },
    },
  } as unknown as WritingState;

  const result = await run(stateWithCallbacks);
  const output = readLifecycleOutput(agentId, result);
  sendEvent("agent_done", {
    agentId,
    agentName,
    agentCallId,
    stateRef,
    durationMs: Date.now() - startTime,
    hasOutput: !!output,
    content: output?.content ?? "",
    insights: output?.insights ?? [],
    proactiveSuggestions: output?.proactiveSuggestions ?? [],
    scores: output?.scores,
    qualityGate: output?.qualityGate,
    rewriteBrief: output?.rewriteBrief,
  });

  return result;
}

function readLifecycleOutput(agentId: CoreAgentId, result: unknown): AgentOutput | null {
  if (!result || typeof result !== "object") return null;
  const maybeOperationResult = result as { output?: unknown };
  if (maybeOperationResult.output && typeof maybeOperationResult.output === "object") {
    return maybeOperationResult.output as AgentOutput;
  }
  return readReviewerOutput(result as Partial<WritingState>, agentId);
}

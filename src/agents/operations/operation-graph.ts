/**
 * 创作操作图。
 *
 * LangGraph 在这里表达业务步骤，而不是围绕 Agent 身份编排。
 */

import { END, START, StateGraph, getWriter } from "@langchain/langgraph";
import type { WritingState, AgentOutput, CoreAgentId } from "@/agents/graph/state";
import { AGENT_NAMES } from "@/agents/graph/state";
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
    .addNode("applyArtifactPatch", withOperationTrace("apply_artifact_patch", applyArtifactPatchNode))
    .addNode("reviseArtifact", withOperationTrace("revise_artifact", reviseArtifactNode))
    .addNode("awaitUserDecision", withOperationTrace("await_user_decision", awaitUserDecisionNode))
    .addNode("suggestNextAction", withOperationTrace("suggest_next_action", suggestNextActionNode))
    .addEdge(START, "prepareOperationContext")
    .addEdge("prepareOperationContext", "executeOperation")
    .addConditionalEdges("executeOperation", routeAfterExecute, OPERATION_EXECUTE_ROUTES)
    .addConditionalEdges("submitArtifactOrRespond", routeAfterSubmit, OPERATION_SUBMIT_ROUTES)
    .addConditionalEdges("reviewArtifact", routeAfterReview, OPERATION_REVIEW_ROUTES)
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
  reviewArtifact: "reviewArtifact",
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
    activeArtifactId: state.activeArtifactId,
    artifactIteration: state.artifactIteration,
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
        })
      : null;
    const novelData = await aggregateNovelContextForWriting(state.novelId, target?.contextChapterId ?? state.chapterId);
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
      chapterDraftTarget: target?.target ?? null,
      novelData: { ...patchedNovelData, novelId: state.novelId } as GraphState["novelData"],
    };
  }
  return { operationStage: "准备操作上下文" };
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

  const artifactId = result.artifact?.id ?? result.statePatch.activeArtifactId ?? state.activeArtifactId;
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
    conversationHistory: history,
    activeAgent,
    activeArtifactId: artifactId,
    operationStage: "执行创作操作",
  };
}

function routeAfterExecute(state: GraphState): keyof typeof OPERATION_EXECUTE_ROUTES {
  if (state.pendingUserResponse && state.activeArtifactId) return "awaitUserDecision";
  return "submitArtifactOrRespond";
}

async function submitArtifactOrRespondNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  if (!operation) return { operationStage: "整理结果" };

  const def = getOperationDefinition(operation.kind);
  const label = getCreativeOperationLabel(operation.kind);
  if (!def.requiresArtifact) {
    emit(writer, "operation_stage", {
      stage: "直接回复",
      label,
      message: `${label}已完成。`,
    });
    return { operationStage: "直接回复" };
  }

  emit(writer, "operation_stage", {
    stage: "提交待审核草案",
    label,
    artifactId: state.activeArtifactId,
    message: `${label}已生成待审核草案。`,
  });
  return { operationStage: "提交待审核草案" };
}

function routeAfterSubmit(state: GraphState): keyof typeof OPERATION_SUBMIT_ROUTES {
  const operation = state.currentOperation;
  if (!operation) return "suggestNextAction";
  const def = getOperationDefinition(operation.kind);
  if (def.requiresArtifact && state.activeArtifactId && def.reviewers.length > 0) {
    return "reviewArtifact";
  }
  return "suggestNextAction";
}

async function reviewArtifactNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  if (!operation || !state.activeArtifactId) return { operationStage: "整理结果" };

  const def = getOperationDefinition(operation.kind);
  const reviewer = selectCurrentReviewer(state, def.reviewers);
  if (!reviewer) return { operationStage: "整理结果", reviewerAgent: null };
  const label = getCreativeOperationLabel(operation.kind);
  emit(writer, "artifact_review_started", {
    fromAgent: def.primaryAgent,
    toAgent: reviewer,
    artifactId: state.activeArtifactId,
    artifactKey: `${state.taskId}:${operation.kind}`,
    revision: state.artifactIteration + 1,
    depth: state.artifactIteration + 1,
  });
  emit(writer, "operation_stage", {
    stage: "审核草案",
    label,
    message: `${AGENT_NAMES[reviewer]}正在审核${label}。`,
  });

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
  const artifact = await submitArtifactEvaluation({
    artifactId: state.activeArtifactId,
    evaluatorAgent: reviewer,
    verdict,
    summary,
    requiredChanges,
  });

  emit(writer, "workflow_evaluation_submitted", {
    agentId: reviewer,
    artifactId: artifact.id,
    verdict,
    summary,
  });

  return {
    ...reviewPatch,
    activeAgent: reviewer,
    activeArtifactId: artifact.id,
    operationStage: "审核草案",
    artifactIteration: state.artifactIteration + 1,
    errorMessage: verdict === "block" ? summary : null,
    reviewerAgent: reviewer,
    reviserAgent: verdict === "revise" && revisionMode === "rewrite" ? def.primaryAgent : null,
    pendingArtifactRevision: verdict === "revise"
      ? { summary, requiredChanges, revisionMode, patches }
      : null,
    controlEvents: undefined,
  };
}

export function routeAfterReview(state: GraphState): keyof typeof OPERATION_REVIEW_ROUTES {
  const operation = state.currentOperation;
  if (state.errorMessage) return "suggestNextAction";
  if (state.pendingArtifactRevision?.revisionMode === "patch") return "applyArtifactPatch";
  if (state.reviserAgent && state.artifactIteration < state.maxArtifactIterations) {
    return "reviseArtifact";
  }
  if (operation && hasNextReviewer(state, getOperationDefinition(operation.kind).reviewers)) {
    return "reviewArtifact";
  }
  return "awaitUserDecision";
}

export function selectCurrentReviewer(
  state: GraphState,
  reviewers: CoreAgentId[]
): CoreAgentId | null {
  if (state.reviewerAgent) {
    const currentIndex = reviewers.indexOf(state.reviewerAgent);
    const nextReviewer = reviewers[currentIndex + 1];
    if (nextReviewer) return nextReviewer;
    if (currentIndex >= 0) return null;
  }
  return reviewers[0] ?? null;
}

export function hasNextReviewer(state: GraphState, reviewers: CoreAgentId[]): boolean {
  if (!state.reviewerAgent) return reviewers.length > 0;
  const currentIndex = reviewers.indexOf(state.reviewerAgent);
  return currentIndex >= 0 && currentIndex < reviewers.length - 1;
}

async function applyArtifactPatchNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const pending = state.pendingArtifactRevision;
  const label = operation ? getCreativeOperationLabel(operation.kind) : "待审核草案";
  emit(writer, "operation_stage", {
    stage: "应用小修",
    label,
    message: `正在应用${label}的小修补丁。`,
  });

  if (!state.activeArtifactId || !pending?.patches?.length) {
    emit(writer, "operation_stage", {
      stage: "应用小修",
      label,
      message: "小修补丁缺失，改为交回主责 Agent 返工。",
    });
    return {
      operationStage: "应用小修",
      pendingArtifactRevision: null,
      reviserAgent: operation?.primaryAgent ?? state.reviserAgent,
    };
  }

  const result = await applyArtifactEvaluationPatch({
    artifactId: state.activeArtifactId,
    evaluatorAgent: state.activeAgent ?? state.reviewerAgent ?? "编辑",
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
      pendingArtifactRevision: null,
      reviserAgent: operation?.primaryAgent ?? state.reviserAgent,
    };
  }

  emit(writer, "artifact_submitted", {
    agentId: state.activeAgent ?? state.reviewerAgent ?? operation?.primaryAgent ?? "编辑",
    artifact: result.artifact,
    artifactId: result.artifact.id,
    status: result.artifact.status,
    revision: result.artifact.revision,
  });

  return {
    activeArtifactId: result.artifact.id,
    operationStage: "应用小修",
    pendingArtifactRevision: null,
    reviserAgent: null,
  };
}

export function routeAfterPatch(state: GraphState): keyof typeof OPERATION_PATCH_ROUTES {
  const operation = state.currentOperation;
  if (state.errorMessage) return "suggestNextAction";
  if (state.reviserAgent && state.artifactIteration < state.maxArtifactIterations) {
    return "reviseArtifact";
  }
  if (operation && hasNextReviewer(state, getOperationDefinition(operation.kind).reviewers)) {
    return "reviewArtifact";
  }
  return "awaitUserDecision";
}

async function reviseArtifactNode(state: GraphState) {
  const writer = getWriter();
  const operation = state.currentOperation;
  const label = operation ? getCreativeOperationLabel(operation.kind) : "待审核草案";
  emit(writer, "operation_stage", {
    stage: "返工草案",
    label,
    message: `正在根据审核意见返工${label}。`,
  });
  return {
    operationStage: "返工草案",
    reviserAgent: null,
    pendingArtifactRevision: null,
    pendingAgentCall: operation
      ? {
          fromAgent: state.activeAgent ?? "编辑",
          toAgent: operation.primaryAgent,
          reason: `${label}需要继续修改`,
          specificQuestion: state.editorOutput?.content ?? state.validatorOutput?.content ?? "请根据审核意见继续修改草案。",
          timestamp: Date.now(),
        }
      : state.pendingAgentCall,
    activeAgent: operation?.primaryAgent ?? state.activeAgent,
  };
}

async function awaitUserDecisionNode(state: GraphState) {
  const writer = getWriter();
  if (!state.activeArtifactId || !state.currentOperation) return { operationStage: "整理结果" };
  const label = getCreativeOperationLabel(state.currentOperation.kind);
  await markArtifactAwaitingUser({ artifactId: state.activeArtifactId });
  await markTaskAwaitingUserReview({
    taskId: state.taskId,
    artifactId: state.activeArtifactId,
    state,
    operationStage: "等待用户决策",
  });
  const artifactRecord = await prisma.reviewArtifact.findUnique({
    where: { id: state.activeArtifactId },
    include: { evaluations: { orderBy: { createdAt: "desc" } } },
  });
  const artifact = artifactRecord ? toReviewArtifactDto(artifactRecord) : undefined;
  emit(writer, "operation_stage", {
    stage: "等待用户决策",
    label,
    artifactId: state.activeArtifactId,
    message: `${label}已通过审核，等待你确认。`,
  });
  emit(writer, "artifact_awaiting_user_approval", {
    agentId: state.activeAgent ?? state.currentOperation.primaryAgent,
    artifactId: state.activeArtifactId,
    artifact,
  });
  langGraphInterrupt(createArtifactReviewInterrupt({
    artifactId: state.activeArtifactId,
    artifact,
    summary: `${label}已通过审核，请决定是否应用到项目。`,
    content: `${label}已生成待审核草案。`,
  }));
  return { operationStage: "等待用户决策" };
}

async function suggestNextActionNode(state: GraphState) {
  const writer = getWriter();
  const label = state.currentOperation ? getCreativeOperationLabel(state.currentOperation.kind) : "创作操作";
  emit(writer, "operation_stage", {
    stage: "建议下一步",
    label,
    message: `${label}流程已整理完成。`,
  });
  return { operationStage: "建议下一步", phase: "completed" };
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

  const sendEvent = (type: string, payload: Record<string, unknown>) => {
    if (directEventCallback) {
      directEventCallback(type, payload);
      return;
    }
    emit(writer, type, { agentId, ...payload });
  };

  sendEvent("agent_start", { agentId, agentName });

  const stateWithCallbacks = {
    ...state,
    activeAgent: agentId,
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

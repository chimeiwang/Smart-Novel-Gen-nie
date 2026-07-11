/**
 * LangGraph 图定义
 *
 * @module agents/graph/graph-definition
 * @description Phase 5 拆分：StateGraph 节点、边、条件路由的定义。
 *  从 executor.ts 拆出，不含 HTTP/SSE/持久化逻辑。
 *
 * @phase Phase 5 — 拆分 LangGraph 执行器
 */

import { StateGraph, StateSchema, ReducedValue, UntrackedValue, START, END, MemorySaver, getWriter } from "@langchain/langgraph";
import { z } from "zod";
import type { WritingState, AgentOutput, CoreAgentId, AgentMessage, AgentUpdates, AgentControlEvent, WritingPhase, ArtifactReviewState, ArtifactReviewResult, OperationStep, WritingRuntimeContext } from "./state";
import {
  CORE_AGENT_IDS,
  AGENT_NAMES,
  createDefaultArtifactReviewState,
} from "./state";
import { addUserMessage } from "./context-manager";
import { emit } from "./sse-adapter";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import { getCreativeOperationLabel } from "@/shared/contracts/creative-operation";
import { buildOperationGraph } from "@/agents/operations/operation-graph";
import { routeCreativeOperation } from "@/agents/operations/operation-router";
import { getAgentObservabilityConfig } from "@/shared/env";
import { logger } from "@/shared/lib/logger";
import { CheckpointCleanupScheduler } from "./checkpoint-lifecycle";

// ============================================
// 常量
// ============================================

// ============================================
// 状态定义
// ============================================

export const mergeAgentMessagesForState = (current: AgentMessage[], next: AgentMessage[] | undefined): AgentMessage[] => {
  // 当前所有节点都提交经过截断/压缩后的完整历史；next 必须是权威值，
  // 否则 reducer 会把已截断的旧消息重新保留下来，导致 checkpoint 无界增长。
  return next ?? current;
};
const mergeAgentOutputs = (
  current: Partial<Record<CoreAgentId, AgentOutput>>,
  next: Partial<Record<CoreAgentId, AgentOutput>> | undefined
) => ({ ...current, ...(next ?? {}) });
const mergeArtifactReviewResults = (
  current: ArtifactReviewResult[],
  next: ArtifactReviewResult[] | undefined
) => current.concat(next ?? []);

export const WritingStateAnnotation = new StateSchema({
  taskId: z.string(),
  userId: z.string(),
  novelId: z.string(),
  chapterId: z.string(),
  targetWordCount: z.number(),
  phase: z.custom<WritingPhase>(),
  userMessage: z.string(),

  // Legacy facade kept for existing routes/frontends. artifactReview.status is the authority.
  pendingUserResponse: z.boolean().default(false),

  conversationHistory: new ReducedValue<AgentMessage[], AgentMessage[]> (
    z.custom<AgentMessage[]>().default(() => []),
    {
      inputSchema: z.custom<AgentMessage[]>(),
      reducer: mergeAgentMessagesForState,
    }
  ),
  activeAgent: z.custom<CoreAgentId | null>().nullable(),
  currentOperation: z.custom<CreativeOperation | null>().nullable(),
  operationMode: z.custom<WritingState["operationMode"]>(),
  operationStep: z.custom<OperationStep>().default("init"),
  operationStage: z.string().nullable().default(null),
  chapterDraftTarget: z.custom<WritingState["chapterDraftTarget"]>().nullable().default(null),

  agentOutputs: new ReducedValue<Partial<Record<CoreAgentId, AgentOutput>>, Partial<Record<CoreAgentId, AgentOutput>>>(
    z.custom<Partial<Record<CoreAgentId, AgentOutput>>>().default(() => ({})),
    {
      inputSchema: z.custom<Partial<Record<CoreAgentId, AgentOutput>>>(),
      reducer: mergeAgentOutputs,
    }
  ),

  // Legacy fixed fields remain as facades while nodes migrate to agentOutputs.
  loreAdvisorOutput: z.custom<AgentOutput | null>().nullable(),
  plotAdvisorOutput: z.custom<AgentOutput | null>().nullable(),
  writerOutput: z.custom<AgentOutput | null>().nullable(),
  validatorOutput: z.custom<AgentOutput | null>().nullable(),
  editorOutput: z.custom<AgentOutput | null>().nullable(),

  generatedContent: z.string().default(""),
  pendingUpdates: z.custom<AgentUpdates | null>().nullable(),

  // Large request context: available during a run, excluded from checkpoint.
  novelData: new UntrackedValue<WritingState["novelData"]>(undefined, { guard: false }),
  runtime: new UntrackedValue<WritingRuntimeContext | undefined>(undefined, { guard: false }),

  pendingAgentCall: z.custom<WritingState["pendingAgentCall"]>().nullable(),
  errorMessage: z.string().nullable(),

  // Legacy runtime callback facade. Kept untracked so checkpoints stay serializable.
  streamCallbacks: new UntrackedValue<Record<string, (chunk: string) => void>>(undefined, { guard: false }),
  eventCallbacks: new UntrackedValue<Record<string, (type: string, payload: Record<string, unknown>) => void> | undefined>(undefined, { guard: false }),

  qualityCheckId: z.string().nullable(),
  // control events 在当前执行节点内消费，不参与 checkpoint 或跨请求恢复。
  controlEvents: new UntrackedValue<AgentControlEvent[] | undefined>(undefined, { guard: false }),

  artifactReview: z.custom<ArtifactReviewState>().default(() => createDefaultArtifactReviewState()),

  // Legacy artifact review facade fields. artifactReview is the authority.
  activeArtifactId: z.string().nullable().default(null),
  artifactMode: z.custom<"none" | "review_loop">().default("none"),
  reviewerAgent: z.custom<CoreAgentId | null>().nullable().default(null),
  reviewWorkerAgent: z.custom<CoreAgentId | null>().nullable().default(null),
  artifactReviewResults: new ReducedValue<ArtifactReviewResult[], ArtifactReviewResult[]>(
    z.custom<ArtifactReviewResult[]>().default(() => []),
    {
      inputSchema: z.custom<ArtifactReviewResult[]>(),
      reducer: mergeArtifactReviewResults,
    }
  ),
  reviserAgent: z.custom<CoreAgentId | null>().nullable().default(null),
  pendingArtifactRevision: z.custom<WritingState["pendingArtifactRevision"]>().nullable().default(null),
  artifactIteration: z.number().default(0),
  maxArtifactIterations: z.number().default(5),
});

export type GraphState = typeof WritingStateAnnotation.State;
export type WritingGraphState = GraphState;
export type WritingGraphInput = GraphState;
export type WritingGraphOutput = Partial<GraphState>;

// ============================================
// 图编译（单例）
// ============================================

let _compiledGraph: ReturnType<typeof buildGraph> | null = null;
let _memorySaver: MemorySaver | null = null;
const _checkpointCleanupScheduler = new CheckpointCleanupScheduler();

export function getGraph() {
  if (!_compiledGraph) {
    _compiledGraph = buildGraph();
  }
  return _compiledGraph;
}

export async function deleteGraphThreadCheckpoint(threadId: string): Promise<void> {
  _checkpointCleanupScheduler.cancel(threadId);
  const config = getAgentObservabilityConfig();
  if (!config.langGraphMemorySaverCleanupOnDone) return;
  await _memorySaver?.deleteThread(threadId);
}

export function cancelGraphThreadCheckpointCleanup(threadId: string): void {
  _checkpointCleanupScheduler.cancel(threadId);
}

export function scheduleGraphThreadCheckpointCleanup(threadId: string): void {
  const config = getAgentObservabilityConfig();
  if (config.langGraphMemorySaverTtlMs <= 0) return;

  _checkpointCleanupScheduler.schedule({
    threadId,
    ttlMs: config.langGraphMemorySaverTtlMs,
    cleanup: async (expiredThreadId) => {
      await _memorySaver?.deleteThread(expiredThreadId);
      logger.info("WORKFLOW", "LangGraph MemorySaver checkpoint TTL 已清理", {
        taskId: expiredThreadId,
        ttlMs: config.langGraphMemorySaverTtlMs,
      });
    },
    onError: (error, expiredThreadId) => {
      logger.warn("WORKFLOW", "LangGraph MemorySaver checkpoint TTL 清理失败", {
        taskId: expiredThreadId,
        error: error instanceof Error ? error.message : String(error),
      });
    },
  });
}

/**
 * 编译 LangGraph StateGraph
 *
 * 节点：initSession → operationWorkflow 子图 → END，或 initSession → statusReport → END。
 * 创作操作图负责业务步骤、草案、审核、返工和用户确认。
 */
function buildGraph() {
  const operationWorkflow = buildOperationGraph(WritingStateAnnotation);
  const graph = new StateGraph(WritingStateAnnotation)
    .addNode("initSession", initSessionNode)
    .addNode("operationWorkflow", operationWorkflow)
    .addNode("statusReport", statusReportNode)

    .addEdge(START, "initSession")
    .addConditionalEdges("initSession", routeAfterInit, {
      operationWorkflow: "operationWorkflow",
      statusReport: "statusReport",
    })

    .addEdge("operationWorkflow", END)
    .addEdge("statusReport", END);

  // MemorySaver 是 interrupt/resume 的运行依赖，不是可关闭的监控面。
  // 项目当前不承诺停机恢复或多实例恢复，持久业务状态仍以 WritingTask DB 记录为准。
  _memorySaver = new MemorySaver();
  return graph.compile({ checkpointer: _memorySaver });
}

// ============================================
// 路由
// ============================================

function routeAfterInit(state: GraphState): string {
  if (!state.currentOperation) return "statusReport";
  return "operationWorkflow";
}

// ============================================
// initSession Node
// ============================================

async function initSessionNode(state: GraphState) {
  const writer = getWriter();
  const userMessage = state.userMessage;

  const updatedState = addUserMessage(state as unknown as WritingState, userMessage);
  emit(writer, "classifying_intent", { message: "正在识别创作操作..." });
  emit(writer, "agent_status", {
    agentId: "system",
    status: "thinking",
    message: "正在识别创作操作...",
  });
  const classifyStart = Date.now();
  const routed = await routeCreativeOperation({
    userMessage,
    userId: state.userId,
    novelId: state.novelId,
  });
  const classifyDurationMs = Date.now() - classifyStart;
  const currentOperation = routed.operation;
  const resolvedAgent = currentOperation.primaryAgent;
  const label = getCreativeOperationLabel(currentOperation.kind);

  emit(writer, "operation_classified", {
    operation: currentOperation,
    rawMessage: userMessage,
  });
  emit(writer, "intent_classified", {
    targetAgent: resolvedAgent,
    operation: currentOperation,
    confidence: currentOperation.confidence,
    reasoning: routed.reasoning,
    rawMessage: userMessage,
  });

  emit(writer, "command_parsed", {
    targetAgent: resolvedAgent,
    operation: currentOperation,
    rawMessage: userMessage,
  });
  emit(writer, "operation_stage", {
    stage: "识别创作操作",
    label,
    message: `已识别为${label}，耗时 ${classifyDurationMs}ms。`,
  });
  emit(writer, "agent_status", {
    agentId: "system",
    status: "completed",
    message: `已识别为${label}，耗时 ${classifyDurationMs}ms。`,
  });

  return {
    conversationHistory: updatedState.conversationHistory,
    activeAgent: resolvedAgent,
    currentOperation,
    operationMode: "operation_graph" as const,
    operationStep: "classify_operation" as OperationStep,
    operationStage: "识别创作操作",
  };
}

// ============================================
// statusReport Node
// ============================================

async function statusReportNode(state: GraphState) {
  const writer = getWriter();
  const lines: string[] = [];
  lines.push("## 当前状态");
  lines.push("");
  lines.push(`小说：${state.novelData.novelName}`);
  lines.push(`章节：${state.novelData.chapterTitle}`);
  lines.push(`对话历史：${state.conversationHistory.length} 条`);
  lines.push("");

  const lastAgent = state.conversationHistory
    .filter((m) => m.agentOutput)
    .slice(-1)[0];
  if (lastAgent) {
    lines.push(`最近活跃 Agent：${lastAgent.agentName}`);
    lines.push("");
  }

  lines.push("### 可用 Agent");
  for (const id of CORE_AGENT_IDS) {
    lines.push(`- @${id}：${AGENT_NAMES[id]}`);
  }

  const report = lines.join("\n");
  emit(writer, "status_report", { content: report });
  return { phase: "idle" as WritingPhase };
}

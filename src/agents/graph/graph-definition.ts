/**
 * LangGraph 图定义
 *
 * @module agents/graph/graph-definition
 * @description Phase 5 拆分：StateGraph 节点、边、条件路由的定义。
 *  从 executor.ts 拆出，不含 HTTP/SSE/持久化逻辑。
 *
 * @phase Phase 5 — 拆分 LangGraph 执行器
 */

import { StateGraph, Annotation, START, END, MemorySaver, getWriter } from "@langchain/langgraph";
import type { WritingState, AgentOutput, CoreAgentId, AgentMessage, AgentUpdates, AgentControlEvent, WritingPhase } from "./state";
import {
  CORE_AGENT_IDS,
  AGENT_NAMES,
} from "./state";
import { addUserMessage } from "./context-manager";
import { emit } from "./sse-adapter";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import { getCreativeOperationLabel } from "@/shared/contracts/creative-operation";
import { buildOperationGraph } from "@/agents/operations/operation-graph";
import { routeCreativeOperation } from "@/agents/operations/operation-router";
import { getAgentObservabilityConfig } from "@/shared/env";

// ============================================
// 常量
// ============================================

// ============================================
// 状态定义
// ============================================

export const WritingStateAnnotation = Annotation.Root({
  taskId: Annotation<string>,
  userId: Annotation<string>,
  novelId: Annotation<string>,
  chapterId: Annotation<string>,
  targetWordCount: Annotation<number>,
  phase: Annotation<WritingPhase>,
  userMessage: Annotation<string>,
  pendingUserResponse: Annotation<boolean>,
  conversationHistory: Annotation<AgentMessage[]>,
  activeAgent: Annotation<CoreAgentId | null>,
  currentOperation: Annotation<CreativeOperation | null>,
  operationMode: Annotation<WritingState["operationMode"]>,
  operationStage: Annotation<string | null>,
  loreAdvisorOutput: Annotation<AgentOutput | null>,
  plotAdvisorOutput: Annotation<AgentOutput | null>,
  writerOutput: Annotation<AgentOutput | null>,
  validatorOutput: Annotation<AgentOutput | null>,
  editorOutput: Annotation<AgentOutput | null>,
  generatedContent: Annotation<string>,
  pendingUpdates: Annotation<AgentUpdates | null>,
  novelData: Annotation<WritingState["novelData"]>,
  pendingAgentCall: Annotation<WritingState["pendingAgentCall"]>,
  errorMessage: Annotation<string | null>,
  streamCallbacks: Annotation<Record<string, (chunk: string) => void>>,
  eventCallbacks: Annotation<Record<string, (type: string, payload: Record<string, unknown>) => void> | undefined>,
  qualityCheckId: Annotation<string | null>,
  controlEvents: Annotation<AgentControlEvent[] | undefined>,
  activeArtifactId: Annotation<string | null>,
  artifactMode: Annotation<"none" | "review_loop">,
  reviewerAgent: Annotation<CoreAgentId | null>,
  reviserAgent: Annotation<CoreAgentId | null>,
  artifactIteration: Annotation<number>,
  maxArtifactIterations: Annotation<number>,
});

export type GraphState = typeof WritingStateAnnotation.State;

// ============================================
// 图编译（单例）
// ============================================

let _compiledGraph: ReturnType<typeof buildGraph> | null = null;
let _memorySaver: MemorySaver | null = null;

export function getGraph() {
  if (!_compiledGraph) {
    _compiledGraph = buildGraph();
  }
  return _compiledGraph;
}

export async function deleteGraphThreadCheckpoint(threadId: string): Promise<void> {
  const config = getAgentObservabilityConfig();
  if (!config.langGraphMemorySaverEnabled || !config.langGraphMemorySaverCleanupOnDone) return;
  await _memorySaver?.deleteThread(threadId);
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

  // MemorySaver 只用于当前进程内的 LangGraph interrupt/resume。
  // 项目当前不承诺停机恢复或多实例恢复，持久业务状态仍以 WritingTask DB 记录为准。
  const config = getAgentObservabilityConfig();
  if (!config.langGraphMemorySaverEnabled) {
    _memorySaver = null;
    return graph.compile();
  }

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
  const routed = await routeCreativeOperation({
    userMessage,
    userId: state.userId,
    novelId: state.novelId,
  });
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
    message: `已识别为${label}。`,
  });

  return {
    conversationHistory: updatedState.conversationHistory,
    activeAgent: resolvedAgent,
    currentOperation,
    operationMode: "operation_graph" as const,
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

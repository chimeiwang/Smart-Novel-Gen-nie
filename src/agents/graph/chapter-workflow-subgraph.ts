/**
 * 章节生产 / 审核 / 返工子图。
 *
 * @module agents/graph/chapter-workflow-subgraph
 * @description 承载 Agent 执行、control event 处理、ReviewArtifact 复审与返工循环。
 */

import { StateGraph, END, getWriter } from "@langchain/langgraph";
import type { RetryPolicy } from "@langchain/langgraph";
import type { WritingState, AgentOutput, CoreAgentId, AgentControlEvent, WritingPhase } from "./state";
import {
  AGENT_NAMES,
  AGENT_TO_OUTPUT_FIELD,
} from "./state";
import { logger } from "@/shared/lib/logger";
import { traceAgentExecution, createTraceMetadata } from "@/agents/lib/langsmith-tracer";
import { emit } from "./sse-adapter";
import { processControlEvents } from "./control-event-processor";
import { mapAgentToNode, toGraphCommand } from "./command-router";
import { addAgentMessage } from "./context-manager";
import type { GraphState, WritingStateAnnotation } from "./graph-definition";

export const MAX_CALL_CHAIN_DEPTH = 20;
export const AGENT_TIMEOUT_MS = 300000;

export const AGENT_RETRY_POLICY: RetryPolicy = {
  maxAttempts: 3,
  initialInterval: 2000,
  backoffFactor: 2,
  maxInterval: 30000,
};

export function buildChapterWorkflowSubgraph(
  annotation: typeof WritingStateAnnotation
) {
  return new StateGraph(annotation)
    .addNode("loreAdvisor", agentNode("设定"), { retryPolicy: AGENT_RETRY_POLICY })
    .addNode("plotAdvisor", agentNode("剧情"), { retryPolicy: AGENT_RETRY_POLICY })
    .addNode("author", agentNode("写作"), { retryPolicy: AGENT_RETRY_POLICY })
    .addNode("validator", agentNode("校验"), { retryPolicy: AGENT_RETRY_POLICY })
    .addNode("editor", agentNode("编辑"), { retryPolicy: AGENT_RETRY_POLICY })
    .addNode("processResult", processResultNode, {
      ends: ["loreAdvisor", "plotAdvisor", "author", "validator", "editor", END],
    })
    .addConditionalEdges("__start__", routeToActiveAgent, {
      loreAdvisor: "loreAdvisor",
      plotAdvisor: "plotAdvisor",
      author: "author",
      validator: "validator",
      editor: "editor",
      end: END,
    })
    .addEdge("loreAdvisor", "processResult")
    .addEdge("plotAdvisor", "processResult")
    .addEdge("author", "processResult")
    .addEdge("validator", "processResult")
    .addEdge("editor", "processResult")
    .compile();
}

function routeToActiveAgent(state: GraphState) {
  return mapAgentToNode(state.activeAgent);
}

function agentNode(agentId: CoreAgentId) {
  return async (state: GraphState) => {
    const writer = getWriter();
    const startTime = Date.now();
    const agentName = AGENT_NAMES[agentId];
    const directStreamCallback = state.streamCallbacks?.[agentId];
    const directEventCallback = state.eventCallbacks?.[agentId];

    if (directEventCallback) {
      directEventCallback("agent_start", { agentId, agentName });
    } else {
      emit(writer, "agent_start", { agentId, agentName });
    }

    const node = await importAgentNode(agentId);
    if (!node) {
      throw new Error(`Agent 节点不存在: ${agentId}`);
    }

    const stateWithCallbacks = {
      ...state,
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
          if (directEventCallback) {
            directEventCallback(type, payload);
            return;
          }
          emit(writer, type, { agentId, ...payload });
        },
      },
    };

    const result = await traceAgentExecution(
      agentId,
      createTraceMetadata({
        taskId: state.taskId, novelId: state.novelId,
        chapterId: state.chapterId, agentId, callType: "agent_execution",
      }),
      async () => {
        return await withTimeout(
          node(stateWithCallbacks as unknown as WritingState),
          AGENT_TIMEOUT_MS,
          `Agent ${agentName} 执行超时`
        );
      }
    );

    const durationMs = Date.now() - startTime;
    const outputField = AGENT_TO_OUTPUT_FIELD[agentId];
    const output = (result as Record<string, unknown>)[outputField] as AgentOutput | null;

    const donePayload = {
      type: "agent_done",
      agentId, agentName, durationMs,
      hasOutput: !!output,
      content: output?.content ?? "",
      insights: output?.insights ?? [],
      proactiveSuggestions: output?.proactiveSuggestions ?? [],
      scores: output?.scores,
      qualityGate: output?.qualityGate,
      rewriteBrief: output?.rewriteBrief,
    };

    if (directEventCallback) {
      directEventCallback("agent_done", donePayload);
    } else {
      emit(writer, "agent_done", donePayload);
    }

    return { ...result, activeAgent: agentId };
  };
}

async function processResultNode(state: GraphState) {
  const writer = getWriter();
  const activeAgent = state.activeAgent;
  if (!activeAgent) return toGraphCommand({ nextAgent: null });

  const outputField = AGENT_TO_OUTPUT_FIELD[activeAgent];
  const output = (state as Record<string, unknown>)[outputField] as AgentOutput | null;
  if (!output) return toGraphCommand({ nextAgent: null });

  const updatedHistory = addAgentMessage(
    { ...state, conversationHistory: state.conversationHistory } as unknown as WritingState,
    output, false
  ).conversationHistory;

  if (output.insights && output.insights.length > 0) {
    emit(writer, "agent_insights", { agentId: activeAgent, insights: output.insights });
  }
  if (output.proactiveSuggestions && output.proactiveSuggestions.length > 0) {
    emit(writer, "proactive_suggestions", { agentId: activeAgent, suggestions: output.proactiveSuggestions });
  }

  const controlEvents = (state as Record<string, unknown>).controlEvents as AgentControlEvent[] | undefined;
  if (controlEvents && controlEvents.length > 0) {
    const result = await processControlEvents(
      {
        events: controlEvents,
        state: {
          taskId: state.taskId,
          chapterId: state.chapterId,
          qualityCheckId: state.qualityCheckId,
          callChainDepth: state.callChainDepth,
          novelData: state.novelData,
        },
        activeAgent,
        output,
        updatedHistory,
      },
      {
        emitEvent: (type, payload) => emit(writer, type, payload),
        maxCallChainDepth: MAX_CALL_CHAIN_DEPTH,
      }
    );
    return toGraphCommand(result);
  }

  return toGraphCommand({
    conversationHistory: updatedHistory,
    nextAgent: null,
    controlEvents: undefined,
  });
}

async function importAgentNode(
  agentId: CoreAgentId
): Promise<((state: WritingState) => Promise<Partial<WritingState>>) | null> {
  try {
    const nodes = await import("./nodes");
    const map: Record<string, string> = {
      "设定": "loreAdvisorNode", "剧情": "plotAdvisorNode",
      "写作": "authorNode", "校验": "validatorNode", "编辑": "editorNode",
    };
    const key = map[agentId];
    return key ? (nodes as Record<string, (s: WritingState) => Promise<Partial<WritingState>>>)[key] ?? null : null;
  } catch (error) {
    logger.error("GRAPH", `导入 Agent 节点失败: ${agentId}`, { error: String(error) });
    return null;
  }
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      }
    );
  });
}

export type ChapterWorkflowPhase = WritingPhase;

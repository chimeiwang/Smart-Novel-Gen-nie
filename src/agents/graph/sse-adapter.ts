/**
 * SSE 适配器
 *
 * @module agents/graph/sse-adapter
 * @description Phase 5 拆分：LangGraph event → 前端 SSE event 的转换层。
 *  从 executor.ts 拆出，独立可测试。
 *
 * @phase Phase 5 — 拆分 LangGraph 执行器
 */

import { CORE_AGENT_IDS, AGENT_NAMES, AGENT_TO_OUTPUT_FIELD } from "./state";
import type { AgentOutput } from "./state";
import type { GraphState } from "./graph-definition";
import { logger } from "@/shared/lib/logger";

// ============================================
// 常量
// ============================================

import type { StreamMode } from "@langchain/langgraph";
import type { WorkflowEventFileLogger } from "./workflow-event-log";

export const SSE_HEADERS = {
  "Content-Type": "text/event-stream",
  "Cache-Control": "no-cache, no-transform",
  "Connection": "keep-alive",
  "X-Accel-Buffering": "no",
} as const;

export const STREAM_MODES: StreamMode[] = ["updates", "custom"];

export type SendEventFn = (type: string, data?: Record<string, unknown>) => void;

// ============================================
// 直接流式回调
// ============================================

/** 为每个 Agent 创建直接流式回调（用于 streamCallbacks）。只承载段落文本 chunk。 */
export function createDirectStreamCallbacks(sendEvent: SendEventFn): Record<string, (chunk: string) => void> {
  const callbacks: Record<string, (chunk: string) => void> = {};

  for (const agentId of CORE_AGENT_IDS) {
    callbacks[agentId] = (chunk: string) => {
      for (const char of Array.from(chunk)) {
        sendEvent("agent_chunk", { agentId, chunk: char });
      }
    };
  }

  return callbacks;
}

/** 为每个 Agent 创建结构化事件回调（用于 eventCallbacks）。 */
export function createDirectEventCallbacks(
  sendEvent: SendEventFn
): Record<string, (type: string, payload: Record<string, unknown>) => void> {
  const callbacks: Record<string, (type: string, payload: Record<string, unknown>) => void> = {};

  for (const agentId of CORE_AGENT_IDS) {
    callbacks[agentId] = (type, payload) => {
      sendEvent(type, { agentId, ...payload });
    };
  }

  return callbacks;
}

// ============================================
// 状态更新过滤
// ============================================

/**
 * 过滤状态更新中的敏感/冗余字段
 */
export function sanitizeStateUpdate(update: Record<string, unknown>): Record<string, unknown> {
  const allowedKeys = [
    "phase", "activeAgent", "nextAgent", "callChainDepth",
    "pendingUserResponse", "errorMessage",
  ];
  const sanitized: Record<string, unknown> = {};
  for (const key of allowedKeys) {
    if (key in update) sanitized[key] = update[key];
  }
  sanitized.changedKeys = Object.keys(update);
  return sanitized;
}

// ============================================
// agent_done 回退
// ============================================

/**
 * 从 state 中提取 agent_done 负载
 */
export function getAgentDonePayloadFromState(state: GraphState): Record<string, unknown> | null {
  const agentId = state.activeAgent;
  if (!agentId) return null;

  const outputField = AGENT_TO_OUTPUT_FIELD[agentId];
  const output = (state as Record<string, unknown>)[outputField] as AgentOutput | null;
  if (!output || !output.content) return null;

  return {
    agentId,
    agentName: AGENT_NAMES[agentId],
    durationMs: 0,
    hasOutput: true,
    content: output.content,
    insights: output.insights ?? [],
    proactiveSuggestions: output.proactiveSuggestions ?? [],
    scores: output.scores,
    qualityGate: output.qualityGate,
    rewriteBrief: output.rewriteBrief,
    source: "final_state_fallback",
  };
}

/**
 * 发送 agent_done 回退事件（interrupt 场景下 graph 不会发出 agent_done）
 */
export function sendAgentDoneFallback(
  state: GraphState,
  sendEvent: SendEventFn,
  sentKeys: Set<string>
): void {
  const payload = getAgentDonePayloadFromState(state);
  if (!payload) return;

  const key = `${payload.agentId}:${String(payload.content).length}`;
  if (sentKeys.has(key)) return;

  sendEvent("agent_done", payload);
}

// ============================================
// SSE 控制器
// ============================================

/**
 * 创建 SSE 事件处理器
 *
 * 处理 LangGraph streamEvents 返回的 event stream：
 * - "updates" → 过滤后转发 state_update
 * - "custom" / "on_custom_event" → 转发 getWriter() 发出的业务事件
 * - "interrupt" → 转发 user_input_required 并停止
 */
export function createSSEController(sendEvent: SendEventFn, auditLog?: WorkflowEventFileLogger) {
  return {
    handleEvent(rawEvent: unknown): "continue" | "interrupt" | "done" {
      auditLog?.recordLangGraphEvent(rawEvent);

      const event = rawEvent as Record<string, unknown>;
      const eventType = event.event as string;

      if (eventType === "updates") {
        const data = event.data as Record<string, Record<string, unknown>>;
        for (const [nodeName, update] of Object.entries(data)) {
          if (update && Object.keys(update).length > 0) {
            sendEvent("state_update", { node: nodeName, ...sanitizeStateUpdate(update) });
          }
        }
        return "continue";
      }

      if (eventType === "custom") {
        const data = event.data as Record<string, unknown>;
        const name = (data.event as string) || "custom";
        logger.info("SSE", `自定义事件: ${name}`, { name, dataKeys: Object.keys(data).join(",") });
        sendEvent(name, data);
        return "continue";
      }

      if (eventType === "on_custom_event") {
        const data = event.data as Record<string, unknown>;
        const name = (data.event as string) || (event.name as string) || "custom";
        logger.info("SSE", `自定义事件(on_custom_event): ${name}`, { name, dataKeys: Object.keys(data ?? {}).join(",") });
        sendEvent(name, data);
        return "continue";
      }

      if (eventType === "interrupt") {
        sendEvent("user_input_required", event.data as Record<string, unknown>);
        return "interrupt";
      }

      const interruptPayload = extractInterruptPayload(event);
      if (interruptPayload) {
        sendEvent("user_input_required", interruptPayload);
        return "interrupt";
      }

      return "continue";
    },
  };
}

// ============================================
// 辅助
// ============================================

/** 向 LangGraph writer 发送命名事件 */
function extractInterruptPayload(event: Record<string, unknown>): Record<string, unknown> | null {
  const data = event.data as Record<string, unknown> | undefined;
  const direct = getInterruptValue(data?.__interrupt__);
  if (direct) return direct;

  const chunk = data?.chunk;
  if (Array.isArray(chunk) && chunk.length >= 2 && chunk[0] === "updates") {
    const update = chunk[1] as Record<string, unknown> | undefined;
    return getInterruptValue(update?.__interrupt__);
  }

  return null;
}

function getInterruptValue(raw: unknown): Record<string, unknown> | null {
  if (!raw) return null;
  const candidate = Array.isArray(raw) ? raw[0] : raw;
  if (!candidate || typeof candidate !== "object") return null;
  const record = candidate as Record<string, unknown>;
  const value = record.value ?? record;
  if (!value || typeof value !== "object") return null;
  return value as Record<string, unknown>;
}

export function emit(
  w: ((chunk: unknown) => void) | undefined,
  event: string,
  data?: Record<string, unknown>
) {
  if (w) w({ event, ...data });
}

/**
 * Agent Runtime 单轮执行结果
 *
 * @module agents/runtime/turn-result
 * @description 定义 AgentRuntime.runTurn() 的返回值结构。
 *   visibleContent 给用户看（段落文本），controlEvents 给服务端处理。
 *
 * Phase C 返工：Control Event 类型改为从 agent-control.ts 重导出，
 *   避免两套类型系统分歧。唯一数据源是 shared/contracts/agent-control.ts。
 *
 * @phase Phase 0 — 协议和接口落地（Phase C 返工）
 */

// ============================================
// Control Event 类型（从 agent-control.ts 重导出）
// ============================================

// 唯一数据源
import type {
  AgentControlEvent,
} from "@/shared/contracts/agent-control";

export type {
  QualityReportEvent,
  QualityScores,
  ProposalUpdatesEvent,
  BeatPlanProposalEvent,
  ValidationReportEvent,
  ConflictItem,
  AgentControlEvent,
} from "@/shared/contracts/agent-control";

// ============================================
// 工具调用记录
// ============================================

/** 单次工具调用记录（用于调试和追踪） */
export interface RuntimeToolCallRecord {
  /** 工具名称 */
  name: string;
  /** 工具类型 */
  toolKind: "read" | "proposal" | "control" | "mutating";
  /** 调用参数 */
  args: Record<string, unknown>;
  /** 调用时间戳 */
  timestamp: number;
}

/** 单次工具结果记录 */
export interface RuntimeToolResultRecord {
  /** 工具名称 */
  name: string;
  /** 执行结果（文本或结构化 JSON） */
  result: string;
  /** 结果时间戳 */
  timestamp: number;
}

// ============================================
// Token 用量
// ============================================

/** LLM Token 用量 */
export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
  cachedTokens?: number;
  totalTokens: number;
}

// ============================================
// AgentTurnResult
// ============================================

/**
 * Agent 单轮执行结果
 *
 * 由 AgentRuntime.runTurn() 返回。
 * - visibleContent：给前端渲染的段落文本（不套 JSON 外壳）
 * - controlEvents：给服务端（control-event-processor / LangGraph）处理的结构化控制事件
 * - toolCalls/toolResults：用于调试和追踪
 *
 * 注意：visibleContent 和 controlEvents 的来源严格分离。
 *   visibleContent 来自 assistant content（段落文本），
 *   controlEvents 来自 control 类型 tool_calls 的参数。
 *   前端不应从 visibleContent 中解析业务协议。
 */
export interface AgentTurnResult {
  /** 用户可见内容（段落文本） */
  visibleContent: string;

  /** 控制事件列表（来自 control tool calls） */
  controlEvents: AgentControlEvent[];

  /** 工具调用记录（所有类型） */
  toolCalls: RuntimeToolCallRecord[];

  /** 工具结果记录 */
  toolResults: RuntimeToolResultRecord[];

  /** Token 用量 */
  usage?: TokenUsage;

  /** 完成原因 */
  finishReason?: string;
}

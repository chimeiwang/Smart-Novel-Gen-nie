/**
 * Agent 定义类型
 *
 * @module agents/runtime/agent-definition
 * @description Phase 4 核心抽象：每个 Agent 通过声明式配置定义，
 *  AgentRunner 统一负责执行管道（消息构建 → 工具调用 → 流式输出 → 解析 → 错误处理）。
 *
 * @phase Phase 4 — AgentDefinition + AgentRunner
 */

import type { OpenAI } from "openai";
import type { AgentOutput, CoreAgentId, WritingState } from "../graph/state";
import type { AgentUpdateSection } from "@/shared/contracts/agent-updates";
import type { ModelCallProfile, ModelReasoningEffort } from "./model-runtime";

/**
 * Agent 输出模式。
 * 只允许段落文本正文 + control tools。旧 JSON 信封模式已从主路径移除。
 */
export type AgentOutputMode = "paragraph_text_with_control_tools";

// ============================================
// AgentDefinition
// ============================================

/**
 * Agent 声明式定义
 *
 * 替代原来在每个 Agent node 中重复的 ~200 行模板代码。
 * AgentRunner 根据此定义统一执行。
 */
export interface AgentDefinition {
  /** Agent ID */
  id: CoreAgentId;
  /** Agent 中文名 */
  name: string;
  /** WritingState 中对应的输出字段 */
  outputField: keyof WritingState;
  /** 日志标识（用于 logger.info 的 tag） */
  logTag: string;

  /**
   * 输出模式。保留字段是为了让配置显式声明协议；旧 JSON 信封模式已删除。
   */
  outputMode: AgentOutputMode;

  // ---- 工具配置 ----

  /**
   * 能力域列表。
   * AgentRunner 按此从 registry 派生 OpenAI tools。
   */
  toolCapabilities: string[];
  /** 最大工具调用轮次（默认 10） */
  maxIterations?: number;
  /** 模型调用预算档位。 */
  modelProfile?: ModelCallProfile;
  /** 供应商原生推理强度，不通过 system prompt 暴露思考过程。 */
  reasoningEffort?: ModelReasoningEffort;
  /** 成功调用后立即结束 Agent 回合的 control tools。 */
  terminalControlTools?: string[];

  // ---- 上下文构建 ----

  /**
   * 构建 LLM 消息列表
   * 每个 Agent 有自己的 system prompt、summary index、对话历史组装方式
   */
  buildMessages: (state: WritingState) => OpenAI.Chat.ChatCompletionMessageParam[];

  // ---- 可选钩子 ----

  /**
   * 执行前守卫：返回 { skip: true, ... } 时跳过执行
   * 用于内容不足、条件不满足等场景
   */
  preGuard?: (state: WritingState) => { skip: boolean; skipMessage?: string; skipOutput?: Partial<WritingState> } | null;

  /**
   * 流式字段名已废弃：新协议直接流式输出段落文本。
   * @deprecated 不再读取。
   */
  streamFieldName?: string;

  /**
   * 执行后处理钩子（Phase 7：作家特有逻辑收归此处）
   *
   * AgentRunner 返回基础 state partial 后调用。
   * 用于正文提取、草案准备、校验触发检测等 Agent 特有的后处理逻辑。
   */
  postProcess?: (output: AgentOutput, state: WritingState) => Partial<WritingState> | Promise<Partial<WritingState>>;

  /**
   * 允许的 updates section（Phase 2：按 Agent 限域）。
   * 不声明则不允许生成任何 updates。sanitize 时只保留白名单内的 section。
   */
  allowedUpdateSections?: AgentUpdateSection[];

  /** 状态通知文案 */
  statusMessages?: {
    understanding?: string;
    thinking?: string;
    responding?: string;
    parsing?: string;
    querying?: string;
  };
}

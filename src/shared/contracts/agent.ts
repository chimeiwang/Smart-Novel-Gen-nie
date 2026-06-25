/**
 * Agent 契约（Phase 1：唯一字段来源）
 *
 * @module shared/contracts/agent
 * @description Agent ID、元信息、默认启用列表的唯一来源。
 *  替代 registry.ts 和 state.ts 中分散的 Agent 常量定义。
 *
 * @phase Phase 1 — 字段契约统一
 */

import { z } from "zod";

// ============================================
// Agent ID
// ============================================

export const ALL_CORE_AGENT_IDS = [
  "设定",
  "剧情",
  "写作",
  "校验",
  "编辑",
] as const;

export const CoreAgentIdSchema = z.enum(ALL_CORE_AGENT_IDS);
export type CoreAgentId = z.infer<typeof CoreAgentIdSchema>;

// ============================================
// Agent 元信息
// ============================================

export interface AgentMeta {
  id: CoreAgentId;
  name: string;
  description: string;
  required: boolean;
  promptFile: string;
}

export const AGENT_META_MAP: Record<CoreAgentId, AgentMeta> = {
  "设定": {
    id: "设定",
    name: "设定顾问",
    description: "讨论设定、新增/修改设定、检测设定冲突",
    required: false,
    promptFile: "设定顾问.md",
  },
  "剧情": {
    id: "剧情",
    name: "剧情顾问",
    description: "讨论剧情、修改大纲、管理剧情进度",
    required: false,
    promptFile: "剧情顾问.md",
  },
  "写作": {
    id: "写作",
    name: "作家",
    description: "根据设定、背景、大纲生成正文",
    required: false,
    promptFile: "作家.md",
  },
  "校验": {
    id: "校验",
    name: "校验员",
    description: "检查文章与设定的一致性，触发重写",
    required: false,
    promptFile: "校验员.md",
  },
  "编辑": {
    id: "编辑",
    name: "网文编辑",
    description: "评估商业性、读者兴趣、爽点节奏和章节尾钩",
    required: false,
    promptFile: "网文编辑.md",
  },
};

export const AGENT_REGISTRY: AgentMeta[] = ALL_CORE_AGENT_IDS.map(
  (id) => AGENT_META_MAP[id]
);

/** 默认启用全部 Agent（逗号分隔字符串，用于 WritingConfig） */
export const DEFAULT_ENABLED_AGENTS_STRING = ALL_CORE_AGENT_IDS.join(",");

/** 默认启用全部 Agent（数组，用于新任务创建） */
export const DEFAULT_ENABLED_AGENTS: CoreAgentId[] = [...ALL_CORE_AGENT_IDS];

// ============================================
// 编解码
// ============================================

/**
 * selectedAgents 编码：CoreAgentId[] → 逗号字符串
 */
export function encodeSelectedAgents(agents: string[]): string {
  return agents.filter((a) => CoreAgentIdSchema.safeParse(a).success).join(",");
}

/**
 * selectedAgents 解码：逗号字符串 → CoreAgentId[]
 */
export function decodeSelectedAgents(raw: string): CoreAgentId[] {
  return raw.split(",").map((s) => s.trim()).filter((s): s is CoreAgentId => CoreAgentIdSchema.safeParse(s).success);
}

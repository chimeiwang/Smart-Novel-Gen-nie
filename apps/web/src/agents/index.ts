/**
 * Agent 模块导出
 *
 * @module agents
 * @description 集中导出所有 Agent，便于外部统一引用
 *
 * ## Agent 列表
 *
 * | Agent 名称 | 文件 | 功能简介 |
 * |-----------|------|---------|
 * | PortraitAgentStream | portrait-agent-stream.ts | 文风画像生成（流式版） |
 * | PortraitAgent | portrait-agent-legacy.ts | 文风画像生成（非流式版） |
 *
 * ## 五Agent 写作系统
 *
 * | Agent | 文件 | 功能简介 |
 * |-------|------|---------|
 * | 设定顾问 | graph/nodes/lore-advisor-node.ts | 讨论/创建/修改设定 |
 * | 剧情顾问 | graph/nodes/plot-advisor-node.ts | 讨论剧情/管理大纲 |
 * | 作家 | graph/nodes/author-node.ts | 生成正文 |
 * | 校验员 | graph/nodes/validator-node.ts | 一致性检查 |
 * | 网文编辑 | graph/nodes/editor-node.ts | 商业性评审与返工建议 |
 */

// ============================================
// 客户端安全的导出（类型和注册表）
// ============================================

export type {
  AgentMeta,
  AgentContext,
  AgentResult,
  AgentUpdates,
  NovelWithContext,
  OutlineNodeData,
  PlotProgressData,
  CharacterData,
  ItemData,
  LocationData,
  FactionData,
  GlossaryData,
  ForeshadowingData,
  ReferenceData,
  ForeshadowingUpdate,
  OutlineUpdate,
  OrchestrationEvent,
  OrchestrationResult,
} from "./types";

export {
  AGENT_REGISTRY,
  getRequiredAgents,
  getOptionalAgents,
  getAgentMeta,
  getDefaultEnabledAgents,
  validateAgentSelection,
  type AgentId,
} from "./registry";

// ============================================
// 文风画像 Agent（仅服务端）
// ============================================

export { PortraitAgentStream, createPortraitAgentStream } from "./portrait-agent-stream";
export { PortraitAgent, createPortraitAgent } from "./portrait-agent-legacy";
export type { PortraitResult } from "./portrait-agent-legacy";

// ============================================
// LangGraph 工作流（仅服务端）
// ============================================

export * from "./graph";

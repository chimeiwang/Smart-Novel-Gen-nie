/**
 * Agent 公共导出（客户端安全）
 *
 * @module agents/client
 * @description 仅导出类型和注册表，不包含 Node.js 依赖
 * 可安全在客户端组件中使用
 */

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

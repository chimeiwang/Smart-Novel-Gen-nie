/**
 * Agent 注册表兼容导出层。
 *
 * Agent ID、元信息和默认启用列表的唯一来源是
 * `src/shared/contracts/agent.ts`。本文件只保留历史 import 路径。
 */

import {
  AGENT_REGISTRY as CONTRACT_AGENT_REGISTRY,
  DEFAULT_ENABLED_AGENTS,
  type AgentMeta,
  type CoreAgentId,
} from "@/shared/contracts/agent";

export const AGENT_REGISTRY: AgentMeta[] = [...CONTRACT_AGENT_REGISTRY];

export function getRequiredAgents(): AgentMeta[] {
  return AGENT_REGISTRY.filter((agent) => agent.required);
}

export function getOptionalAgents(): AgentMeta[] {
  return AGENT_REGISTRY.filter((agent) => !agent.required);
}

export function getAgentMeta(agentId: string): AgentMeta | undefined {
  return AGENT_REGISTRY.find((agent) => agent.id === agentId);
}

export function getDefaultEnabledAgents(): CoreAgentId[] {
  return [...DEFAULT_ENABLED_AGENTS];
}

export function validateAgentSelection(selectedAgents: string[]): {
  valid: boolean;
  missing: string[];
} {
  const selected = new Set(selectedAgents);
  const missing = getRequiredAgents()
    .filter((agent) => !selected.has(agent.id))
    .map((agent) => agent.id);

  return {
    valid: missing.length === 0,
    missing,
  };
}

export type AgentId = CoreAgentId;

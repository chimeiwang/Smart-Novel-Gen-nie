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

export function getDefaultEnabledAgents(): CoreAgentId[] {
  return [...DEFAULT_ENABLED_AGENTS];
}

export type AgentId = CoreAgentId;
export type OrchestrationEvent = {
  type: "host_intent";
  intent: {
    action: string;
    reason?: string;
  };
};

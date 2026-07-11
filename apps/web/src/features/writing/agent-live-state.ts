import type { CoreAgentId } from "@/shared/contracts/agent";

export type AgentLiveRun = {
  agentId: CoreAgentId;
  content: string;
  statusMessage: string;
  startedAt: number;
};

export type AgentLiveRuns = Partial<Record<CoreAgentId, AgentLiveRun>>;

export type AgentLiveAction =
  | { type: "start"; agentId: CoreAgentId; startedAt: number; statusMessage: string }
  | { type: "status"; agentId: CoreAgentId; statusMessage: string; startedAt: number }
  | { type: "chunk"; agentId: CoreAgentId; chunk: string; startedAt: number }
  | { type: "finish"; agentId: CoreAgentId }
  | { type: "reset" };

function createRun(
  agentId: CoreAgentId,
  startedAt: number,
  statusMessage = "正在处理..."
): AgentLiveRun {
  return {
    agentId,
    content: "",
    statusMessage,
    startedAt,
  };
}

export function reduceAgentLiveRuns(
  state: AgentLiveRuns,
  action: AgentLiveAction
): AgentLiveRuns {
  if (action.type === "reset") return {};

  if (action.type === "finish") {
    if (!state[action.agentId]) return state;
    const next = { ...state };
    delete next[action.agentId];
    return next;
  }

  if (action.type === "start") {
    return {
      ...state,
      [action.agentId]: createRun(
        action.agentId,
        action.startedAt,
        action.statusMessage
      ),
    };
  }

  const current = state[action.agentId] ?? createRun(action.agentId, action.startedAt);

  if (action.type === "status") {
    return {
      ...state,
      [action.agentId]: {
        ...current,
        statusMessage: action.statusMessage,
      },
    };
  }

  if (!action.chunk) return state;
  return {
    ...state,
    [action.agentId]: {
      ...current,
      content: current.content + action.chunk,
    },
  };
}

export function listAgentLiveRuns(state: AgentLiveRuns): AgentLiveRun[] {
  return Object.values(state)
    .filter((run): run is AgentLiveRun => Boolean(run))
    .sort((left, right) => left.startedAt - right.startedAt);
}

export function resolveFinalAgentContent(
  authoritativeContent: string | undefined,
  bufferedContent: string | undefined
): string {
  return authoritativeContent ?? bufferedContent ?? "";
}

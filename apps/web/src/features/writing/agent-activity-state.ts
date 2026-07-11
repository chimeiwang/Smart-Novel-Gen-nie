export type AgentActivityStatus =
  | "understanding"
  | "thinking"
  | "asking"
  | "discussing"
  | "drafting"
  | "refining"
  | "querying"
  | "responding"
  | "parsing"
  | "suggestions"
  | "completed"
  | "done"
  | "error"
  | string;

export type AgentActivityEntry = {
  id: string;
  status: AgentActivityStatus;
  label: string;
  message: string;
  agentId?: string;
  toolName?: string;
  toolLabel?: string;
  argsSummary?: string;
  resultSummary?: string;
  timestamp: number;
};

export type AgentActivityRound = {
  id: string;
  agentId: string;
  anchorMessageId?: string;
  entries: AgentActivityEntry[];
  expanded: boolean;
  running: boolean;
  completionStatus: "running" | "done" | "error";
  updatedAt: number;
};

export type AgentActivityState = {
  rounds: AgentActivityRound[];
  activeRoundIds: Record<string, string>;
};

export const EMPTY_AGENT_ACTIVITY_STATE: AgentActivityState = {
  rounds: [],
  activeRoundIds: {},
};

export type AgentActivityAction =
  | { type: "start"; agentId: string; roundId: string; now: number }
  | { type: "add"; agentId: string; roundId: string; entry: AgentActivityEntry; now: number }
  | { type: "attach"; agentId: string; messageId: string; now: number }
  | { type: "finish"; agentId?: string; status: "done" | "error"; now: number; errorEntry?: AgentActivityEntry }
  | { type: "discard"; agentId: string }
  | { type: "toggle"; roundId: string }
  | { type: "reset" };

function createRound(agentId: string, roundId: string, now: number): AgentActivityRound {
  return {
    id: roundId,
    agentId,
    entries: [],
    expanded: false,
    running: true,
    completionStatus: "running",
    updatedAt: now,
  };
}

export function reduceAgentActivityState(
  state: AgentActivityState,
  action: AgentActivityAction
): AgentActivityState {
  if (action.type === "reset") return EMPTY_AGENT_ACTIVITY_STATE;

  if (action.type === "start") {
    const previousRoundId = state.activeRoundIds[action.agentId];
    return {
      rounds: [
        ...state.rounds.filter((round) => round.id !== previousRoundId),
        createRound(action.agentId, action.roundId, action.now),
      ],
      activeRoundIds: {
        ...state.activeRoundIds,
        [action.agentId]: action.roundId,
      },
    };
  }

  if (action.type === "add") {
    const activeRoundId = state.activeRoundIds[action.agentId] ?? action.roundId;
    const hasRound = state.rounds.some((round) => round.id === activeRoundId);
    const rounds = hasRound
      ? state.rounds
      : [...state.rounds, createRound(action.agentId, activeRoundId, action.now)];
    return {
      rounds: rounds.map((round) =>
        round.id === activeRoundId
          ? {
              ...round,
              entries: [...round.entries, action.entry],
              running: true,
              completionStatus: action.entry.status === "error" ? "error" : round.completionStatus,
              updatedAt: action.now,
            }
          : round
      ),
      activeRoundIds: {
        ...state.activeRoundIds,
        [action.agentId]: activeRoundId,
      },
    };
  }

  if (action.type === "attach") {
    const activeRoundId = state.activeRoundIds[action.agentId];
    if (!activeRoundId) return state;
    return {
      ...state,
      rounds: state.rounds.map((round) =>
        round.id === activeRoundId
          ? { ...round, anchorMessageId: action.messageId, updatedAt: action.now }
          : round
      ),
    };
  }

  if (action.type === "finish") {
    const targetAgentIds = action.agentId
      ? [action.agentId]
      : Object.keys(state.activeRoundIds);
    const targetRoundIds = new Set(targetAgentIds.flatMap((agentId) => {
      const roundId = state.activeRoundIds[agentId];
      return roundId ? [roundId] : [];
    }));
    if (targetRoundIds.size === 0) return state;
    const activeRoundIds = { ...state.activeRoundIds };
    for (const agentId of targetAgentIds) delete activeRoundIds[agentId];
    return {
      rounds: state.rounds.map((round) => {
        if (!targetRoundIds.has(round.id)) return round;
        const completionStatus = round.completionStatus === "error" ? "error" : action.status;
        return {
          ...round,
          running: false,
          expanded: false,
          completionStatus,
          updatedAt: action.now,
          entries: action.status === "error" && action.errorEntry && round.completionStatus !== "error"
            ? [...round.entries, action.errorEntry]
            : round.entries,
        };
      }),
      activeRoundIds,
    };
  }

  if (action.type === "discard") {
    const roundId = state.activeRoundIds[action.agentId];
    if (!roundId) return state;
    const activeRoundIds = { ...state.activeRoundIds };
    delete activeRoundIds[action.agentId];
    return {
      rounds: state.rounds.filter((round) => round.id !== roundId),
      activeRoundIds,
    };
  }

  return {
    ...state,
    rounds: state.rounds.map((round) =>
      round.id === action.roundId ? { ...round, expanded: !round.expanded } : round
    ),
  };
}

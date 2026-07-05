import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  EMPTY_AGENT_ACTIVITY_STATE,
  reduceAgentActivityState,
  type AgentActivityEntry,
} from "../agent-activity-state";

function entry(agentId: string, message: string, status = "querying"): AgentActivityEntry {
  return {
    id: `${agentId}-${message}`,
    agentId,
    status,
    label: status,
    message,
    timestamp: 1,
  };
}

describe("agent activity state", () => {
  it("keeps parallel reviewer activities and completion independent", () => {
    let state = reduceAgentActivityState(EMPTY_AGENT_ACTIVITY_STATE, {
      type: "start", agentId: "校验", roundId: "validator-round", now: 1,
    });
    state = reduceAgentActivityState(state, {
      type: "start", agentId: "编辑", roundId: "editor-round", now: 2,
    });
    state = reduceAgentActivityState(state, {
      type: "add", agentId: "校验", roundId: "unused", entry: entry("校验", "读取角色"), now: 3,
    });
    state = reduceAgentActivityState(state, {
      type: "add", agentId: "编辑", roundId: "unused", entry: entry("编辑", "读取章节"), now: 4,
    });
    state = reduceAgentActivityState(state, {
      type: "attach", agentId: "编辑", messageId: "editor-message", now: 5,
    });
    state = reduceAgentActivityState(state, {
      type: "finish", agentId: "编辑", status: "done", now: 6,
    });

    const validatorRound = state.rounds.find((round) => round.agentId === "校验");
    const editorRound = state.rounds.find((round) => round.agentId === "编辑");
    assert.equal(validatorRound?.running, true);
    assert.equal(validatorRound?.entries[0]?.message, "读取角色");
    assert.equal(editorRound?.running, false);
    assert.equal(editorRound?.anchorMessageId, "editor-message");
    assert.equal(state.activeRoundIds["校验"], "validator-round");
    assert.equal(state.activeRoundIds["编辑"], undefined);
  });

  it("preserves an agent error when a later done event arrives", () => {
    let state = reduceAgentActivityState(EMPTY_AGENT_ACTIVITY_STATE, {
      type: "start", agentId: "校验", roundId: "validator-round", now: 1,
    });
    state = reduceAgentActivityState(state, {
      type: "add",
      agentId: "校验",
      roundId: "unused",
      entry: entry("校验", "校验失败", "error"),
      now: 2,
    });
    state = reduceAgentActivityState(state, {
      type: "finish", agentId: "校验", status: "done", now: 3,
    });

    assert.equal(state.rounds[0]?.completionStatus, "error");
  });
});

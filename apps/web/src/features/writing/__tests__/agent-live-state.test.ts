import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  listAgentLiveRuns,
  reduceAgentLiveRuns,
  resolveFinalAgentContent,
  type AgentLiveRuns,
} from "../agent-live-state";

describe("agent live state", () => {
  it("keeps interleaved reviewer streams isolated", () => {
    let state: AgentLiveRuns = {};
    state = reduceAgentLiveRuns(state, {
      type: "start",
      agentId: "校验",
      startedAt: 1,
      statusMessage: "正在校验...",
    });
    state = reduceAgentLiveRuns(state, {
      type: "start",
      agentId: "编辑",
      startedAt: 2,
      statusMessage: "正在评审...",
    });
    state = reduceAgentLiveRuns(state, { type: "chunk", agentId: "校验", chunk: "校验一", startedAt: 1 });
    state = reduceAgentLiveRuns(state, { type: "chunk", agentId: "编辑", chunk: "编辑一", startedAt: 2 });
    state = reduceAgentLiveRuns(state, { type: "finish", agentId: "编辑" });
    state = reduceAgentLiveRuns(state, { type: "chunk", agentId: "校验", chunk: "校验二", startedAt: 1 });

    assert.equal(state["编辑"], undefined);
    assert.equal(state["校验"]?.content, "校验一校验二");
    assert.deepEqual(listAgentLiveRuns(state).map((run) => run.agentId), ["校验"]);
  });

  it("updates only the matching agent status", () => {
    let state: AgentLiveRuns = {};
    state = reduceAgentLiveRuns(state, {
      type: "status",
      agentId: "校验",
      statusMessage: "正在查询角色详情...",
      startedAt: 1,
    });

    assert.equal(state["校验"]?.statusMessage, "正在查询角色详情...");
    assert.equal(state["编辑"], undefined);
  });

  it("uses agent_done content as authoritative even when it is shorter", () => {
    assert.equal(resolveFinalAgentContent("最终报告", "混入其他 Agent 的更长缓冲内容"), "最终报告");
    assert.equal(resolveFinalAgentContent(undefined, "流式回退"), "流式回退");
  });

  it("clears every live run on reset", () => {
    const state = reduceAgentLiveRuns({
      "校验": {
        agentId: "校验",
        content: "报告",
        statusMessage: "正在输出",
        startedAt: 1,
      },
    }, { type: "reset" });

    assert.deepEqual(state, {});
  });
});

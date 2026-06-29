import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  mergeAgentMessagesForState,
  mergeControlEventsForState,
} from "../graph-definition";
import type { AgentControlEvent, AgentMessage } from "../state";

describe("LangGraph state reducers", () => {
  it("appends conversation messages without duplicating ids", () => {
    const first: AgentMessage = {
      id: "msg-1",
      agentId: "写作",
      agentName: "作家",
      content: "第一条",
      timestamp: 1,
    };
    const second: AgentMessage = {
      id: "msg-2",
      agentId: "编辑",
      agentName: "编辑",
      content: "第二条",
      timestamp: 2,
    };

    assert.deepEqual(
      mergeAgentMessagesForState([first], [first, second]).map((item) => item.id),
      ["msg-1", "msg-2"]
    );
  });

  it("appends control events and ignores undefined writes", () => {
    const first = { type: "propose_updates", updates: {}, summary: "a" } as AgentControlEvent;
    const second = {
      type: "submit_quality_report",
      scores: {},
      qualityGate: "pass",
      summary: "b",
    } as AgentControlEvent;

    assert.deepEqual(mergeControlEventsForState([first], undefined), [first]);
    assert.deepEqual(mergeControlEventsForState([first], [second]), [first, second]);
  });
});

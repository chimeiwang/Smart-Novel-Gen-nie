import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  mergeAgentMessagesForState,
} from "../graph-definition";
import type { AgentMessage } from "../state";

describe("LangGraph state reducers", () => {
  it("uses the next complete conversation history as the authoritative value", () => {
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

  it("allows a truncated history to remove old messages", () => {
    const oldMessage: AgentMessage = {
      id: "msg-old",
      agentId: "写作",
      agentName: "作家",
      content: "应被截断",
      timestamp: 1,
    };
    const retainedMessage: AgentMessage = {
      id: "msg-new",
      agentId: "编辑",
      agentName: "编辑",
      content: "保留",
      timestamp: 2,
    };

    assert.deepEqual(
      mergeAgentMessagesForState([oldMessage, retainedMessage], [retainedMessage]).map((item) => item.id),
      ["msg-new"]
    );
  });
});

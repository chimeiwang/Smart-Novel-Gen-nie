/**
 * Command router tests
 *
 * 验证 control event 处理结果可以被转换为单一 Graph 路由决策。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { isCommand } from "@langchain/langgraph";
import { mapAgentToNode, toGraphCommand, toGraphRoute } from "../command-router";

describe("mapAgentToNode", () => {
  it("maps CoreAgentId to graph node names", () => {
    assert.equal(mapAgentToNode("设定"), "loreAdvisor");
    assert.equal(mapAgentToNode("剧情"), "plotAdvisor");
    assert.equal(mapAgentToNode("写作"), "author");
    assert.equal(mapAgentToNode("校验"), "validator");
    assert.equal(mapAgentToNode("编辑"), "editor");
  });
});

describe("toGraphRoute", () => {
  it("routes to target node when nextAgent exists", () => {
    assert.equal(toGraphRoute({ nextAgent: "编辑" }), "editor");
  });

  it("routes to end when there is no nextAgent", () => {
    assert.equal(toGraphRoute({ nextAgent: null }), "end");
  });
});

describe("toGraphCommand", () => {
  it("creates a LangGraph Command with update and goto for Agent routing", () => {
    const command = toGraphCommand({
      conversationHistory: [],
      nextAgent: "编辑",
      controlEvents: undefined,
    });

    assert.equal(isCommand(command), true);
    assert.deepEqual(command.goto, ["editor"]);
    assert.deepEqual(command.update, {
      conversationHistory: [],
      nextAgent: null,
      controlEvents: undefined,
    });
  });

  it("routes to __end__ when there is no next Agent", () => {
    const command = toGraphCommand({
      conversationHistory: [],
      nextAgent: null,
      controlEvents: undefined,
    });

    assert.equal(isCommand(command), true);
    assert.deepEqual(command.goto, ["__end__"]);
    assert.deepEqual(command.update, {
      conversationHistory: [],
      nextAgent: null,
      controlEvents: undefined,
    });
  });
});

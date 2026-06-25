/**
 * Control event router tests
 *
 * 验证 control event 的控制流分类独立于具体落库、interrupt 和 SSE 副作用。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { splitControlEvents } from "../control-event-router";
import type { AgentControlEvent } from "../state";

describe("splitControlEvents", () => {
  it("separates side-effect events from route events while preserving order", () => {
    const events: AgentControlEvent[] = [
      {
        type: "submit_evaluation",
        artifactKey: "outline-1",
        verdict: "revise",
        summary: "需要返工",
      },
      {
        type: "request_revision",
        toAgent: "剧情",
        reason: "复审未通过",
        instructions: "补一个明确小赢节点。",
      },
    ];

    const result = splitControlEvents(events);

    assert.deepEqual(result.sideEffectEvents.map((event) => event.type), ["submit_evaluation"]);
    assert.equal(result.routeEvent?.type, "request_revision");
  });

  it("uses the first route event and keeps later route events out of side effects", () => {
    const events: AgentControlEvent[] = [
      {
        type: "route_to_agent",
        toAgent: "写作",
        reason: "先写正文",
      },
      {
        type: "request_revision",
        toAgent: "剧情",
        reason: "后续返工",
        instructions: "调整大纲。",
      },
    ];

    const result = splitControlEvents(events);

    assert.equal(result.routeEvent?.type, "route_to_agent");
    assert.deepEqual(result.sideEffectEvents, []);
    assert.deepEqual(result.ignoredRouteEvents.map((event) => event.type), ["request_revision"]);
  });

  it("allows propose_updates and route_to_agent in the same turn", () => {
    const events: AgentControlEvent[] = [
      {
        type: "propose_updates",
        summary: "调整前三章大纲",
        updates: {
          outlineAdjustments: [
            { action: "update", nodeTitle: "第一章", content: "强化开篇钩子" },
          ],
        },
      },
      {
        type: "route_to_agent",
        toAgent: "编辑",
        reason: "请复审大纲草案",
      },
    ];

    const result = splitControlEvents(events);

    assert.deepEqual(result.sideEffectEvents.map((event) => event.type), ["propose_updates"]);
    assert.equal(result.routeEvent?.type, "route_to_agent");
    assert.deepEqual(result.ignoredRouteEvents, []);
  });
});

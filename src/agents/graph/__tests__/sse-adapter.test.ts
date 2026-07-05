import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createDirectStreamCallbacks, createSSEController } from "../sse-adapter";

describe("createDirectStreamCallbacks", () => {
  it("forwards each provider delta as one unicode-safe SSE chunk", () => {
    const sent: Array<{ type: string; data?: Record<string, unknown> }> = [];
    const callbacks = createDirectStreamCallbacks((type, data) => {
      sent.push({ type, data });
    });

    callbacks["校验"]("校验通过🙂");

    assert.deepEqual(sent, [
      {
        type: "agent_chunk",
        data: { agentId: "校验", chunk: "校验通过🙂" },
      },
    ]);
  });
});

describe("createSSEController", () => {
  it("treats LangGraph __interrupt__ updates as a user input interrupt", () => {
    const sent: Array<{ type: string; data?: Record<string, unknown> }> = [];
    const controller = createSSEController((type, data) => {
      sent.push({ type, data });
    });

    const result = controller.handleEvent({
      event: "on_chain_stream",
      data: {
        chunk: [
          "updates",
          {
            __interrupt__: [
              {
                value: {
                  type: "user_input_required",
                  decisionType: "artifact_review",
                  artifactId: "artifact-1",
                },
              },
            ],
          },
        ],
      },
    });

    assert.equal(result, "interrupt");
    assert.deepEqual(sent, [
      {
        type: "user_input_required",
        data: {
          type: "user_input_required",
          decisionType: "artifact_review",
          artifactId: "artifact-1",
        },
      },
    ]);
  });

  it("forwards custom events emitted inside a namespaced subgraph", () => {
    const sent: Array<{ type: string; data?: Record<string, unknown> }> = [];
    const controller = createSSEController((type, data) => {
      sent.push({ type, data });
    });

    const result = controller.handleEvent({
      event: "on_chain_stream",
      data: {
        chunk: [
          ["operationWorkflow:run-1"],
          "custom",
          {
            event: "agent_start",
            agentId: "剧情",
            agentCallId: "A01",
          },
        ],
      },
    });

    assert.equal(result, "continue");
    assert.deepEqual(sent, [
      {
        type: "agent_start",
        data: {
          event: "agent_start",
          agentId: "剧情",
          agentCallId: "A01",
        },
      },
    ]);
  });

  it("forwards state updates emitted inside a namespaced subgraph", () => {
    const sent: Array<{ type: string; data?: Record<string, unknown> }> = [];
    const controller = createSSEController((type, data) => {
      sent.push({ type, data });
    });

    const result = controller.handleEvent({
      event: "on_chain_stream",
      data: {
        chunk: [
          ["operationWorkflow:run-1"],
          "updates",
          {
            executeOperation: {
              phase: "executing",
              activeAgent: "剧情",
              internalOnly: "完整内容只进入审计日志",
            },
          },
        ],
      },
    });

    assert.equal(result, "continue");
    assert.deepEqual(sent, [
      {
        type: "state_update",
        data: {
          node: "executeOperation",
          namespace: ["operationWorkflow:run-1"],
          phase: "executing",
          activeAgent: "剧情",
          changedKeys: ["phase", "activeAgent", "internalOnly"],
        },
      },
    ]);
  });

  it("treats namespaced subgraph __interrupt__ updates as a user input interrupt", () => {
    const sent: Array<{ type: string; data?: Record<string, unknown> }> = [];
    const controller = createSSEController((type, data) => {
      sent.push({ type, data });
    });

    const result = controller.handleEvent({
      event: "on_chain_stream",
      data: {
        chunk: [
          ["operationWorkflow:run-1"],
          "updates",
          {
            __interrupt__: [
              {
                value: {
                  type: "user_input_required",
                  decisionType: "artifact_review",
                  artifactId: "artifact-2",
                },
              },
            ],
          },
        ],
      },
    });

    assert.equal(result, "interrupt");
    assert.deepEqual(sent, [
      {
        type: "user_input_required",
        data: {
          type: "user_input_required",
          decisionType: "artifact_review",
          artifactId: "artifact-2",
        },
      },
    ]);
  });
});

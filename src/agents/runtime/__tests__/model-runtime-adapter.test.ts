/**
 * ModelRuntime adapter tests.
 *
 * 运行方式：npx tsx --test src/agents/runtime/__tests__/model-runtime-adapter.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyLangChainStreamChunk,
  createLangChainStreamAccumulator,
  LegacyOpenAIRuntime,
  openAIMessagesToLangChain,
  usageFromLangChain,
} from "../model-runtime";

function createStream(chunks: unknown[]): AsyncIterable<unknown> {
  return {
    async *[Symbol.asyncIterator]() {
      for (const chunk of chunks) {
        yield chunk;
      }
    },
  };
}

function createMockClient(streams: AsyncIterable<unknown>[]) {
  let calls = 0;
  return {
    get calls() {
      return calls;
    },
    chat: {
      completions: {
        create: async () => {
          const stream = streams[calls];
          calls += 1;
          if (!stream) {
            throw new Error("unexpected extra LLM call");
          }
          return stream;
        },
      },
    },
  };
}

function createBillingStub() {
  return {
    ensureCanStartModelCall: async () => ({ maxOutputTokens: 1024 }),
    chargeAiUsage: async () => {},
  };
}

describe("LangChain stream adapter", () => {
  it("maps visible content, tool call chunks, usage, and finish reason", () => {
    const accumulator = createLangChainStreamAccumulator();
    const chunks: string[] = [];

    applyLangChainStreamChunk(
      accumulator,
      {
        content: "提交草案",
        tool_call_chunks: [
          {
            index: 0,
            id: "call_",
            name: "propose_",
            args: "{\"summary\":",
          },
        ],
      },
      (chunk) => chunks.push(chunk)
    );
    applyLangChainStreamChunk(accumulator, {
      content: "并等待确认。",
      tool_call_chunks: [
        {
          index: 0,
          id: "updates",
          name: "updates",
          args: "\"新增角色\",\"updates\":{}}",
        },
      ],
      usage_metadata: {
        input_tokens: 11,
        output_tokens: 7,
        total_tokens: 18,
      },
      response_metadata: {
        finish_reason: "tool_calls",
      },
    });

    assert.equal(accumulator.content, "提交草案并等待确认。");
    assert.deepEqual(chunks, ["提交草案"]);
    assert.equal(accumulator.finishReason, "tool_calls");
    assert.deepEqual(accumulator.usage, {
      promptTokens: 11,
      completionTokens: 7,
      totalTokens: 18,
    });
    assert.deepEqual(accumulator.toolCallAccumulator.get(0), {
      id: "call_updates",
      name: "propose_updates",
      arguments: "{\"summary\":\"新增角色\",\"updates\":{}}",
    });
  });

  it("maps LangChain usage metadata into TokenUsage", () => {
    assert.deepEqual(usageFromLangChain({
      input_tokens: 3,
      output_tokens: 5,
      total_tokens: 8,
    }), {
      promptTokens: 3,
      completionTokens: 5,
      totalTokens: 8,
    });
  });
});

describe("OpenAI message adapter", () => {
  it("converts current text and tool message roles", () => {
    const messages = openAIMessagesToLangChain([
      { role: "system", content: "sys" },
      { role: "user", content: "hello" },
      {
        role: "assistant",
        content: "need tool",
        tool_calls: [
          {
            id: "call_1",
            type: "function",
            function: {
              name: "get_character_detail",
              arguments: "{\"name\":\"张三\"}",
            },
          },
        ],
      },
      { role: "tool", tool_call_id: "call_1", content: "result" },
    ]);

    assert.equal(messages[0].getType(), "system");
    assert.equal(messages[1].getType(), "human");
    assert.equal(messages[2].getType(), "ai");
    assert.equal(messages[3].getType(), "tool");
    assert.deepEqual((messages[2] as any).tool_calls, [
      { id: "call_1", name: "get_character_detail", args: { name: "张三" } },
    ]);
    assert.equal((messages[3] as any).tool_call_id, "call_1");
  });
});

describe("ModelRuntime tool-call turn boundary", () => {
  it("returns raw tool calls without parsing business control events", async () => {
    const stream = createStream([
      {
        choices: [
          {
            delta: {
              content: "我会提交审核结论。",
              tool_calls: [
                {
                  index: 0,
                  id: "call_evaluation",
                  function: {
                    name: "submit_evaluation",
                    arguments: JSON.stringify({
                      artifactKey: "draft-1",
                      verdict: "pass",
                      summary: "可以提交给用户确认。",
                    }),
                  },
                },
              ],
            },
            finish_reason: "tool_calls",
          },
        ],
      },
    ]);
    const client = createMockClient([stream]);
    const runtime = new LegacyOpenAIRuntime({
      client: client as never,
      isAiConfigured: () => true,
      billing: createBillingStub(),
    });

    const result = await runtime.runToolCallTurn({
      messages: [{ role: "user", content: "提交审核" }],
      tools: [],
    });

    assert.equal(client.calls, 1);
    assert.equal(result.content, "我会提交审核结论。");
    assert.equal(result.toolCalls.length, 1);
    assert.equal(result.toolCalls[0].function.name, "submit_evaluation");
    assert.equal("controlEvents" in result, false);
  });
});

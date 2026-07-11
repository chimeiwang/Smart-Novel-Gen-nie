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
  ModelCallTimeoutError,
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
  const requests: unknown[] = [];
  return {
    get calls() {
      return calls;
    },
    requests,
    chat: {
      completions: {
        create: async (request: unknown) => {
          requests.push(request);
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
    ensureCanStartModelCall: async (input: { maxOutputTokens?: number }) => ({
      maxOutputTokens: input.maxOutputTokens ?? 1024,
    }),
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
      cachedTokens: 0,
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
      input_token_details: { cache_read: 2 },
    }), {
      promptTokens: 3,
      completionTokens: 5,
      totalTokens: 8,
      cachedTokens: 2,
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

  it("times out a hanging model call", async () => {
    const previousTimeout = process.env.LLM_CALL_TIMEOUT_MS;
    process.env.LLM_CALL_TIMEOUT_MS = "10";
    const client = {
      chat: {
        completions: {
          create: () => new Promise(() => {}),
        },
      },
    };
    const runtime = new LegacyOpenAIRuntime({
      client: client as never,
      isAiConfigured: () => true,
      billing: createBillingStub(),
    });

    try {
      await assert.rejects(
        () => runtime.runToolCallTurn({
          messages: [{ role: "user", content: "会超时" }],
          tools: [],
        }),
        (error) => error instanceof ModelCallTimeoutError && /10ms/.test(error.message)
      );
    } finally {
      if (previousTimeout === undefined) {
        delete process.env.LLM_CALL_TIMEOUT_MS;
      } else {
        process.env.LLM_CALL_TIMEOUT_MS = previousTimeout;
      }
    }
  });
});

describe("ModelCallProfile", () => {
  it("uses a fast profile without reasoning effort for structured calls", async () => {
    const response = {
      choices: [{ message: { content: JSON.stringify({ ok: true }) }, finish_reason: "stop" }],
      usage: { prompt_tokens: 3, completion_tokens: 2, total_tokens: 5 },
    };
    const client = createMockClient([response as never]);
    const runtime = new LegacyOpenAIRuntime({
      client: client as never,
      isAiConfigured: () => true,
      billing: createBillingStub(),
    });

    const result = await runtime.completeStructured(
      { parse: (value: unknown) => value } as never,
      {
        profile: "fast",
        messages: [{ role: "user", content: "route" }],
      }
    );

    assert.deepEqual(result.data, { ok: true });
    assert.equal(client.calls, 1);
    assert.equal((client.requests[0] as { max_tokens?: number }).max_tokens, 384000);
    assert.equal("reasoning_effort" in (client.requests[0] as Record<string, unknown>), false);
  });

  it("uses the full output budget and medium native reasoning for fast tool-call turns", async () => {
    const stream = createStream([
      {
        choices: [{ delta: { content: "done" }, finish_reason: "stop" }],
      },
    ]);
    const client = createMockClient([stream]);
    const runtime = new LegacyOpenAIRuntime({
      client: client as never,
      isAiConfigured: () => true,
      billing: createBillingStub(),
    });

    await runtime.runToolCallTurn({
      profile: "fast",
      reasoningEffort: "medium",
      messages: [{ role: "system", content: "你是审核员" }, { role: "user", content: "审核草案" }],
      tools: [],
    });

    const request = client.requests[0] as {
      max_tokens?: number;
      reasoning_effort?: string;
      messages?: Array<{ content?: string }>;
    };
    assert.equal(request.max_tokens, 384000);
    assert.equal(request.reasoning_effort, "medium");
    assert.equal(JSON.stringify(request.messages).includes("Absolute maximum"), false);
  });
});

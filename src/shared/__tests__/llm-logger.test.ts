import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildAgentRunFinalLogRecord,
  buildLLMRequestLogRecord,
  buildLLMResponseLogRecord,
  buildLLMToolCallLogRecord,
} from "../lib/logger";
import { getLLMLogMode } from "../env";

describe("LLM log mode", () => {
  it("defaults invalid or missing values to summary", () => {
    const original = process.env.LLM_LOG_MODE;
    try {
      delete process.env.LLM_LOG_MODE;
      assert.equal(getLLMLogMode(), "summary");
      process.env.LLM_LOG_MODE = "invalid";
      assert.equal(getLLMLogMode(), "summary");
      process.env.LLM_LOG_MODE = "off";
      assert.equal(getLLMLogMode(), "off");
      process.env.LLM_LOG_MODE = "full";
      assert.equal(getLLMLogMode(), "full");
    } finally {
      if (original === undefined) delete process.env.LLM_LOG_MODE;
      else process.env.LLM_LOG_MODE = original;
    }
  });

  it("summary records total serialized chars without retaining full messages", () => {
    const messages = [
      { role: "system", content: "系统提示" },
      { role: "user", content: "用户请求" },
      { role: "assistant", content: "", tool_calls: [{ function: { name: "get_novel_info", arguments: "{}" } }] },
    ];
    const tools = [{ type: "function", function: { name: "get_novel_info" } }];
    const record = buildLLMRequestLogRecord({
      requestId: "request-1",
      messages,
      tools,
      context: { agentRunId: "run-1", modelTurn: 2 },
      mode: "summary",
      timestamp: "2026-06-29T00:00:00.000Z",
    });

    assert.equal(record.serializedChars, JSON.stringify({ messages, tools }).length);
    assert.equal(record.messageSerializedChars, JSON.stringify(messages).length);
    assert.equal(record.toolSerializedChars, JSON.stringify(tools).length);
    assert.equal(record.textChars, "系统提示".length + "用户请求".length);
    assert.equal(record.messageCount, 3);
    assert.equal(record.toolDefinitionCount, 1);
    assert.equal(record.agentRunId, "run-1");
    assert.equal(record.modelTurn, 2);
    assert.equal("messages" in record, false);
  });

  it("full mode retains messages and tool definitions", () => {
    const messages = [{ role: "user", content: "完整请求" }];
    const tools = [{ type: "function", function: { name: "get_novel_info" } }];
    const record = buildLLMRequestLogRecord({
      requestId: "request-2",
      messages,
      tools,
      mode: "full",
    });

    assert.deepEqual(record.messages, messages);
    assert.deepEqual(record.tools, tools);
  });

  it("records response chars, token usage, duration and finish reason without full content in summary mode", () => {
    const record = buildLLMResponseLogRecord({
      requestId: "request-3",
      content: "审核通过，可以提交用户确认。",
      usage: { promptTokens: 100, completionTokens: 20, cachedTokens: 40, totalTokens: 120 },
      durationMs: 1234,
      finishReason: "stop",
      mode: "summary",
    });

    assert.equal(record.contentChars, "审核通过，可以提交用户确认。".length);
    assert.deepEqual(record.usage, { promptTokens: 100, completionTokens: 20, cachedTokens: 40, totalTokens: 120 });
    assert.equal(record.durationMs, 1234);
    assert.equal(record.finishReason, "stop");
    assert.equal("content" in record, false);
  });

  it("records tool argument/result chars and distinguishes AGENT_RUN_FINAL from RESPONSE", () => {
    const toolRecord = buildLLMToolCallLogRecord({
      requestId: "run-1",
      toolName: "get_novel_info",
      args: { chapterId: "chapter-1" },
      result: "tool result",
      durationMs: 12,
      mode: "summary",
    });
    const finalRecord = buildAgentRunFinalLogRecord({
      agentRunId: "run-1",
      content: "最终报告",
      toolCallCount: 1,
      controlEventTypes: ["submit_evaluation"],
      mode: "summary",
    });

    assert.equal(toolRecord.argsChars, JSON.stringify({ chapterId: "chapter-1" }).length);
    assert.equal(toolRecord.resultChars, "tool result".length);
    assert.equal(finalRecord.event, "AGENT_RUN_FINAL");
    assert.equal(finalRecord.contentChars, "最终报告".length);
    assert.equal(finalRecord.toolCallCount, 1);
  });
});

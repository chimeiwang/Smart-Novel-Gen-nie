import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildAgentRunFinalLogRecord,
  buildLLMRequestLogRecord,
  buildLLMResponseLogRecord,
  buildLLMToolCallLogRecord,
  formatLLMIndexLine,
  formatLLMLogRecord,
  formatLLMWorkflowBlock,
  shouldWriteSplitLLMLog,
} from "../lib/logger";
import { getLLMLogMode } from "../env";

describe("LLM log mode", () => {
  it("defaults invalid or missing values to full", () => {
    const original = process.env.LLM_LOG_MODE;
    try {
      delete process.env.LLM_LOG_MODE;
      assert.equal(getLLMLogMode(), "full");
      process.env.LLM_LOG_MODE = "invalid";
      assert.equal(getLLMLogMode(), "full");
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

  it("full response retains supplier reasoning and requested tool calls", () => {
    const toolCalls = [{
      id: "call-1",
      type: "function",
      function: { name: "get_novel_info", arguments: "{\"chapterId\":\"chapter-1\"}" },
    }];
    const record = buildLLMResponseLogRecord({
      requestId: "request-readable",
      content: "我先查询小说信息。",
      reasoningContent: "需要先确认当前章节。",
      toolCalls,
      mode: "full",
    });

    assert.equal(record.reasoningContent, "需要先确认当前章节。");
    assert.deepEqual(record.toolCalls, toolCalls);
    assert.equal(record.reasoningChars, "需要先确认当前章节。".length);
    assert.equal(record.toolCallCount, 1);
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

  it("formats a full request as readable multiline text without long business ids", () => {
    const record = buildLLMRequestLogRecord({
      requestId: "1782989283209-mt57n1",
      messages: [
        { role: "system", content: "你是校验员。" },
        { role: "user", content: "检查第六章。" },
        {
          role: "assistant",
          content: "",
          tool_calls: [{ id: "call_should_not_be_logged", type: "function", function: { name: "get_novel_info", arguments: "{}" } }],
        },
        { role: "tool", tool_call_id: "call_should_not_be_logged", content: "{\"title\":\"第六章\"}" },
      ],
      tools: [{ type: "function", function: { name: "get_novel_info", description: "读取小说信息" } }],
      context: {
        agentRunId: "1782989200000-chain77",
        agentId: "校验",
        callType: "校验员(new)",
        modelTurn: 2,
        taskId: "cmr3dogeb00fba2kz7lpt9j1s",
      },
      mode: "full",
      timestamp: "2026-07-02T00:00:00.000Z",
    });
    const output = formatLLMLogRecord(record);

    assert.match(output, /\[chain77\] \[第 2 轮\] \[步骤 01\] >>> LLM 输入（发送给模型）/);
    assert.match(output, /Agent: 校验/);
    assert.match(output, /你是校验员。/);
    assert.match(output, /get_novel_info/);
    assert.match(output, /"title": "第六章"/);
    assert.doesNotMatch(output, /cmr3dogeb00fba2kz7lpt9j1s/);
    assert.doesNotMatch(output, /call_should_not_be_logged/);
    assert.equal(output.startsWith("{"), false);
  });

  it("formats tool arguments and results in dedicated readable sections", () => {
    const record = buildLLMToolCallLogRecord({
      requestId: "run-tool123",
      toolName: "get_novel_info",
      args: { chapterId: "chapter-1" },
      result: "{\"title\":\"第六章\"}",
      context: {
        agentRunId: "1782989200000-chain77",
        agentId: "校验",
        modelTurn: 2,
        toolCallIndex: 2,
        toolCallTotal: 3,
      },
      mode: "full",
    });
    const output = formatLLMLogRecord(record);

    assert.match(output, /\[chain77\] \[第 2 轮\] \[步骤 04\] 工具 2\/3：get_novel_info/);
    assert.match(output, /【工具 2\/3 输入参数 >>>】/);
    assert.match(output, /"chapterId": "chapter-1"/);
    assert.match(output, /【工具 2\/3 输出结果 <<<】/);
    assert.match(output, /"title": "第六章"/);
  });

  it("uses the same chain and explicit round steps for input, output, and ordered tools", () => {
    const context = {
      agentRunId: "1782989200000-chain77",
      agentId: "写作",
      modelTurn: 3,
    };
    const request = buildLLMRequestLogRecord({
      requestId: "1782989210000-request1",
      messages: [{ role: "user", content: "继续写作" }],
      context,
      mode: "full",
    });
    const response = buildLLMResponseLogRecord({
      requestId: "1782989210000-request1",
      content: "先读取大纲。",
      toolCalls: [
        { type: "function", function: { name: "get_outline", arguments: "{}" } },
        { type: "function", function: { name: "get_recent_chapters", arguments: "{}" } },
      ],
      context,
      mode: "full",
    });
    const tool = buildLLMToolCallLogRecord({
      requestId: context.agentRunId,
      toolName: "get_recent_chapters",
      args: {},
      result: "最近章节",
      context: { ...context, toolCallIndex: 2, toolCallTotal: 2 },
      mode: "full",
    });

    assert.match(formatLLMLogRecord(request), /\[chain77\] \[第 3 轮\] \[步骤 01\] >>> LLM 输入/);
    assert.match(formatLLMLogRecord(response), /\[chain77\] \[第 3 轮\] \[步骤 02\] <<< LLM 输出/);
    assert.match(formatLLMLogRecord(response), /工具 1\/2：get_outline/);
    assert.match(formatLLMLogRecord(response), /工具 2\/2：get_recent_chapters/);
    assert.match(formatLLMLogRecord(tool), /\[chain77\] \[第 3 轮\] \[步骤 04\] 工具 2\/2/);
  });

  it("formats a one-line chronological index pointing to the isolated run transcript", () => {
    const record = buildLLMResponseLogRecord({
      requestId: "1782989210000-request1",
      content: "完成",
      toolCalls: [],
      finishReason: "stop",
      context: { agentRunId: "1782989200000-chain77", agentId: "写作", modelTurn: 3 },
      mode: "full",
      timestamp: "2026-07-02T13:47:41.193Z",
    });
    const line = formatLLMIndexLine(record, "runs/2026-07-02/写作-chain77.log");

    assert.match(line, /^13:47:41\.193 \| 链路 chain77 \| 写作 \| 第 3 轮 \| 步骤 02 \| <<< LLM 输出/);
    assert.match(line, /详情=runs\/2026-07-02\/写作-chain77\.log/);
  });

  it("formats only verbatim LLM messages and model content for the human workflow timeline", () => {
    const request = buildLLMRequestLogRecord({
      requestId: "request-raw",
      messages: [{
        role: "assistant",
        content: "不要压缩  空格与\n换行",
        tool_calls: [{ id: "call-original", function: { name: "read", arguments: "{\"id\":\"raw-1\"}" } }],
      }],
      tools: [{ type: "function", function: { name: "read", description: "原始工具定义" } }],
      context: { taskId: "task-raw", modelTurn: 1 },
      mode: "full",
      timestamp: "2026-07-03T01:02:03.004Z",
    });
    const response = buildLLMResponseLogRecord({
      requestId: "request-raw",
      content: "模型输出第一行\n模型输出第二行",
      reasoningContent: "供应商推理原文",
      usage: { promptTokens: 120, completionTokens: 30, cachedTokens: 80, totalTokens: 150 },
      toolCalls: [{ id: "call-response-only", function: { name: "read", arguments: "{\"id\":\"raw-1\"}" } }],
      context: { taskId: "task-raw", modelTurn: 1 },
      mode: "full",
      timestamp: "2026-07-03T01:02:04.004Z",
    });
    const tool = buildLLMToolCallLogRecord({
      requestId: "request-raw",
      toolName: "read",
      args: { id: "raw-1" },
      result: "工具返回第一行\n工具返回第二行",
      context: { taskId: "task-raw", modelTurn: 1, toolCallIndex: 1, toolCallTotal: 1 },
      mode: "full",
      timestamp: "2026-07-03T01:02:05.004Z",
    });

    const output = [request, response, tool].map(formatLLMWorkflowBlock).join("");
    assert.match(output, /第 1 轮 LLM 输入 >>>/);
    assert.match(output, /不要压缩  空格与\n换行/);
    assert.match(output, /模型输出第一行\n模型输出第二行/);
    assert.match(output, /Token 消耗: 输入 120 \| 输出 30 \| 缓存 80 \| 合计 150/);
    assert.doesNotMatch(output, /【发送给模型的工具定义原文】/);
    assert.doesNotMatch(output, /原始工具定义/);
    assert.doesNotMatch(output, /供应商推理原文/);
    assert.match(output, /call-original/);
    assert.doesNotMatch(output, /call-response-only/);
    assert.doesNotMatch(output, /第 1 轮 工具 1\/1：read/);
    assert.doesNotMatch(output, /工具返回第一行\n工具返回第二行/);
  });

  it("writes workflow LLM records to split files only when explicitly enabled", () => {
    const workflowRecord = buildLLMResponseLogRecord({
      requestId: "request-workflow",
      content: "完成",
      context: { taskId: "task-1" },
      mode: "full",
    });
    const standaloneRecord = buildLLMResponseLogRecord({
      requestId: "request-standalone",
      content: "完成",
      mode: "full",
    });

    assert.equal(shouldWriteSplitLLMLog(workflowRecord, false), false);
    assert.equal(shouldWriteSplitLLMLog(workflowRecord, true), true);
    assert.equal(shouldWriteSplitLLMLog(standaloneRecord, false), true);
  });
});

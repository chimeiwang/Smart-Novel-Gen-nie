/**
 * 本地日志系统
 *
 * @module shared/lib/logger
 * @description 简单的本地文件日志，用于调试内存泄漏和 SSE 问题
 */

import fs from "fs";
import path from "path";
import { getLLMLogMode, type LLMLogMode } from "@/shared/env";

/** 日志文件目录 */
const LOG_DIR = path.join(process.cwd(), "logs");

/** LLM 日志文件目录 */
const LLM_LOG_DIR = path.join(process.cwd(), "logs", "llm");
const HUMAN_WORKFLOW_LOG_DIR = path.join(process.cwd(), "logs", "workflow-events");

/** 日志级别 */
export type LogLevel = "ERROR" | "WARN" | "INFO" | "DEBUG";

/** 日志条目 */
export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  category: string;
  message: string;
  data?: unknown;
  memory?: {
    heapUsed: number;
    heapTotal: number;
    external: number;
    rss: number;
  };
  sse?: {
    taskId?: string;
    event?: string;
    duration?: number;
  };
}

export interface LLMLogContext {
  agentRunId?: string;
  modelTurn?: number;
  toolCallIndex?: number;
  toolCallTotal?: number;
  callType?: string;
  agentId?: string;
  taskId?: string;
  userId?: string;
  novelId?: string;
  [key: string]: unknown;
}

export interface LLMLogUsage {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  cachedTokens?: number;
}

export interface LLMLogRecord extends LLMLogContext {
  timestamp: string;
  event: "REQUEST" | "RESPONSE" | "TOOL_CALL" | "AGENT_RUN_FINAL" | "ERROR";
  requestId: string;
  [key: string]: unknown;
}

/** Workflow 人工日志接收 LLM 原文记录的运行时回调。 */
export type WorkflowLLMTraceSink = (record: LLMLogRecord) => void;

const LLM_LOG_PREVIEW_CHARS = 300;

function serializeForLength(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return "[无法序列化的数据]";
  }
}

function getMessageTextLength(message: unknown): number {
  if (!message || typeof message !== "object") return 0;
  const item = message as { content?: unknown };
  const contentChars = typeof item.content === "string"
    ? item.content.length
    : item.content == null ? 0 : serializeForLength(item.content).length;
  return contentChars;
}

function getMessagePreview(messages: unknown[]): string {
  for (let index = messages.length - 1; index >= 0; index--) {
    const message = messages[index];
    if (!message || typeof message !== "object") continue;
    const content = (message as { content?: unknown }).content;
    if (typeof content === "string" && content.trim()) {
      return content.replace(/\s+/g, " ").trim().slice(0, LLM_LOG_PREVIEW_CHARS);
    }
  }
  return "";
}

export function buildLLMRequestLogRecord(input: {
  requestId: string;
  messages: unknown[];
  tools?: unknown[];
  context?: LLMLogContext;
  mode: Exclude<LLMLogMode, "off">;
  timestamp?: string;
}): LLMLogRecord {
  const serializedMessages = serializeForLength(input.messages);
  const serializedTools = serializeForLength(input.tools ?? []);
  const serializedRequest = serializeForLength({
    messages: input.messages,
    tools: input.tools ?? [],
  });
  const roleCounts: Record<string, number> = {};
  for (const message of input.messages) {
    const role = message && typeof message === "object" && typeof (message as { role?: unknown }).role === "string"
      ? String((message as { role: string }).role)
      : "unknown";
    roleCounts[role] = (roleCounts[role] ?? 0) + 1;
  }
  const record: LLMLogRecord = {
    ...(input.context ?? {}),
    timestamp: input.timestamp ?? new Date().toISOString(),
    event: "REQUEST",
    requestId: input.requestId,
    messageCount: input.messages.length,
    roleCounts,
    serializedChars: serializedRequest.length,
    messageSerializedChars: serializedMessages.length,
    toolSerializedChars: serializedTools.length,
    textChars: input.messages.reduce<number>((total, message) => total + getMessageTextLength(message), 0),
    toolDefinitionCount: input.tools?.length ?? 0,
    preview: getMessagePreview(input.messages),
  };
  if (input.mode === "full") {
    record.messages = input.messages;
    record.tools = input.tools ?? [];
  }
  return record;
}

export function buildLLMResponseLogRecord(input: {
  requestId: string;
  content: string;
  reasoningContent?: string;
  toolCalls?: unknown[];
  usage?: LLMLogUsage;
  context?: LLMLogContext;
  durationMs?: number;
  finishReason?: string;
  mode: Exclude<LLMLogMode, "off">;
  timestamp?: string;
}): LLMLogRecord {
  const record: LLMLogRecord = {
    ...(input.context ?? {}),
    timestamp: input.timestamp ?? new Date().toISOString(),
    event: "RESPONSE",
    requestId: input.requestId,
    contentChars: input.content.length,
    reasoningChars: input.reasoningContent?.length ?? 0,
    toolCallCount: input.toolCalls?.length ?? 0,
    preview: input.content.replace(/\s+/g, " ").trim().slice(0, LLM_LOG_PREVIEW_CHARS),
    durationMs: input.durationMs,
    finishReason: input.finishReason,
    usage: input.usage,
  };
  if (input.mode === "full") {
    record.content = input.content;
    record.reasoningContent = input.reasoningContent ?? "";
    record.toolCalls = input.toolCalls ?? [];
  }
  return record;
}

export function buildLLMToolCallLogRecord(input: {
  requestId: string;
  toolName: string;
  args: Record<string, unknown>;
  result: string;
  context?: LLMLogContext;
  durationMs?: number;
  mode: Exclude<LLMLogMode, "off">;
  timestamp?: string;
}): LLMLogRecord {
  const serializedArgs = serializeForLength(input.args);
  const record: LLMLogRecord = {
    ...(input.context ?? {}),
    timestamp: input.timestamp ?? new Date().toISOString(),
    event: "TOOL_CALL",
    requestId: input.requestId,
    toolName: input.toolName,
    argsChars: serializedArgs.length,
    resultChars: input.result.length,
    resultPreview: input.result.replace(/\s+/g, " ").trim().slice(0, LLM_LOG_PREVIEW_CHARS),
    durationMs: input.durationMs,
  };
  if (input.mode === "full") {
    record.args = input.args;
    record.result = input.result;
  }
  return record;
}

export function buildAgentRunFinalLogRecord(input: {
  agentRunId: string;
  content: string;
  context?: LLMLogContext;
  usage?: LLMLogUsage;
  finishReason?: string;
  toolCallCount?: number;
  controlEventTypes?: string[];
  mode: Exclude<LLMLogMode, "off">;
  timestamp?: string;
}): LLMLogRecord {
  const record: LLMLogRecord = {
    ...(input.context ?? {}),
    timestamp: input.timestamp ?? new Date().toISOString(),
    event: "AGENT_RUN_FINAL",
    requestId: input.agentRunId,
    agentRunId: input.agentRunId,
    contentChars: input.content.length,
    preview: input.content.replace(/\s+/g, " ").trim().slice(0, LLM_LOG_PREVIEW_CHARS),
    usage: input.usage,
    finishReason: input.finishReason,
    toolCallCount: input.toolCallCount ?? 0,
    controlEventTypes: input.controlEventTypes ?? [],
  };
  if (input.mode === "full") record.content = input.content;
  return record;
}

const LLM_LOG_SEPARATOR = "=".repeat(88);

function prettyPrint(value: unknown): string {
  if (typeof value === "string") return value || "（空）";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function prettyPrintContent(value: unknown): string {
  if (typeof value !== "string") return prettyPrint(value);
  if (!value) return "（空）";
  const trimmed = value.trim();
  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      return prettyPrint(JSON.parse(trimmed));
    } catch {
      return value;
    }
  }
  return value;
}

function shortRequestRef(requestId: string): string {
  const parts = requestId.split("-");
  if (parts.length > 1) return parts.at(-1) || requestId.slice(-8);
  return requestId.length > 8 ? requestId.slice(-8) : requestId;
}

export function getHumanWorkflowLogPath(taskId: string, timestamp = new Date().toISOString()): string {
  const date = timestamp.slice(0, 10);
  const root = process.env.WORKFLOW_EVENT_LOG_DIR || HUMAN_WORKFLOW_LOG_DIR;
  return path.join(root, "runs", date, `${shortRequestRef(taskId)}.log`);
}

export function appendHumanWorkflowLog(taskId: string, timestamp: string, content: string): void {
  const filePath = getHumanWorkflowLogPath(taskId, timestamp);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.appendFileSync(filePath, content, "utf-8");
}

function getChainRef(record: LLMLogRecord): string {
  return shortRequestRef(
    typeof record.agentRunId === "string" && record.agentRunId
      ? record.agentRunId
      : record.requestId
  );
}

function getRoundLabel(record: LLMLogRecord): string {
  return typeof record.modelTurn === "number" ? `第 ${record.modelTurn} 轮` : "单轮调用";
}

function getStepLabel(record: LLMLogRecord): string {
  if (record.event === "REQUEST") return "步骤 01";
  if (record.event === "RESPONSE") return "步骤 02";
  if (record.event === "TOOL_CALL") {
    const index = typeof record.toolCallIndex === "number" ? record.toolCallIndex : 1;
    return `步骤 ${String(index + 2).padStart(2, "0")}`;
  }
  return record.event === "AGENT_RUN_FINAL" ? "流程结束" : "异常";
}

function formatContext(record: LLMLogRecord): string {
  const parts: string[] = [];
  if (typeof record.agentId === "string" && record.agentId) parts.push(`Agent: ${record.agentId}`);
  if (typeof record.callType === "string" && record.callType) parts.push(`调用类型: ${record.callType}`);
  if (typeof record.operationKind === "string" && record.operationKind) parts.push(`操作: ${record.operationKind}`);
  return parts.length > 0 ? parts.join(" | ") : "Agent: 通用调用";
}

function formatUsage(usage: unknown): string | null {
  if (!usage || typeof usage !== "object") return null;
  const item = usage as Partial<LLMLogUsage>;
  const fields = [
    `输入 ${item.promptTokens ?? 0}`,
    `输出 ${item.completionTokens ?? 0}`,
    `合计 ${item.totalTokens ?? 0}`,
  ];
  if (item.cachedTokens !== undefined) fields.push(`缓存 ${item.cachedTokens}`);
  return `Token: ${fields.join(" / ")}`;
}

function formatWorkflowUsage(usage: unknown): string {
  if (!usage || typeof usage !== "object") return "Token 消耗: 供应商未返回 usage";
  const item = usage as Partial<LLMLogUsage>;
  return [
    `输入 ${item.promptTokens ?? 0}`,
    `输出 ${item.completionTokens ?? 0}`,
    `缓存 ${item.cachedTokens ?? 0}`,
    `合计 ${item.totalTokens ?? (item.promptTokens ?? 0) + (item.completionTokens ?? 0)}`,
  ].join(" | ").replace(/^/, "Token 消耗: ");
}

function formatMessages(messages: unknown[]): string {
  return messages.map((message, index) => {
    if (!message || typeof message !== "object") {
      return `--- 消息 ${index + 1} [unknown] ---\n${prettyPrint(message)}`;
    }
    const item = message as Record<string, unknown>;
    const role = typeof item.role === "string" ? item.role : "unknown";
    const content = item.content;
    const extra = Object.fromEntries(Object.entries(item)
      .filter(([key]) => key !== "role" && key !== "content" && key !== "tool_call_id")
      .map(([key, value]) => {
        if (key !== "tool_calls" || !Array.isArray(value)) return [key, value];
        return [key, value.map((toolCall) => {
          if (!toolCall || typeof toolCall !== "object") return toolCall;
          const sanitized = { ...toolCall as Record<string, unknown> };
          delete sanitized.id;
          return sanitized;
        })];
      }));
    const lines = [`--- 消息 ${index + 1} [${role}] ---`, prettyPrintContent(content)];
    if (Object.keys(extra).length > 0) {
      lines.push("附加字段：", prettyPrint(extra));
    }
    return lines.join("\n");
  }).join("\n\n");
}

function formatMessagesVerbatim(messages: unknown[]): string {
  return messages.map((message, index) => {
    if (!message || typeof message !== "object") {
      return `--- 消息 ${index + 1} [unknown] ---\n${prettyPrint(message)}`;
    }
    const item = message as Record<string, unknown>;
    const role = typeof item.role === "string" ? item.role : "unknown";
    const lines = [
      `--- 消息 ${index + 1} [${role}] ---`,
      prettyPrintContent(item.content),
    ];
    const extra = Object.fromEntries(Object.entries(item).filter(([key]) => key !== "role" && key !== "content"));
    if (Object.keys(extra).length > 0) lines.push("附加字段原文：", prettyPrint(extra));
    return lines.join("\n");
  }).join("\n\n");
}

function formatToolDefinitions(tools: unknown[]): string {
  if (tools.length === 0) return "（无）";
  return tools.map((tool, index) => {
    const item = tool && typeof tool === "object" ? tool as Record<string, unknown> : null;
    const fn = item?.function && typeof item.function === "object"
      ? item.function as Record<string, unknown>
      : null;
    const name = typeof fn?.name === "string" ? fn.name : `工具 ${index + 1}`;
    return `--- ${name} ---\n${prettyPrint(tool)}`;
  }).join("\n\n");
}

function formatModelToolCalls(toolCalls: unknown[]): string {
  if (toolCalls.length === 0) return "（无）";
  return toolCalls.map((toolCall, index) => {
    const item = toolCall && typeof toolCall === "object" ? toolCall as Record<string, unknown> : null;
    const fn = item?.function && typeof item.function === "object"
      ? item.function as Record<string, unknown>
      : null;
    const name = typeof fn?.name === "string" ? fn.name : `工具 ${index + 1}`;
    const rawArgs = fn?.arguments;
    let args: unknown = rawArgs;
    if (typeof rawArgs === "string") {
      try {
        args = JSON.parse(rawArgs);
      } catch {
        args = rawArgs;
      }
    }
    return `--- 工具 ${index + 1}/${toolCalls.length}：${name} ---\n${prettyPrint(args)}`;
  }).join("\n\n");
}

function getEventDirectionTitle(record: LLMLogRecord): string {
  if (record.event === "REQUEST") return ">>> LLM 输入（发送给模型）";
  if (record.event === "RESPONSE") return "<<< LLM 输出（模型返回）";
  if (record.event === "TOOL_CALL") {
    const index = typeof record.toolCallIndex === "number" ? record.toolCallIndex : 1;
    const total = typeof record.toolCallTotal === "number" ? record.toolCallTotal : "?";
    return `工具 ${index}/${total}：${String(record.toolName || "unknown")}（输入 >>> / 输出 <<<）`;
  }
  if (record.event === "AGENT_RUN_FINAL") return "=== Agent 调用链最终汇总 ===";
  return "!!! 调用失败 !!!";
}

export function formatLLMIndexLine(record: LLMLogRecord, detailPath: string): string {
  const time = record.timestamp.slice(11, 23);
  const agent = typeof record.agentId === "string" && record.agentId ? record.agentId : "通用";
  let detail = "";
  if (record.event === "REQUEST") {
    detail = `${record.messageCount ?? 0} 条消息，${record.toolDefinitionCount ?? 0} 个工具`;
  } else if (record.event === "RESPONSE") {
    detail = `结束=${String(record.finishReason || "unknown")}，工具请求=${record.toolCallCount ?? 0}`;
  } else if (record.event === "TOOL_CALL") {
    detail = `${String(record.toolName || "unknown")}，耗时=${record.durationMs ?? "?"}ms`;
  } else if (record.event === "AGENT_RUN_FINAL") {
    detail = `结束=${String(record.finishReason || "unknown")}，工具总数=${record.toolCallCount ?? 0}`;
  } else {
    detail = String(record.message || "未知错误");
  }
  return [
    time,
    `链路 ${getChainRef(record)}`,
    agent,
    getRoundLabel(record),
    getStepLabel(record),
    getEventDirectionTitle(record),
    detail,
    `详情=${detailPath}`,
  ].join(" | ") + "\n";
}

/** 将 LLM 记录排版为适合人工逐轮阅读的多行文本块。 */
export function formatLLMLogRecord(record: LLMLogRecord): string {
  const lines = [
    LLM_LOG_SEPARATOR,
    `[${getChainRef(record)}] [${getRoundLabel(record)}] [${getStepLabel(record)}] ${getEventDirectionTitle(record)}`,
    `时间: ${record.timestamp}`,
    formatContext(record),
  ];

  if (record.event === "REQUEST") {
    lines.push(`消息数: ${record.messageCount ?? 0} | 可用工具数: ${record.toolDefinitionCount ?? 0}`);
    if (Array.isArray(record.messages)) {
      lines.push("", "【请求消息】", formatMessages(record.messages));
      lines.push("", "【可用工具定义】", formatToolDefinitions(Array.isArray(record.tools) ? record.tools : []));
    } else {
      lines.push("", "【请求摘要】", String(record.preview || "（空）"), "（LLM_LOG_MODE=summary，完整内容未写入）");
    }
  } else if (record.event === "RESPONSE") {
    const stats = [
      typeof record.durationMs === "number" ? `耗时: ${record.durationMs}ms` : null,
      record.finishReason ? `结束原因: ${String(record.finishReason)}` : null,
      formatUsage(record.usage),
    ].filter(Boolean);
    if (stats.length > 0) lines.push(stats.join(" | "));
    lines.push("", "【模型正文】", typeof record.content === "string" ? record.content || "（空）" : String(record.preview || "（空）"));
    if (typeof record.content !== "string") lines.push("（LLM_LOG_MODE=summary，完整内容未写入）");
    if (typeof record.reasoningContent === "string" && record.reasoningContent) {
      lines.push("", "【供应商返回的推理内容】", record.reasoningContent);
    }
    if (Array.isArray(record.toolCalls) && record.toolCalls.length > 0) {
      lines.push("", `【模型声明的工具调用顺序：共 ${record.toolCalls.length} 个】`, formatModelToolCalls(record.toolCalls));
    }
  } else if (record.event === "TOOL_CALL") {
    const index = typeof record.toolCallIndex === "number" ? record.toolCallIndex : 1;
    const total = typeof record.toolCallTotal === "number" ? record.toolCallTotal : "?";
    lines.push(`顺序: 模型声明的第 ${index}/${total} 个工具 | 耗时: ${record.durationMs ?? "?"}ms`);
    lines.push("", `【工具 ${index}/${total} 输入参数 >>>】`, "args" in record ? prettyPrint(record.args) : "（summary 模式未写入完整参数）");
    lines.push("", `【工具 ${index}/${total} 输出结果 <<<】`, typeof record.result === "string" ? prettyPrintContent(record.result) : String(record.resultPreview || "（空）"));
    if (typeof record.result !== "string") lines.push("（LLM_LOG_MODE=summary，完整结果未写入）");
  } else if (record.event === "AGENT_RUN_FINAL") {
    const stats = [
      record.finishReason ? `结束原因: ${String(record.finishReason)}` : null,
      typeof record.toolCallCount === "number" ? `工具调用: ${record.toolCallCount}` : null,
      formatUsage(record.usage),
    ].filter(Boolean);
    if (stats.length > 0) lines.push(stats.join(" | "));
    if (Array.isArray(record.controlEventTypes) && record.controlEventTypes.length > 0) {
      lines.push(`控制事件: ${record.controlEventTypes.join(", ")}`);
    }
    lines.push("", "【Agent 可见输出汇总】", typeof record.content === "string" ? record.content || "（空）" : String(record.preview || "（空）"));
    if (typeof record.content !== "string") lines.push("（LLM_LOG_MODE=summary，完整内容未写入）");
  } else {
    lines.push("", "【错误】", String(record.message || "未知错误"));
  }

  return `${lines.join("\n")}\n\n`;
}

/** 写入统一工作流时间线的 LLM 原文块；上下文由工作流文件头统一说明。 */
export function formatLLMWorkflowBlock(record: LLMLogRecord): string {
  const time = record.timestamp.slice(11, 23);
  const round = getRoundLabel(record);
  if (record.event === "REQUEST") {
    const messages = Array.isArray(record.messages)
      ? formatMessagesVerbatim(record.messages)
      : "（当前不是 full 模式，未取得请求原文）";
    return [
      `[${time}] ${round} LLM 输入 >>>`,
      "【发送给模型的消息原文】",
      messages,
      "",
    ].join("\n") + "\n";
  }
  if (record.event === "RESPONSE") {
    const lines = [
      `[${time}] ${round} LLM 输出 <<<`,
      formatWorkflowUsage(record.usage),
      "【模型正文原文】",
      typeof record.content === "string" ? record.content || "（空）" : "（当前不是 full 模式，未取得输出原文）",
    ];
    lines.push("");
    return `${lines.join("\n")}\n`;
  }
  if (record.event === "TOOL_CALL") {
    return "";
  }
  if (record.event === "ERROR") {
    return `[${time}] LLM 调用失败\n${String(record.message || "未知错误")}\n\n`;
  }
  return "";
}

export function shouldWriteSplitLLMLog(record: LLMLogRecord, splitLogEnabled: boolean): boolean {
  const belongsToWorkflow = typeof record.taskId === "string" && Boolean(record.taskId);
  return !belongsToWorkflow || splitLogEnabled;
}

/** 日志实例 */
class LocalLogger {
  private initialized = false;

  /**
   * 初始化日志目录
   */
  private init(): void {
    if (this.initialized) return;

    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true });
    }

    if (!fs.existsSync(LLM_LOG_DIR)) {
      fs.mkdirSync(LLM_LOG_DIR, { recursive: true });
    }

    this.initialized = true;
  }

  /**
   * 获取今天的日志文件路径
   */
  private getLogFilePath(): string {
    this.init();
    const date = new Date().toISOString().split("T")[0];
    return path.join(LOG_DIR, `app-${date}.log`);
  }

  /**
   * 获取 LLM 日志文件路径
   */
  private getLLMIndexFilePath(record: LLMLogRecord): string {
    this.init();
    const date = record.timestamp.slice(0, 10);
    return path.join(LLM_LOG_DIR, `llm-${date}.index.log`);
  }

  private getLLMRunFilePath(record: LLMLogRecord): { absolutePath: string; relativePath: string } {
    this.init();
    const date = record.timestamp.slice(0, 10);
    const agent = String(record.agentId || "通用").replace(/[^\p{L}\p{N}_-]+/gu, "-");
    const fileName = `${agent}-${getChainRef(record)}.log`;
    const relativePath = path.join("runs", date, fileName);
    const absolutePath = path.join(LLM_LOG_DIR, relativePath);
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    return { absolutePath, relativePath };
  }

  private getLLMTaskIndexFilePath(record: LLMLogRecord): string | null {
    if (typeof record.taskId !== "string" || !record.taskId) return null;
    const date = record.timestamp.slice(0, 10);
    const taskRef = shortRequestRef(record.taskId);
    const taskDir = path.join(LLM_LOG_DIR, "tasks", date);
    fs.mkdirSync(taskDir, { recursive: true });
    return path.join(taskDir, `${taskRef}.index.log`);
  }

  /**
   * 写入 LLM 日志
   */
  private writeLLMLogRecord(
    record: LLMLogRecord,
    force = false,
    workflowTraceSink?: WorkflowLLMTraceSink
  ): void {
    if (workflowTraceSink) {
      try {
        workflowTraceSink(record);
      } catch (error) {
        console.error("Workflow LLM 日志写入失败:", error);
      }
    }
    if (process.env.NODE_TEST_CONTEXT && process.env.LLM_LOG_WRITE_IN_TESTS !== "true") return;
    if (!force && getLLMLogMode() === "off") return;
    try {
      const belongsToWorkflow = typeof record.taskId === "string" && Boolean(record.taskId);
      if (!workflowTraceSink && belongsToWorkflow) {
        const workflowBlock = formatLLMWorkflowBlock(record);
        if (workflowBlock) appendHumanWorkflowLog(String(record.taskId), record.timestamp, workflowBlock);
      }

      // 有 taskId 的 Agent 调用已经进入统一工作流日志，默认不再重复生成
      // llm/runs、llm/tasks 和每日 index。无 taskId 的独立 LLM 调用仍保留旧目录作为兜底。
      const splitLogEnabled = process.env.LLM_SPLIT_LOG_ENABLED === "true";
      if (!shouldWriteSplitLLMLog(record, splitLogEnabled)) return;

      const runFile = this.getLLMRunFilePath(record);
      const indexLine = formatLLMIndexLine(record, runFile.relativePath);
      fs.appendFileSync(runFile.absolutePath, formatLLMLogRecord(record), "utf-8");
      fs.appendFileSync(this.getLLMIndexFilePath(record), indexLine, "utf-8");
      const taskIndexPath = this.getLLMTaskIndexFilePath(record);
      if (taskIndexPath) fs.appendFileSync(taskIndexPath, indexLine, "utf-8");
    } catch (e) {
      console.error("LLM 日志写入失败:", e);
    }
  }

  /**
   * 格式化日志条目
   */
  private formatEntry(entry: LogEntry): string {
    const base = `[${entry.timestamp}] [${entry.level}] [${entry.category}] ${entry.message}`;

    let line = base;
    if (entry.memory) {
      line += ` | 内存: heap=${Math.round(entry.memory.heapUsed / 1024 / 1024)}MB, rss=${Math.round(entry.memory.rss / 1024 / 1024)}MB`;
    }
    if (entry.sse) {
      line += ` | SSE: taskId=${entry.sse.taskId || "unknown"}, event=${entry.sse.event || "unknown"}`;
      if (entry.sse.duration !== undefined) {
        line += `, duration=${entry.sse.duration}ms`;
      }
    }
    if (entry.data !== undefined) {
      try {
        const dataStr = typeof entry.data === "string" ? entry.data : JSON.stringify(entry.data);
        line += ` | ${dataStr}`;
      } catch {
        line += ` | [无法序列化的数据]`;
      }
    }

    return line + "\n";
  }

  /**
   * 写入日志
   */
  private write(entry: LogEntry): void {
    try {
      const logPath = this.getLogFilePath();
      const formatted = this.formatEntry(entry);
      fs.appendFileSync(logPath, formatted, "utf-8");
    } catch (e) {
      console.error("日志写入失败:", e);
    }
  }

  /**
   * 获取当前内存使用情况
   */
  private getMemoryInfo(): LogEntry["memory"] {
    const mem = process.memoryUsage();
    return {
      heapUsed: mem.heapUsed,
      heapTotal: mem.heapTotal,
      external: mem.external,
      rss: mem.rss,
    };
  }

  /**
   * 记录日志（通用方法）
   */
  private log(
    level: LogLevel,
    category: string,
    message: string,
    data?: unknown,
    extras?: { sse?: LogEntry["sse"] }
  ): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      category,
      message,
      data,
      memory: this.getMemoryInfo(),
      ...extras,
    };

    this.write(entry);

    // 同时打印到控制台，方便实时查看
    const consoleMsg = this.formatEntry(entry).trim();
    if (level === "ERROR") {
      console.error(consoleMsg);
    } else if (level === "WARN") {
      console.warn(consoleMsg);
    } else {
      console.log(consoleMsg);
    }
  }

  /**
   * 错误日志
   */
  error(category: string, message: string, data?: unknown): void {
    this.log("ERROR", category, message, data);
  }

  /**
   * 警告日志
   */
  warn(category: string, message: string, data?: unknown): void {
    this.log("WARN", category, message, data);
  }

  /**
   * 信息日志
   */
  info(category: string, message: string, data?: unknown): void {
    this.log("INFO", category, message, data);
  }

  /**
   * 调试日志
   */
  debug(category: string, message: string, data?: unknown): void {
    this.log("DEBUG", category, message, data);
  }

  /**
   * SSE 连接开始
   */
  sseStart(taskId: string, params?: Record<string, unknown>): void {
    this.log("INFO", "SSE", `SSE连接开始`, params, {
      sse: { taskId, event: "start" },
    });
  }

  /**
   * SSE 连接结束
   */
  sseEnd(taskId: string, reason: string, durationMs: number): void {
    this.log("INFO", "SSE", `SSE连接结束: ${reason}`, undefined, {
      sse: { taskId, event: "end", duration: durationMs },
    });
  }

  /**
   * SSE 事件
   */
  sseEvent(taskId: string, eventType: string, data?: unknown): void {
    this.log("DEBUG", "SSE", `SSE事件: ${eventType}`, data, {
      sse: { taskId, event: eventType },
    });
  }

  /**
   * SSE 错误
   */
  sseError(taskId: string, error: unknown): void {
    const errorMsg = error instanceof Error ? error.message : String(error);
    const errorStack = error instanceof Error ? error.stack : undefined;
    this.log("ERROR", "SSE", `SSE错误: ${errorMsg}`, errorStack, {
      sse: { taskId, event: "error" },
    });
  }

  /**
   * 内存快照
   */
  memorySnapshot(category: string, label?: string): void {
    const mem = this.getMemoryInfo();
    if (!mem) return;

    const msg = label ? `内存快照 [${label}]` : "内存快照";
    this.log("INFO", "MEMORY", msg, {
      heapUsedMB: Math.round(mem.heapUsed / 1024 / 1024 * 100) / 100,
      heapTotalMB: Math.round(mem.heapTotal / 1024 / 1024 * 100) / 100,
      rssMB: Math.round(mem.rss / 1024 / 1024 * 100) / 100,
      externalMB: Math.round(mem.external / 1024 / 1024 * 100) / 100,
    });
  }

  /**
   * 记录未捕获异常
   */
  uncaughtException(error: unknown, context?: string): void {
    const errorMsg = error instanceof Error ? error.message : String(error);
    const errorStack = error instanceof Error ? error.stack : undefined;
    this.log("ERROR", "UNCAUGHT", `未捕获异常${context ? ` (${context})` : ""}: ${errorMsg}`, errorStack);
  }

  /**
   * 记录未处理的 Promise 拒绝
   */
  unhandledRejection(reason: unknown, promise?: string): void {
    const reasonMsg = reason instanceof Error ? reason.message : String(reason);
    this.log("ERROR", "UNHANDLED", `未处理的Promise拒绝: ${reasonMsg}`, { promise });
  }

  /**
   * 清理旧日志（保留最近 N 天）
   */
  cleanOldLogs(keepDays = 7): number {
    this.init();

    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - keepDays);
    const cutoffStr = cutoffDate.toISOString().split("T")[0];

    let deletedCount = 0;

    try {
      const files = fs.readdirSync(LOG_DIR);
      for (const file of files) {
        if (!file.endsWith(".log")) continue;

        const match = file.match(/app-(\d{4}-\d{2}-\d{2})\.log/);
        if (match && match[1] < cutoffStr) {
          fs.unlinkSync(path.join(LOG_DIR, file));
          deletedCount++;
        }
      }
    } catch (e) {
      console.error("清理旧日志失败:", e);
    }

    return deletedCount;
  }

  /**
   * 获取日志文件列表
   */
  getLogFiles(): Array<{ name: string; size: number; modified: Date }> {
    this.init();

    try {
      const files = fs.readdirSync(LOG_DIR);
      return files
        .filter((f) => f.endsWith(".log"))
        .map((f) => {
          const stat = fs.statSync(path.join(LOG_DIR, f));
          return {
            name: f,
            size: stat.size,
            modified: stat.mtime,
          };
        })
        .sort((a, b) => b.modified.getTime() - a.modified.getTime());
    } catch {
      return [];
    }
  }

  // ==================== LLM 日志方法 ====================

  /**
   * 记录 LLM 请求
   */
  llmRequest(
    requestId: string,
    messages: unknown[],
    options: {
      tools?: unknown[];
      context?: LLMLogContext;
      workflowTraceSink?: WorkflowLLMTraceSink;
    } = {}
  ): void {
    const mode = getLLMLogMode();
    if (mode === "off") return;
    this.writeLLMLogRecord(buildLLMRequestLogRecord({
      requestId,
      messages,
      tools: options.tools,
      context: options.context,
      mode,
    }), false, options.workflowTraceSink);
    console.log(`[LLM] 请求 #${requestId} 已记录`);
  }

  /**
   * 记录 LLM 响应
   */
  llmResponse(
    requestId: string,
    content: string,
    usage?: LLMLogUsage,
    options: {
      context?: LLMLogContext;
      durationMs?: number;
      finishReason?: string;
      reasoningContent?: string;
      toolCalls?: unknown[];
      workflowTraceSink?: WorkflowLLMTraceSink;
    } = {}
  ): void {
    const mode = getLLMLogMode();
    if (mode === "off") return;
    this.writeLLMLogRecord(buildLLMResponseLogRecord({
      requestId,
      content,
      usage,
      context: options.context,
      durationMs: options.durationMs,
      finishReason: options.finishReason,
      reasoningContent: options.reasoningContent,
      toolCalls: options.toolCalls,
      mode,
    }), false, options.workflowTraceSink);
    console.log(`[LLM] 响应 #${requestId} 已记录 (${content.length} chars)`);
  }

  /**
   * 记录工具调用
   */
  llmToolCall(
    requestId: string,
    toolName: string,
    args: Record<string, unknown>,
    result: string,
    options: {
      context?: LLMLogContext;
      durationMs?: number;
      workflowTraceSink?: WorkflowLLMTraceSink;
    } = {}
  ): void {
    const mode = getLLMLogMode();
    if (mode === "off") return;
    this.writeLLMLogRecord(buildLLMToolCallLogRecord({
      requestId,
      toolName,
      args,
      result,
      context: options.context,
      durationMs: options.durationMs,
      mode,
    }), false, options.workflowTraceSink);
    console.log(`[LLM] 工具调用 ${toolName} #${requestId} 已记录`);
  }

  agentRunFinal(
    agentRunId: string,
    content: string,
    options: {
      context?: LLMLogContext;
      usage?: LLMLogUsage;
      finishReason?: string;
      toolCallCount?: number;
      controlEventTypes?: string[];
      workflowTraceSink?: WorkflowLLMTraceSink;
    } = {}
  ): void {
    const mode = getLLMLogMode();
    if (mode === "off") return;
    this.writeLLMLogRecord(buildAgentRunFinalLogRecord({
      agentRunId,
      content,
      context: options.context,
      usage: options.usage,
      finishReason: options.finishReason,
      toolCallCount: options.toolCallCount,
      controlEventTypes: options.controlEventTypes,
      mode,
    }), false, options.workflowTraceSink);
  }

  llmError(
    requestId: string,
    error: unknown,
    context?: LLMLogContext,
    workflowTraceSink?: WorkflowLLMTraceSink
  ): void {
    const message = error instanceof Error ? error.message : String(error);
    this.writeLLMLogRecord({
      ...(context ?? {}),
      timestamp: new Date().toISOString(),
      event: "ERROR",
      requestId,
      message,
    }, true, workflowTraceSink);
  }

  /**
   * 生成唯一请求 ID
   */
  generateRequestId(): string {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
}

/** 单例导出 */
export const logger = new LocalLogger();

/** 便捷方法 */
export const logError = (category: string, message: string, data?: unknown) =>
  logger.error(category, message, data);
export const logInfo = (category: string, message: string, data?: unknown) =>
  logger.info(category, message, data);
export const logWarn = (category: string, message: string, data?: unknown) =>
  logger.warn(category, message, data);
export const logDebug = (category: string, message: string, data?: unknown) =>
  logger.debug(category, message, data);

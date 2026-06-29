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
    preview: input.content.replace(/\s+/g, " ").trim().slice(0, LLM_LOG_PREVIEW_CHARS),
    durationMs: input.durationMs,
    finishReason: input.finishReason,
    usage: input.usage,
  };
  if (input.mode === "full") record.content = input.content;
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
  private getLLMLogFilePath(): string {
    this.init();
    const date = new Date().toISOString().split("T")[0];
    return path.join(LLM_LOG_DIR, `llm-${date}.jsonl`);
  }

  /**
   * 写入 LLM 日志
   */
  private writeLLMLogRecord(record: LLMLogRecord, force = false): void {
    if (!force && getLLMLogMode() === "off") return;
    try {
      const logPath = this.getLLMLogFilePath();
      fs.appendFileSync(logPath, JSON.stringify(record) + "\n", "utf-8");
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
    options: { tools?: unknown[]; context?: LLMLogContext } = {}
  ): void {
    const mode = getLLMLogMode();
    if (mode === "off") return;
    this.writeLLMLogRecord(buildLLMRequestLogRecord({
      requestId,
      messages,
      tools: options.tools,
      context: options.context,
      mode,
    }));
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
      mode,
    }));
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
    options: { context?: LLMLogContext; durationMs?: number } = {}
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
    }));
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
    }));
  }

  llmError(requestId: string, error: unknown, context?: LLMLogContext): void {
    const message = error instanceof Error ? error.message : String(error);
    this.writeLLMLogRecord({
      ...(context ?? {}),
      timestamp: new Date().toISOString(),
      event: "ERROR",
      requestId,
      message,
    }, true);
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

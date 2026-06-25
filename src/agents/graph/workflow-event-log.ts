/**
 * Workflow event file logger
 *
 * @module agents/graph/workflow-event-log
 * @description 将 LangGraph 执行事件和项目业务事件以 JSONL 形式追加写入本地文件。
 *  该日志只用于审计和调试，写入失败不能影响工作流执行。
 */

import fs from "fs";
import path from "path";
import { getAgentObservabilityConfig } from "@/shared/env";

const DEFAULT_LOG_DIR = path.join(process.cwd(), "logs", "workflow-events");
const SCHEMA_VERSION = 1;
const STRING_PREVIEW_LIMIT = 500;
const MAX_OBJECT_KEYS = 30;
const MAX_ARRAY_ITEMS = 5;
const VERBOSE_STRING_PREVIEW_LIMIT = 4000;
const VERBOSE_MAX_OBJECT_KEYS = 100;
const VERBOSE_MAX_ARRAY_ITEMS = 20;

const OMIT_KEYS = new Set([
  "streamCallbacks",
  "eventCallbacks",
]);

const SUMMARY_KEYS = new Set([
  "conversationHistory",
  "generatedContent",
  "messages",
  "novelData",
  "prompt",
  "systemPrompt",
]);

export interface WorkflowEventLogContext {
  taskId: string;
  runKind: "writing-workflow" | "resume-writing-workflow";
  userId?: string | null;
  novelId?: string | null;
  chapterId?: string | null;
  qualityCheckId?: string | null;
}

export interface WorkflowEventLogEntry {
  schemaVersion: number;
  runId: string;
  seq: number;
  timestamp: string;
  source: "workflow" | "langgraph" | "sse" | "persistence" | "error";
  eventType: string;
  taskId: string;
  runKind: WorkflowEventLogContext["runKind"];
  userId?: string | null;
  novelId?: string | null;
  chapterId?: string | null;
  qualityCheckId?: string | null;
  node?: string | null;
  agentId?: string | null;
  langGraphEvent?: string | null;
  changedKeys?: Record<string, string[]> | string[];
  payload?: unknown;
}

type WorkflowEventInput = Omit<
  WorkflowEventLogEntry,
  "schemaVersion" | "runId" | "seq" | "timestamp" | "taskId" | "runKind" |
  "userId" | "novelId" | "chapterId" | "qualityCheckId"
>;

function isLoggingEnabled(): boolean {
  return getAgentObservabilityConfig().workflowEventLogEnabled;
}

function isVerboseLoggingEnabled(): boolean {
  return process.env.WORKFLOW_EVENT_LOG_DETAIL === "verbose";
}

function getLogDir(): string {
  return process.env.WORKFLOW_EVENT_LOG_DIR || DEFAULT_LOG_DIR;
}

function createRunId(taskId: string): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${taskId}-${Date.now()}-${rand}`;
}

function getDailyLogPath(): string {
  const date = new Date().toISOString().slice(0, 10);
  return path.join(getLogDir(), `workflow-events-${date}.jsonl`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function summarizeLargeValue(value: unknown, verbose = isVerboseLoggingEnabled()): Record<string, unknown> {
  const stringLimit = verbose ? VERBOSE_STRING_PREVIEW_LIMIT : STRING_PREVIEW_LIMIT;
  const arrayLimit = verbose ? VERBOSE_MAX_ARRAY_ITEMS : MAX_ARRAY_ITEMS;

  if (typeof value === "string") {
    return {
      type: "string",
      length: value.length,
      preview: value.slice(0, stringLimit),
      truncated: value.length > stringLimit,
    };
  }

  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
      sample: value.slice(0, arrayLimit).map((item) => summarizeValue(item, 1)),
    };
  }

  if (isRecord(value)) {
    return {
      type: "object",
      keys: Object.keys(value),
    };
  }

  return { type: typeof value, value };
}

function summarizeValue(value: unknown, depth = 0): unknown {
  const verbose = isVerboseLoggingEnabled();
  const stringLimit = verbose ? VERBOSE_STRING_PREVIEW_LIMIT : STRING_PREVIEW_LIMIT;
  const objectKeyLimit = verbose ? VERBOSE_MAX_OBJECT_KEYS : MAX_OBJECT_KEYS;
  const arrayLimit = verbose ? VERBOSE_MAX_ARRAY_ITEMS : MAX_ARRAY_ITEMS;
  const maxDepth = verbose ? 5 : 2;

  if (value === null || value === undefined) return value;

  if (typeof value === "string") {
    if (value.length <= stringLimit) return value;
    return summarizeLargeValue(value, verbose);
  }

  if (typeof value === "number" || typeof value === "boolean") return value;

  if (Array.isArray(value)) {
    return {
      type: "array",
      length: value.length,
      sample: value.slice(0, arrayLimit).map((item) => summarizeValue(item, depth + 1)),
    };
  }

  if (!isRecord(value)) {
    return { type: typeof value, value: String(value) };
  }

  const keys = Object.keys(value);
  if (depth >= maxDepth) {
    return {
      type: "object",
      keys,
    };
  }

  const output: Record<string, unknown> = {};
  for (const key of keys.slice(0, objectKeyLimit)) {
    if (OMIT_KEYS.has(key)) {
      output[key] = "[omitted]";
      continue;
    }
    if (SUMMARY_KEYS.has(key) && !verbose) {
      output[key] = summarizeLargeValue(value[key], verbose);
      continue;
    }
    output[key] = summarizeValue(value[key], depth + 1);
  }

  if (keys.length > objectKeyLimit) {
    output.__truncatedKeys = keys.length - objectKeyLimit;
  }

  return output;
}

function extractChangedKeysFromUpdates(data: unknown): Record<string, string[]> | undefined {
  if (!isRecord(data)) return undefined;

  const changedKeys: Record<string, string[]> = {};
  for (const [node, update] of Object.entries(data)) {
    if (isRecord(update)) {
      changedKeys[node] = Object.keys(update);
    }
  }

  return Object.keys(changedKeys).length > 0 ? changedKeys : undefined;
}

function extractNode(data: unknown): string | null {
  if (!isRecord(data)) return null;
  const node = data.node;
  return typeof node === "string" ? node : null;
}

function extractAgentId(data: unknown): string | null {
  if (!isRecord(data)) return null;
  const agentId = data.agentId;
  return typeof agentId === "string" ? agentId : null;
}

export class WorkflowEventFileLogger {
  readonly runId: string;
  private context: WorkflowEventLogContext;
  private seq = 0;
  private initialized = false;
  private readonly enabled: boolean;

  constructor(context: WorkflowEventLogContext) {
    this.context = context;
    this.runId = createRunId(context.taskId);
    this.enabled = isLoggingEnabled();
  }

  isEnabledForTests(): boolean {
    return this.enabled;
  }

  setContext(patch: Partial<WorkflowEventLogContext>): void {
    this.context = { ...this.context, ...patch };
  }

  recordWorkflowEvent(eventType: string, payload?: unknown): void {
    this.record({
      source: "workflow",
      eventType,
      payload: summarizeValue(payload),
    });
  }

  recordPersistenceEvent(eventType: string, payload?: unknown): void {
    this.record({
      source: "persistence",
      eventType,
      payload: summarizeValue(payload),
    });
  }

  recordError(eventType: string, error: unknown, payload?: unknown): void {
    const errorPayload = {
      error: error instanceof Error
        ? { name: error.name, message: error.message, stack: error.stack }
        : String(error),
      payload: summarizeValue(payload),
    };
    this.record({
      source: "error",
      eventType,
      payload: summarizeValue(errorPayload),
    });
  }

  recordSSEEvent(type: string, data?: Record<string, unknown>): void {
    if (type === "agent_chunk") return;

    this.record({
      source: "sse",
      eventType: type,
      node: extractNode(data),
      agentId: extractAgentId(data),
      changedKeys: data?.changedKeys as string[] | undefined,
      payload: summarizeValue(data),
    });
  }

  recordLangGraphEvent(rawEvent: unknown): void {
    const event = isRecord(rawEvent) ? rawEvent : {};
    const eventType = typeof event.event === "string" ? event.event : "unknown";
    const data = event.data;

    this.record({
      source: "langgraph",
      eventType,
      langGraphEvent: eventType,
      node: typeof event.name === "string" ? event.name : extractNode(data),
      changedKeys: eventType === "updates" ? extractChangedKeysFromUpdates(data) : undefined,
      payload: summarizeValue({
        name: event.name,
        tags: event.tags,
        metadata: event.metadata,
        data,
      }),
    });
  }

  private init(): void {
    if (this.initialized || !this.enabled) return;
    fs.mkdirSync(getLogDir(), { recursive: true });
    this.initialized = true;
  }

  private record(input: WorkflowEventInput): void {
    if (!this.enabled) return;

    try {
      this.init();
      const entry: WorkflowEventLogEntry = {
        schemaVersion: SCHEMA_VERSION,
        runId: this.runId,
        seq: ++this.seq,
        timestamp: new Date().toISOString(),
        taskId: this.context.taskId,
        runKind: this.context.runKind,
        userId: this.context.userId,
        novelId: this.context.novelId,
        chapterId: this.context.chapterId,
        qualityCheckId: this.context.qualityCheckId,
        ...input,
      };
      fs.appendFileSync(getDailyLogPath(), `${JSON.stringify(entry)}\n`, "utf-8");
    } catch (error) {
      console.warn("[WORKFLOW_EVENT_LOG] 写入失败:", error);
    }
  }
}

export function createWorkflowEventFileLogger(
  context: WorkflowEventLogContext
): WorkflowEventFileLogger {
  return new WorkflowEventFileLogger(context);
}

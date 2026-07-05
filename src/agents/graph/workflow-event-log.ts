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
import { appendHumanWorkflowLog, getHumanWorkflowLogPath } from "@/shared/lib/logger";

const DEFAULT_LOG_DIR = path.join(process.cwd(), "logs", "workflow-events");
const SCHEMA_VERSION = 2;
const NOISY_SSE_EVENTS = new Set([
  "agent_chunk",
  "agent_status",
  "state_update",
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

interface ReadableWorkflowEventLogEntry {
  schemaVersion: number;
  seq: number;
  time: string;
  summary: string;
  eventType: string;
  source: WorkflowEventLogEntry["source"];
  node?: string | null;
  agent?: string | null;
  changedKeys?: Record<string, string[]> | string[];
  stateChanges?: Record<string, WorkflowStateChange>;
  payload?: unknown;
  context: {
    runId: string;
    taskId: string;
    runKind: WorkflowEventLogContext["runKind"];
    userId?: string | null;
    novelId?: string | null;
    chapterId?: string | null;
    qualityCheckId?: string | null;
  };
}

type WorkflowEventInput = Omit<
  WorkflowEventLogEntry,
  "schemaVersion" | "runId" | "seq" | "timestamp" | "taskId" | "runKind" |
  "userId" | "novelId" | "chapterId" | "qualityCheckId"
>;

function isLoggingEnabled(): boolean {
  return getAgentObservabilityConfig().workflowEventLogEnabled;
}

function getLogDir(): string {
  return process.env.WORKFLOW_EVENT_LOG_DIR || DEFAULT_LOG_DIR;
}

function shortRef(value: string): string {
  const parts = value.split("-");
  if (parts.length > 1) return parts.at(-1) || value.slice(-8);
  return value.length > 8 ? value.slice(-8) : value;
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

function sanitizeGraphStateForAudit(value: unknown, seen = new WeakSet<object>(), key?: string): unknown {
  if (key === "streamCallbacks" || key === "eventCallbacks") return "[runtime-only omitted]";
  if (key === "novelData") return "[untracked novel data omitted; inspect LLM input when needed]";
  if (value === null || value === undefined || typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "function") return "[function omitted]";
  if (Array.isArray(value)) return value.map((item) => sanitizeGraphStateForAudit(item, seen));
  if (!isRecord(value)) return String(value);
  if (seen.has(value)) return "[circular omitted]";
  seen.add(value);
  const output: Record<string, unknown> = {};
  for (const [childKey, childValue] of Object.entries(value)) {
    output[childKey] = sanitizeGraphStateForAudit(childValue, seen, childKey);
  }
  seen.delete(value);
  return output;
}

export type WorkflowStateProjection = Record<string, unknown>;

export interface WorkflowStateChange {
  before?: unknown;
  after?: unknown;
}

function putProjectionValue(
  output: WorkflowStateProjection,
  source: Record<string, unknown>,
  key: string,
  outputKey = key
): void {
  if (key in source) output[outputKey] = source[key];
}

export function projectWorkflowState(value: unknown): WorkflowStateProjection {
  if (!isRecord(value)) return {};
  const output: WorkflowStateProjection = {};
  for (const key of [
    "phase",
    "operationStep",
    "operationStage",
    "activeAgent",
    "reviewWorkerAgent",
    "errorMessage",
  ]) {
    putProjectionValue(output, value, key);
  }

  if ("currentOperation" in value) {
    const operation = value.currentOperation;
    if (isRecord(operation)) {
      output.operationKind = operation.kind;
      output.primaryAgent = operation.primaryAgent;
      output.reviewers = operation.reviewers;
      output.outputKind = operation.outputKind;
      output.requiresArtifact = operation.requiresArtifact;
      output.requiresUserApproval = operation.requiresUserApproval;
    } else {
      output.operationKind = null;
    }
  }

  if ("artifactReview" in value) {
    const review = value.artifactReview;
    if (isRecord(review)) {
      output.artifactStatus = review.status;
      output.activeArtifact = typeof review.activeArtifactId === "string" ? shortRef(review.activeArtifactId) : review.activeArtifactId;
      output.reviewerAgent = review.reviewerAgent;
      output.reviserAgent = review.reviserAgent;
      output.artifactIteration = review.iteration;
      output.maxArtifactIterations = review.maxIterations;
      if (isRecord(review.pendingRevision)) {
        output.pendingRevisionMode = review.pendingRevision.revisionMode;
      } else {
        output.pendingRevisionMode = null;
      }
    } else {
      output.artifactStatus = null;
      output.activeArtifact = null;
    }
  }

  if ("pendingAgentCall" in value) {
    const call = value.pendingAgentCall;
    output.pendingAgentCall = isRecord(call)
      ? `${String(call.fromAgent ?? "?")} → ${String(call.toAgent ?? "?")}：${String(call.reason ?? call.specificQuestion ?? "")}`
      : null;
  }
  if ("agentOutputs" in value) {
    output.agentOutputs = isRecord(value.agentOutputs) ? Object.keys(value.agentOutputs) : [];
  }
  if ("artifactReviewResults" in value) {
    output.artifactReviewResults = Array.isArray(value.artifactReviewResults)
      ? value.artifactReviewResults.map((item) => isRecord(item)
        ? `${String(item.reviewer ?? "?")}:${String(item.verdict ?? "?")}`
        : String(item))
      : [];
  }
  if ("conversationHistory" in value) {
    output.conversationCount = Array.isArray(value.conversationHistory) ? value.conversationHistory.length : 0;
  }
  if ("controlEvents" in value) {
    output.controlEvents = Array.isArray(value.controlEvents)
      ? value.controlEvents.map((item) => isRecord(item) ? String(item.type ?? "unknown") : String(item))
      : [];
  }
  return output;
}

export function diffWorkflowState(
  before: WorkflowStateProjection,
  after: WorkflowStateProjection
): Record<string, WorkflowStateChange> {
  const changes: Record<string, WorkflowStateChange> = {};
  for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (JSON.stringify(before[key]) === JSON.stringify(after[key])) continue;
    changes[key] = { before: before[key], after: after[key] };
  }
  return changes;
}

function extractUpdatesPayload(eventType: string, data: unknown): Record<string, unknown> | null {
  if (eventType === "updates" && isRecord(data)) return data;
  if (!isRecord(data) || !Array.isArray(data.chunk) || data.chunk[0] !== "updates") return null;
  return isRecord(data.chunk[1]) ? data.chunk[1] : null;
}

function getReadableSummary(entry: WorkflowEventLogEntry): string {
  const payload = payloadRecord(entry);
  const agent = entry.agentId ?? extractAgentId(payload) ?? "未知 Agent";
  const summaries: Record<string, string> = {
    sse_stream_created: "SSE 工作流连接已创建",
    sse_client_cancelled: "SSE 客户端已断开",
    workflow_started: "工作流开始",
    workflow_completed: "工作流完成",
    workflow_failed: "工作流失败",
    workflow_interrupted: "工作流等待用户输入",
    resume_started: "恢复工作流开始",
    resume_mode_selected: `恢复模式：${String(payload.mode ?? payload.resumeMode ?? "未知")}`,
    resume_completed: "恢复工作流完成",
    resume_failed: "恢复工作流失败",
    graph_initial_state: "LangGraph 初始状态",
    agent_start: `Agent #${String(payload.agentOrder ?? "?")} 开始：${agent}`,
    agent_done: `Agent #${String(payload.agentOrder ?? "?")} 完成：${agent}`,
    operation_classified: `创作操作已识别：${String(payload.operationKind ?? (isRecord(payload.operation) ? payload.operation.kind : "未知"))}`,
    operation_stage: `创作阶段：${String(payload.stage ?? "未知")}`,
    artifact_submitted: "草案已提交",
    artifact_review_started: "草案复审开始",
    artifact_awaiting_user_approval: "草案等待用户确认",
    artifact_applied: "草案已应用",
    artifact_deleted: "草案已删除",
    user_input_required: "等待用户输入",
    task_state_updated: "WritingTask 状态已持久化",
    history_loaded: "会话历史已加载",
    history_saved: "会话历史已保存",
  };
  if (entry.eventType === "node_completed") {
    return `LangGraph 节点 #${String(payload.nodeOrder ?? "?")} 完成：${entry.node ?? "unknown"}`;
  }
  if (entry.source === "error") return `错误：${entry.eventType}`;
  return summaries[entry.eventType] ?? `业务事件：${entry.eventType}`;
}

function toReadableLogEntry(entry: WorkflowEventLogEntry): ReadableWorkflowEventLogEntry {
  const payload = payloadRecord(entry);
  const stateChanges = isRecord(payload.stateChanges)
    ? payload.stateChanges as Record<string, WorkflowStateChange>
    : undefined;
  return {
    schemaVersion: entry.schemaVersion,
    seq: entry.seq,
    time: entry.timestamp,
    summary: getReadableSummary(entry),
    eventType: entry.eventType,
    source: entry.source,
    node: entry.node,
    agent: entry.agentId,
    changedKeys: entry.changedKeys,
    stateChanges,
    payload: entry.payload,
    context: {
      runId: entry.runId,
      taskId: entry.taskId,
      runKind: entry.runKind,
      userId: entry.userId,
      novelId: entry.novelId,
      chapterId: entry.chapterId,
      qualityCheckId: entry.qualityCheckId,
    },
  };
}

function formatTraceValue(value: unknown): string {
  if (value === undefined) return "（未设置）";
  if (value === null) return "null";
  if (typeof value === "string") return value || "（空）";
  return JSON.stringify(value);
}

function payloadRecord(entry: WorkflowEventLogEntry): Record<string, unknown> {
  return isRecord(entry.payload) ? entry.payload : {};
}

export function formatWorkflowTraceBlock(entry: WorkflowEventLogEntry): string | null {
  const payload = payloadRecord(entry);
  const header = `#${String(entry.seq).padStart(4, "0")} ${entry.timestamp}`;

  if (entry.eventType === "graph_initial_state") {
    const state = isRecord(payload.state) ? payload.state : payload;
    return `${header}  LANGGRAPH 初始状态\n${Object.entries(state)
      .map(([key, value]) => `  - ${key}: ${formatTraceValue(value)}`).join("\n")}` +
      `\n\n  【完整 GraphState】\n${JSON.stringify(payload.fullState ?? state, null, 2)}\n\n`;
  }
  if (entry.eventType === "node_completed") {
    const changes = isRecord(payload.stateChanges) ? payload.stateChanges : {};
    const lines = [
      `${header}  LANGGRAPH 节点 #${String(payload.nodeOrder ?? "?")} 完成：${entry.node ?? "unknown"}`,
      `  节点返回字段：${Array.isArray(entry.changedKeys) ? entry.changedKeys.join(", ") : "（无）"}`,
      "  状态变化：",
    ];
    const changeEntries = Object.entries(changes);
    if (changeEntries.length === 0) lines.push("  - （关键状态无变化）");
    for (const [key, change] of changeEntries) {
      const item = isRecord(change) ? change : {};
      lines.push(`  - ${key}: ${formatTraceValue(item.before)} → ${formatTraceValue(item.after)}`);
    }
    lines.push(`  当前关键状态：${formatTraceValue(payload.stateAfter)}`);
    lines.push("", "  【节点返回的完整 state patch】", JSON.stringify(payload.rawUpdate ?? {}, null, 2));
    return `${lines.join("\n")}\n\n`;
  }
  if (entry.eventType === "agent_start") {
    return `${header}  AGENT 调用 #${String(payload.agentOrder ?? "?")} 开始：${entry.agentId ?? payload.agentId ?? "unknown"}\n` +
      `  名称：${String(payload.agentName ?? "")}` +
      `\n  后续 LLM 输入、输出和工具调用将直接接在本文件中。\n\n`;
  }
  if (entry.eventType === "agent_done") {
    return `${header}  AGENT 调用 #${String(payload.agentOrder ?? "?")} 完成：${entry.agentId ?? payload.agentId ?? "unknown"}\n` +
      `  耗时：${String(payload.durationMs ?? "?")}ms | 有输出：${String(payload.hasOutput ?? false)}\n\n`;
  }
  if (entry.eventType === "operation_classified") {
    const operation = isRecord(payload.operation) ? payload.operation : payload;
    return `${header}  OPERATION 已识别\n  类型：${String(operation.kind ?? payload.operationKind ?? "unknown")} | 主责 Agent：${String(operation.primaryAgent ?? payload.agentId ?? "unknown")} | 审核 Agent：${formatTraceValue(operation.reviewers)}\n\n`;
  }
  if (entry.eventType === "operation_stage") {
    return `${header}  OPERATION 阶段：${String(payload.stage ?? "unknown")}\n  ${String(payload.message ?? "")}\n\n`;
  }
  if (entry.eventType === "workflow_started") {
    return `${header}  WORKFLOW 开始\n  task=${shortRef(entry.taskId)} | kind=${entry.runKind}\n\n`;
  }
  if (entry.eventType === "workflow_completed" || entry.eventType === "workflow_failed" || entry.eventType === "workflow_interrupted") {
    return `${header}  WORKFLOW ${entry.eventType.replace("workflow_", "").toUpperCase()}\n  ${formatTraceValue(payload)}\n\n`;
  }
  if (entry.source === "error") {
    return `${header}  ERROR：${entry.eventType}\n  ${formatTraceValue(payload)}\n\n`;
  }
  if (["artifact_submitted", "artifact_review_started", "artifact_awaiting_user_approval", "artifact_applied", "artifact_deleted", "user_input_required"].includes(entry.eventType)) {
    return `${header}  业务事件：${entry.eventType}\n  ${formatTraceValue(payload)}\n\n`;
  }
  return null;
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
  private stateProjection: WorkflowStateProjection = {};
  private nodeOrder = 0;
  private agentOrder = 0;
  private readonly activeAgentOrders = new Map<string, number[]>();
  private traceRunPath: string | null = null;

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

  recordGraphInitialState(state: unknown): void {
    this.stateProjection = projectWorkflowState(state);
    this.record({
      source: "langgraph",
      eventType: "graph_initial_state",
      changedKeys: Object.keys(this.stateProjection),
      payload: {
        state: this.stateProjection,
        fullState: sanitizeGraphStateForAudit(state),
      },
    });
  }

  recordWorkflowEvent(eventType: string, payload?: unknown): void {
    this.record({
      source: "workflow",
      eventType,
      payload: sanitizeGraphStateForAudit(payload),
    });
  }

  recordPersistenceEvent(eventType: string, payload?: unknown): void {
    this.record({
      source: "persistence",
      eventType,
      payload: sanitizeGraphStateForAudit(payload),
    });
  }

  recordError(eventType: string, error: unknown, payload?: unknown): void {
    const errorPayload = {
      error: error instanceof Error
        ? { name: error.name, message: error.message, stack: error.stack }
        : String(error),
      payload: sanitizeGraphStateForAudit(payload),
    };
    this.record({
      source: "error",
      eventType,
      payload: sanitizeGraphStateForAudit(errorPayload),
    });
  }

  recordSSEEvent(type: string, data?: Record<string, unknown>): void {
    if (NOISY_SSE_EVENTS.has(type)) return;

    const payload = { ...(data ?? {}) };
    if (type === "agent_start") {
      const order = ++this.agentOrder;
      payload.agentOrder = order;
      const agentId = extractAgentId(data) ?? "unknown";
      const queue = this.activeAgentOrders.get(agentId) ?? [];
      queue.push(order);
      this.activeAgentOrders.set(agentId, queue);
    } else if (type === "agent_done") {
      const agentId = extractAgentId(data) ?? "unknown";
      const queue = this.activeAgentOrders.get(agentId) ?? [];
      payload.agentOrder = queue.shift() ?? "?";
      if (queue.length === 0) this.activeAgentOrders.delete(agentId);
    }

    this.record({
      source: "sse",
      eventType: type,
      node: extractNode(data),
      agentId: extractAgentId(data),
      changedKeys: data?.changedKeys as string[] | undefined,
      payload: sanitizeGraphStateForAudit(payload),
    });
  }

  recordLangGraphEvent(rawEvent: unknown): void {
    const event = isRecord(rawEvent) ? rawEvent : {};
    const eventType = typeof event.event === "string" ? event.event : "unknown";
    const data = event.data;
    const updates = extractUpdatesPayload(eventType, data);

    if (updates) {
      for (const [node, update] of Object.entries(updates)) {
        if (!isRecord(update)) continue;
        const patch = projectWorkflowState(update);
        const nextState = { ...this.stateProjection, ...patch };
        const stateChanges = diffWorkflowState(this.stateProjection, nextState);
        this.stateProjection = nextState;
        this.record({
          source: "langgraph",
          eventType: "node_completed",
          langGraphEvent: eventType,
          node,
          changedKeys: Object.keys(update),
          payload: {
            nodeOrder: ++this.nodeOrder,
            stateChanges,
            stateAfter: this.stateProjection,
            rawUpdate: sanitizeGraphStateForAudit(update),
          },
        });
      }
      return;
    }

    // streamEvents 会为每个 Runnable 产生大量 on_chain_* 包装事件。这些事件不代表
    // 业务步骤，写入后会淹没真实的节点、Agent 和状态变化。仅错误值得进入人工时间线。
    if (eventType === "on_chain_error" || eventType === "on_tool_error") {
      this.record({
        source: "error",
        eventType: "langgraph_runtime_error",
        langGraphEvent: eventType,
        node: typeof event.name === "string" ? event.name : extractNode(data),
        payload: sanitizeGraphStateForAudit(data),
      });
    }
  }

  private init(): void {
    if (this.initialized || !this.enabled) return;
    fs.mkdirSync(getLogDir(), { recursive: true });
    this.traceRunPath = getHumanWorkflowLogPath(this.context.taskId, new Date().toISOString());
    appendHumanWorkflowLog(this.context.taskId, new Date().toISOString(), [
      "=".repeat(100),
      "工作流运行",
      `开始时间: ${new Date().toISOString()}`,
      `任务: ${shortRef(this.context.taskId)} | 类型: ${this.context.runKind}`,
      "阅读顺序: LangGraph 状态 → 节点 → Agent → LLM 输入/输出 → 工具输入/返回。",
      "说明: 下文按实际发生顺序追加；LLM 与工具内容均为原文，不做摘要或截断。",
      "=".repeat(100),
      "",
    ].join("\n"));
    this.initialized = true;
  }

  private writeHumanTrace(entry: WorkflowEventLogEntry): void {
    const block = formatWorkflowTraceBlock(entry);
    if (!block || !this.traceRunPath) return;
    appendHumanWorkflowLog(entry.taskId, entry.timestamp, block);
  }

  private record(input: WorkflowEventInput): void {
    if (!this.enabled) return;
    if (process.env.NODE_TEST_CONTEXT && process.env.WORKFLOW_LOG_WRITE_IN_TESTS !== "true") return;

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
      if (process.env.WORKFLOW_MACHINE_EVENT_LOG_ENABLED === "true") {
        fs.appendFileSync(getDailyLogPath(), `${JSON.stringify(toReadableLogEntry(entry))}\n`, "utf-8");
      }
      this.writeHumanTrace(entry);
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

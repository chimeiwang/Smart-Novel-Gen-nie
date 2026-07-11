/**
 * Workflow event file logger
 *
 * @module agents/graph/workflow-event-log
 * @description 将 LangGraph、Agent、LLM 和工具事件整理为单个可直接阅读的任务日志。
 *  可选机器 JSONL 仅作辅助；任何日志写入失败都不能影响工作流执行。
 */

import fs from "fs";
import path from "path";
import { getAgentObservabilityConfig } from "@/shared/env";
import {
  formatLLMWorkflowBlock,
  getHumanWorkflowLogPath,
  type LLMLogRecord,
} from "@/shared/lib/logger";

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

type WorkflowTraceItem =
  | { seq: number; timestamp: string; kind: "workflow"; entry: WorkflowEventLogEntry }
  | { seq: number; timestamp: string; kind: "llm"; record: LLMLogRecord };

interface WorkflowStateRecord {
  ref: string;
  label: string;
  projection: WorkflowStateProjection;
  changes?: Record<string, WorkflowStateChange>;
}

interface UpdatesEnvelope {
  namespace: string[];
  updates: Record<string, unknown>;
}

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
  if (key === "streamCallbacks" || key === "eventCallbacks" || key === "workflowTrace") {
    return "[runtime-only omitted]";
  }
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

function extractUpdatesPayload(eventType: string, data: unknown): UpdatesEnvelope | null {
  if (eventType === "updates" && isRecord(data)) {
    return { namespace: [], updates: data };
  }
  if (!isRecord(data) || !Array.isArray(data.chunk)) return null;
  const chunk = data.chunk;
  if (chunk[0] === "updates" && isRecord(chunk[1])) {
    return { namespace: [], updates: chunk[1] };
  }
  if (
    Array.isArray(chunk[0]) &&
    chunk[1] === "updates" &&
    isRecord(chunk[2])
  ) {
    return {
      namespace: chunk[0].filter((item): item is string => typeof item === "string"),
      updates: chunk[2],
    };
  }
  return null;
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

const STATE_FIELD_LABELS: Record<string, string> = {
  phase: "工作流状态",
  operationStep: "当前步骤",
  operationStage: "步骤说明",
  activeAgent: "当前 Agent",
  reviewWorkerAgent: "当前审核分支",
  errorMessage: "错误信息",
  operationKind: "创作操作",
  primaryAgent: "主责 Agent",
  reviewers: "审核 Agent",
  outputKind: "输出类型",
  requiresArtifact: "需要生成草案",
  requiresUserApproval: "需要用户确认",
  artifactStatus: "草案状态",
  activeArtifact: "当前草案",
  reviewerAgent: "作出返工决定的审核 Agent",
  reviserAgent: "返工 Agent",
  artifactIteration: "当前审核轮次",
  maxArtifactIterations: "最大审核轮次",
  pendingRevisionMode: "返工方式",
  pendingAgentCall: "待执行 Agent 任务",
  agentOutputs: "已有 Agent 输出",
  artifactReviewResults: "审核结果",
  conversationCount: "对话消息数",
  controlEvents: "控制事件",
};

const STATE_VALUE_LABELS: Record<string, Record<string, string>> = {
  phase: {
    idle: "空闲",
    active: "执行中",
    waiting_call: "等待 Agent 调用确认",
    awaiting_user_review: "等待用户审核",
    completed: "已完成",
    error: "失败",
  },
  operationStep: {
    init: "初始化",
    classify_operation: "识别创作操作",
    prepare_context: "准备操作上下文",
    execute_operation: "执行创作操作",
    submit_artifact: "提交草案或回复",
    review_artifact: "审核草案",
    apply_artifact_patch: "应用局部修改",
    revise_artifact: "返工草案",
    await_user_decision: "等待用户决定",
    suggest_next_action: "建议下一步",
    completed: "完成",
    error: "失败",
  },
  operationKind: {
    answer_question: "回答问题",
    create_lore: "创建设定",
    revise_lore: "修改设定",
    create_outline: "创建大纲",
    revise_outline: "修改大纲",
    plan_chapter: "规划章节",
    write_chapter: "生成章节正文",
    rewrite_scene: "重写场景",
    review_chapter: "审核章节",
    sync_lore: "同步设定",
    manage_foreshadowing: "管理伏笔",
  },
  outputKind: {
    chat_answer: "聊天回复",
    lore_proposal: "设定草案",
    outline_proposal: "大纲草案",
    beat_plan: "章节节拍计划",
    chapter_text: "章节正文",
    review_report: "审核报告",
    revision_brief: "返工说明",
    sync_proposal: "同步草案",
  },
  artifactStatus: {
    none: "无草案",
    idle: "无草案",
    draft: "草稿",
    draft_submitted: "草案已提交",
    under_review: "审核中",
    reviewing: "审核中",
    revision_requested: "已要求返工",
    awaiting_user: "等待用户确认",
    applying: "正在应用",
    applied: "已应用",
    discarded: "已丢弃",
    deleted: "已删除",
  },
  pendingRevisionMode: {
    patch: "局部修改",
    rewrite: "整稿重写",
  },
};

const REVIEW_VERDICT_LABELS: Record<string, string> = {
  pass: "通过",
  revise: "返工",
  block: "阻断",
};

const NODE_LABELS: Record<string, string> = {
  initSession: "初始化会话",
  prepareOperationContext: "准备操作上下文",
  executeOperation: "执行创作操作",
  submitArtifactOrRespond: "提交草案或直接回复",
  reviewArtifact: "分发草案审核",
  reviewArtifactWorker: "审核分支完成（并行分支局部状态）",
  mergeArtifactReviews: "汇总审核结果",
  applyArtifactPatch: "应用草案局部修改",
  reviseArtifact: "准备草案返工",
  awaitUserDecision: "等待用户决定",
  suggestNextStep: "建议下一步",
  statusReport: "生成状态报告",
};

function formatChineseStateValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "无";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) {
    if (value.length === 0) return "无";
    if (key === "artifactReviewResults") {
      return value.map((item) => {
        const [agent, verdict] = String(item).split(":");
        return verdict ? `${agent}：${REVIEW_VERDICT_LABELS[verdict] ?? `未翻译结论（${verdict}）`}` : agent;
      }).join("、");
    }
    return value.map((item) => String(item)).join("、");
  }
  if (typeof value === "string") {
    const vocabulary = STATE_VALUE_LABELS[key];
    if (vocabulary) return vocabulary[value] ?? `未翻译值（${value}）`;
    return value || "空";
  }
  return JSON.stringify(value);
}

function translateStateLabel(label: string): string {
  if (label === "LangGraph 初始状态") return "LangGraph 初始状态";
  const agentMatch = label.match(/^(A\d+) 输入状态$/);
  if (agentMatch) return `${agentMatch[1]} Agent 调用前状态`;
  const nodeName = label.replace(/ 完成后$/, "").split("/").at(-1) ?? label;
  return `${NODE_LABELS[nodeName] ?? `未翻译节点（${nodeName}）`}完成后的状态`;
}

function renderChineseStateFields(projection: WorkflowStateProjection): string {
  const entries = Object.entries(projection);
  if (entries.length === 0) return "  - 无关键状态";
  return entries.map(([key, value]) =>
    `  - ${STATE_FIELD_LABELS[key] ?? `未翻译字段（${key}）`}：${formatChineseStateValue(key, value)}`
  ).join("\n");
}

function renderChineseStateChanges(changes: Record<string, WorkflowStateChange>): string {
  const entries = Object.entries(changes);
  if (entries.length === 0) return "  - 无关键状态变化";
  return entries.map(([key, change]) =>
    `  - ${STATE_FIELD_LABELS[key] ?? `未翻译字段（${key}）`}：` +
      `${formatChineseStateValue(key, change.before)} → ${formatChineseStateValue(key, change.after)}`
  ).join("\n");
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
  private readonly traceItems: WorkflowTraceItem[] = [];
  private readonly stateRecords: WorkflowStateRecord[] = [];
  private stateVersion = 0;
  private previousTraceContent = "";
  private runNumber = 1;

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

  createRuntimeTrace(): NonNullable<import("./state").WritingRuntimeContext["workflowTrace"]> {
    return {
      allocateAgentCallId: (agentId) => this.allocateAgentCallId(agentId),
      captureState: (state, label) => this.captureState(state, label),
      recordLLM: (record) => this.recordLLMRecord(record),
    };
  }

  private allocateAgentCallId(_agentId: string): string {
    return `A${String(++this.agentOrder).padStart(2, "0")}`;
  }

  private captureState(state: unknown, label: string): string {
    const ref = `S${String(++this.stateVersion).padStart(3, "0")}`;
    this.stateRecords.push({
      ref,
      label,
      projection: projectWorkflowState(state),
    });
    return ref;
  }

  private recordLLMRecord(record: LLMLogRecord): void {
    if (!this.enabled) return;
    if (process.env.NODE_TEST_CONTEXT && process.env.WORKFLOW_LOG_WRITE_IN_TESTS !== "true") return;
    try {
      this.init();
      const seq = ++this.seq;
      this.traceItems.push({
        seq,
        timestamp: record.timestamp,
        kind: "llm",
        record,
      });
      this.writeHumanTrace();
    } catch (error) {
      console.warn("[WORKFLOW_EVENT_LOG] LLM 日志写入失败:", error);
    }
  }

  recordGraphInitialState(state: unknown): void {
    this.stateProjection = projectWorkflowState(state);
    const stateRef = this.captureState(state, "LangGraph 初始状态");
    this.record({
      source: "langgraph",
      eventType: "graph_initial_state",
      changedKeys: Object.keys(this.stateProjection),
      payload: {
        state: this.stateProjection,
        fullState: sanitizeGraphStateForAudit(state),
        stateRef,
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
      const providedCallId = typeof data?.agentCallId === "string" ? data.agentCallId : null;
      const providedOrder = providedCallId?.match(/^A(\d+)$/)?.[1];
      const order = providedOrder ? Number(providedOrder) : ++this.agentOrder;
      payload.agentOrder = order;
      payload.agentCallId = providedCallId ?? `A${String(order).padStart(2, "0")}`;
      const agentId = extractAgentId(data) ?? "unknown";
      const queue = this.activeAgentOrders.get(agentId) ?? [];
      queue.push(order);
      this.activeAgentOrders.set(agentId, queue);
    } else if (type === "agent_done") {
      const agentId = extractAgentId(data) ?? "unknown";
      const queue = this.activeAgentOrders.get(agentId) ?? [];
      const providedCallId = typeof data?.agentCallId === "string" ? data.agentCallId : null;
      const providedOrder = providedCallId?.match(/^A(\d+)$/)?.[1];
      const queuedOrder = queue.shift();
      payload.agentOrder = providedOrder ? Number(providedOrder) : queuedOrder ?? "?";
      payload.agentCallId = providedCallId ?? (
        typeof payload.agentOrder === "number"
          ? `A${String(payload.agentOrder).padStart(2, "0")}`
          : "?"
      );
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
    const updatesEnvelope = extractUpdatesPayload(eventType, data);

    if (updatesEnvelope) {
      for (const [node, update] of Object.entries(updatesEnvelope.updates)) {
        if (!isRecord(update)) continue;
        const patch = projectWorkflowState(update);
        const nextState = { ...this.stateProjection, ...patch };
        const stateChanges = diffWorkflowState(this.stateProjection, nextState);
        this.stateProjection = nextState;
        const stateRef = `S${String(++this.stateVersion).padStart(3, "0")}`;
        this.stateRecords.push({
          ref: stateRef,
          label: `${updatesEnvelope.namespace.length > 0 ? `${updatesEnvelope.namespace.join("/")}/` : ""}${node} 完成后`,
          projection: nextState,
          changes: stateChanges,
        });
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
            stateRef,
            namespace: updatesEnvelope.namespace,
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

  private renderLLMRecords(): string {
    const llmItems = this.traceItems.filter((item): item is Extract<WorkflowTraceItem, { kind: "llm" }> =>
      item.kind === "llm" && (item.record.event === "REQUEST" || item.record.event === "RESPONSE")
    );
    if (llmItems.length === 0) return "（尚无 LLM 请求或返回）";

    const groups = new Map<string, Extract<WorkflowTraceItem, { kind: "llm" }>[]>();
    for (const item of llmItems) {
      const callId = typeof item.record.agentRunId === "string" && item.record.agentRunId
        ? item.record.agentRunId
        : "通用调用";
      const records = groups.get(callId) ?? [];
      records.push(item);
      groups.set(callId, records);
    }

    return Array.from(groups.entries())
      .sort(([, left], [, right]) => left[0].seq - right[0].seq)
      .map(([callId, items]) => {
        const agentId = items.find((item) => typeof item.record.agentId === "string")?.record.agentId ?? "通用";
        const stateRef = items.find((item) => typeof item.record.stateRef === "string")?.record.stateRef;
        const title = `## ${callId} ${String(agentId)}${stateRef ? `｜调用前状态 ${String(stateRef)}` : ""}`;
        const blocks = items.map((item) => formatLLMWorkflowBlock(item.record)).filter(Boolean).join("\n");
        return `${title}\n\n${blocks}`;
      }).join("\n");
  }

  private renderLangGraphStates(): string {
    if (this.stateRecords.length === 0) return "（尚无 LangGraph 状态）";
    return this.stateRecords.map((state) => {
      const lines = [`## ${state.ref} ${translateStateLabel(state.label)}`];
      if (state.changes) {
        lines.push("", "本次状态变化：", renderChineseStateChanges(state.changes));
      }
      lines.push("", "当前完整状态：", renderChineseStateFields(state.projection));
      return lines.join("\n");
    }).join("\n\n");
  }

  private renderHumanRun(): string {
    const first = this.traceItems[0];
    const last = this.traceItems.at(-1);
    const terminalEntry = [...this.traceItems].reverse().find((item) =>
      item.kind === "workflow" && [
        "workflow_completed",
        "workflow_failed",
        "workflow_interrupted",
        "resume_completed",
        "resume_failed",
      ].includes(item.entry.eventType)
    );
    const status = terminalEntry?.kind === "workflow"
      ? terminalEntry.entry.eventType === "workflow_failed" || terminalEntry.entry.eventType === "resume_failed"
          ? "失败"
          : terminalEntry.entry.eventType === "workflow_interrupted" ||
              ["waiting_call", "awaiting_user_review"].includes(String(payloadRecord(terminalEntry.entry).phase ?? ""))
            ? "等待用户输入"
            : "已完成"
      : "运行中";
    const startedAt = first?.timestamp ?? new Date().toISOString();
    const endedAt = last?.timestamp ?? startedAt;
    const durationMs = Math.max(0, Date.parse(endedAt) - Date.parse(startedAt));
    const llmResponses = this.traceItems.filter((item) => item.kind === "llm" && item.record.event === "RESPONSE").length;
    const agents = this.traceItems.filter((item) => item.kind === "workflow" && item.entry.eventType === "agent_start").length;
    const operationEntry = this.traceItems.find((item) => item.kind === "workflow" && item.entry.eventType === "operation_classified");
    const operationPayload = operationEntry?.kind === "workflow" ? payloadRecord(operationEntry.entry) : {};
    const operation = isRecord(operationPayload.operation) ? operationPayload.operation : operationPayload;

    return [
      "=".repeat(100),
      `工作流运行 R${String(this.runNumber).padStart(2, "0")}`,
      `任务: ${shortRef(this.context.taskId)} | 类型: ${this.context.runKind} | 状态: ${status}`,
      `时间: ${startedAt} → ${endedAt} | 耗时: ${durationMs}ms`,
      `操作: ${formatChineseStateValue("operationKind", operation.kind ?? this.stateProjection.operationKind ?? null)} | Agent 调用: ${agents} | LLM 响应: ${llmResponses}`,
      "说明: 文件只包含 LLM 输入 messages 原文、模型输出正文原文与 LangGraph 中文状态切换。",
      "=".repeat(100),
      "",
      "# 一、LLM 输入与输出原文",
      "",
      this.renderLLMRecords(),
      "",
      "# 二、LangGraph 状态切换（中文）",
      "",
      this.renderLangGraphStates(),
      "",
    ].join("\n");
  }

  private init(): void {
    if (this.initialized || !this.enabled) return;
    fs.mkdirSync(getLogDir(), { recursive: true });
    this.traceRunPath = getHumanWorkflowLogPath(this.context.taskId, new Date().toISOString());
    fs.mkdirSync(path.dirname(this.traceRunPath), { recursive: true });
    if (fs.existsSync(this.traceRunPath)) {
      this.previousTraceContent = fs.readFileSync(this.traceRunPath, "utf-8").trimEnd();
      this.runNumber = (this.previousTraceContent.match(/^工作流运行 R\d+/gm)?.length ?? 0) + 1;
    }
    this.initialized = true;
  }

  private writeHumanTrace(): void {
    if (!this.traceRunPath) return;
    const hasVisibleLLMRecord = this.traceItems.some((item) =>
      item.kind === "llm" && (item.record.event === "REQUEST" || item.record.event === "RESPONSE")
    );
    if (!hasVisibleLLMRecord && this.stateRecords.length === 0) return;
    const current = this.renderHumanRun();
    const content = this.previousTraceContent
      ? `${this.previousTraceContent}\n\n${current}`
      : current;
    const tempPath = `${this.traceRunPath}.${shortRef(this.runId)}.tmp`;
    fs.writeFileSync(tempPath, content, "utf-8");
    fs.renameSync(tempPath, this.traceRunPath);
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
      this.traceItems.push({
        seq: entry.seq,
        timestamp: entry.timestamp,
        kind: "workflow",
        entry,
      });
      this.writeHumanTrace();
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

/**
 * Workflow event debug API
 *
 * @module app/api/debug/workflow-events
 * @description 从本地 JSONL 审计日志读取 LangGraph 工作流事件，用于开发调试页回放。
 */

import fs from "fs";
import path from "path";
import { NextRequest } from "next/server";

import { getAgentObservabilityConfig } from "@/shared/env";
import { getSession } from "@/shared/lib/auth";
import { logger } from "@/shared/lib/logger";
import { readRecentNonEmptyLines } from "./workflow-event-log-reader";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type WorkflowEventSource = "workflow" | "langgraph" | "sse" | "persistence" | "error";

interface WorkflowEventLogEntry {
  schemaVersion: number;
  runId: string;
  seq: number;
  timestamp: string;
  source: WorkflowEventSource;
  eventType: string;
  taskId: string;
  runKind: "writing-workflow" | "resume-writing-workflow";
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

interface WorkflowRunSummary {
  runId: string;
  taskId: string;
  runKind: WorkflowEventLogEntry["runKind"];
  userId?: string | null;
  novelId?: string | null;
  chapterId?: string | null;
  qualityCheckId?: string | null;
  startedAt: string;
  endedAt: string;
  eventCount: number;
  status: "completed" | "interrupted" | "error" | "active";
  sources: WorkflowEventSource[];
  nodes: string[];
  agents: string[];
}

const MAX_FILES = 14;
const MAX_LINES_PER_FILE = 20_000;
const DEFAULT_LOG_DIR = path.join(process.cwd(), "logs", "workflow-events");

function getLogDir(): string {
  return process.env.WORKFLOW_EVENT_LOG_DIR || DEFAULT_LOG_DIR;
}

function readLogFiles(): string[] {
  const dir = getLogDir();
  if (!fs.existsSync(dir)) return [];

  return fs.readdirSync(dir)
    .filter((file) => /^workflow-events-\d{4}-\d{2}-\d{2}\.jsonl$/.test(file))
    .sort()
    .reverse()
    .slice(0, MAX_FILES)
    .map((file) => path.join(dir, file));
}

function parseEntry(line: string): WorkflowEventLogEntry | null {
  try {
    const parsed = JSON.parse(line) as Partial<WorkflowEventLogEntry>;
    if (!parsed.runId || !parsed.taskId || !parsed.eventType || !parsed.timestamp) {
      return null;
    }
    return parsed as WorkflowEventLogEntry;
  } catch {
    return null;
  }
}

function readEntries(): WorkflowEventLogEntry[] {
  const entries: WorkflowEventLogEntry[] = [];

  for (const file of readLogFiles()) {
    const lines = readRecentNonEmptyLines(file, MAX_LINES_PER_FILE);
    for (const line of lines) {
      const entry = parseEntry(line);
      if (entry) entries.push(entry);
    }
  }

  return entries.sort((a, b) => {
    if (a.runId === b.runId) return a.seq - b.seq;
    return a.timestamp.localeCompare(b.timestamp);
  });
}

function getEntryNodes(entry: WorkflowEventLogEntry): string[] {
  const nodes = new Set<string>();

  if (entry.node) nodes.add(entry.node);

  if (
    entry.source === "langgraph" &&
    entry.eventType === "updates" &&
    entry.changedKeys &&
    !Array.isArray(entry.changedKeys)
  ) {
    for (const node of Object.keys(entry.changedKeys)) {
      nodes.add(node);
    }
  }

  return Array.from(nodes);
}

function isVisibleToUser(entries: WorkflowEventLogEntry[], userId: string): boolean {
  const userIds = entries
    .map((entry) => entry.userId)
    .filter((value): value is string => Boolean(value));

  return userIds.length === 0 || userIds.includes(userId);
}

function summarizeRun(entries: WorkflowEventLogEntry[]): WorkflowRunSummary {
  const first = entries[0];
  const last = entries[entries.length - 1];
  const sources = new Set<WorkflowEventSource>();
  const nodes = new Set<string>();
  const agents = new Set<string>();
  let status: WorkflowRunSummary["status"] = "active";

  for (const entry of entries) {
    sources.add(entry.source);
    if (entry.agentId) agents.add(entry.agentId);
    for (const node of getEntryNodes(entry)) nodes.add(node);

    if (entry.source === "error" || entry.eventType === "error" || entry.eventType.endsWith("_error")) {
      status = "error";
    } else if (status !== "error" && entry.eventType.includes("interrupted")) {
      status = "interrupted";
    } else if (
      status === "active" &&
      ["workflow_completed", "resume_completed", "done"].includes(entry.eventType)
    ) {
      status = "completed";
    }
  }

  return {
    runId: first.runId,
    taskId: first.taskId,
    runKind: first.runKind,
    userId: first.userId,
    novelId: first.novelId,
    chapterId: first.chapterId,
    qualityCheckId: first.qualityCheckId,
    startedAt: first.timestamp,
    endedAt: last.timestamp,
    eventCount: entries.length,
    status,
    sources: Array.from(sources),
    nodes: Array.from(nodes),
    agents: Array.from(agents),
  };
}

function groupEntries(entries: WorkflowEventLogEntry[]): Map<string, WorkflowEventLogEntry[]> {
  const grouped = new Map<string, WorkflowEventLogEntry[]>();
  for (const entry of entries) {
    const list = grouped.get(entry.runId) ?? [];
    list.push(entry);
    grouped.set(entry.runId, list);
  }
  return grouped;
}

export function isWorkflowEventDebugEnabled(): boolean {
  return getAgentObservabilityConfig().workflowEventDebugEnabled;
}

export async function GET(request: NextRequest) {
  try {
    if (!isWorkflowEventDebugEnabled()) {
      return new Response(null, { status: 404 });
    }

    const session = await getSession();
    if (!session) {
      return Response.json({ error: "未登录" }, { status: 401 });
    }

    const searchParams = request.nextUrl.searchParams;
    const runId = searchParams.get("runId");
    const taskId = searchParams.get("taskId");

    const grouped = groupEntries(readEntries());
    const visibleGroups = Array.from(grouped.entries())
      .filter(([, entries]) => isVisibleToUser(entries, session.userId));

    const runs = visibleGroups
      .map(([, entries]) => summarizeRun(entries))
      .filter((run) => !taskId || run.taskId === taskId)
      .sort((a, b) => b.startedAt.localeCompare(a.startedAt));

    if (!runId) {
      return Response.json({ runs, events: [] });
    }

    const selected = visibleGroups.find(([id]) => id === runId);
    if (!selected) {
      return Response.json({ error: "运行记录不存在或无权访问" }, { status: 404 });
    }

    const events = selected[1].sort((a, b) => a.seq - b.seq);
    return Response.json({
      runs,
      selectedRun: summarizeRun(events),
      events,
    });
  } catch (error) {
    logger.error("API", "读取 workflow event 日志失败", { error: String(error) });
    return Response.json({ error: "读取 workflow event 日志失败" }, { status: 500 });
  }
}

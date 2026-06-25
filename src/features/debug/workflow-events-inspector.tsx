"use client";

import { useEffect, useMemo, useState } from "react";

import styles from "./workflow-events-inspector.module.css";

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
  novelId?: string | null;
  chapterId?: string | null;
  startedAt: string;
  endedAt: string;
  eventCount: number;
  status: "completed" | "interrupted" | "error" | "active";
  sources: WorkflowEventSource[];
  nodes: string[];
  agents: string[];
}

interface ApiResponse {
  runs: WorkflowRunSummary[];
  selectedRun?: WorkflowRunSummary;
  events: WorkflowEventLogEntry[];
  error?: string;
}

interface GraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
  kind: "system" | "agent" | "process" | "terminal";
}

interface GraphEdge {
  from: string;
  to: string;
  label?: string;
}

const GRAPH_NODES: GraphNode[] = [
  { id: "START", label: "START", x: 6, y: 50, kind: "terminal" },
  { id: "initSession", label: "initSession", x: 18, y: 50, kind: "system" },
  { id: "chapterWorkflow", label: "chapterWorkflow", x: 34, y: 50, kind: "process" },
  { id: "loreAdvisor", label: "设定", x: 52, y: 18, kind: "agent" },
  { id: "plotAdvisor", label: "剧情", x: 52, y: 34, kind: "agent" },
  { id: "author", label: "写作", x: 52, y: 50, kind: "agent" },
  { id: "validator", label: "校验", x: 52, y: 66, kind: "agent" },
  { id: "editor", label: "编辑", x: 52, y: 82, kind: "agent" },
  { id: "statusReport", label: "statusReport", x: 38, y: 18, kind: "system" },
  { id: "processResult", label: "processResult", x: 73, y: 50, kind: "process" },
  { id: "END", label: "END", x: 91, y: 50, kind: "terminal" },
];

const GRAPH_EDGES: GraphEdge[] = [
  { from: "START", to: "initSession" },
  { from: "initSession", to: "chapterWorkflow" },
  { from: "initSession", to: "loreAdvisor" },
  { from: "initSession", to: "plotAdvisor" },
  { from: "initSession", to: "author" },
  { from: "initSession", to: "validator" },
  { from: "initSession", to: "editor" },
  { from: "initSession", to: "statusReport" },
  { from: "chapterWorkflow", to: "loreAdvisor" },
  { from: "chapterWorkflow", to: "plotAdvisor" },
  { from: "chapterWorkflow", to: "author" },
  { from: "chapterWorkflow", to: "validator" },
  { from: "chapterWorkflow", to: "editor" },
  { from: "chapterWorkflow", to: "END" },
  { from: "loreAdvisor", to: "processResult" },
  { from: "plotAdvisor", to: "processResult" },
  { from: "author", to: "processResult" },
  { from: "validator", to: "processResult" },
  { from: "editor", to: "processResult" },
  { from: "statusReport", to: "END" },
  { from: "processResult", to: "loreAdvisor" },
  { from: "processResult", to: "plotAdvisor" },
  { from: "processResult", to: "author" },
  { from: "processResult", to: "validator" },
  { from: "processResult", to: "editor" },
  { from: "processResult", to: "END" },
];

const NODE_IDS = new Set(GRAPH_NODES.map((node) => node.id));

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function shortId(value: string, size = 8): string {
  if (value.length <= size * 2 + 1) return value;
  return `${value.slice(0, size)}…${value.slice(-size)}`;
}

function getEntryNodes(entry: WorkflowEventLogEntry): string[] {
  const nodes = new Set<string>();
  if (entry.node && NODE_IDS.has(entry.node)) nodes.add(entry.node);
  if (
    entry.source === "langgraph" &&
    entry.eventType === "updates" &&
    entry.changedKeys &&
    !Array.isArray(entry.changedKeys)
  ) {
    for (const node of Object.keys(entry.changedKeys)) {
      if (NODE_IDS.has(node)) nodes.add(node);
    }
  }
  return Array.from(nodes);
}

function getChangedKeyText(entry: WorkflowEventLogEntry): string {
  if (!entry.changedKeys) return "";
  if (Array.isArray(entry.changedKeys)) return entry.changedKeys.join(", ");
  return Object.entries(entry.changedKeys)
    .map(([node, keys]) => `${node}: ${keys.join(", ")}`)
    .join(" | ");
}

function getPayloadText(entry: WorkflowEventLogEntry | null): string {
  if (!entry) return "";
  return JSON.stringify(
    {
      seq: entry.seq,
      timestamp: entry.timestamp,
      source: entry.source,
      eventType: entry.eventType,
      node: entry.node,
      agentId: entry.agentId,
      changedKeys: entry.changedKeys,
      payload: entry.payload,
    },
    null,
    2
  );
}

function buildVisitedNodes(events: WorkflowEventLogEntry[], status?: WorkflowRunSummary["status"]): string[] {
  const result: string[] = ["START"];
  for (const event of events) {
    for (const node of getEntryNodes(event)) {
      if (result[result.length - 1] !== node) result.push(node);
    }
  }
  if (status === "completed" && result[result.length - 1] !== "END") {
    result.push("END");
  }
  return result;
}

function buildActiveEdges(visitedNodes: string[]): Set<string> {
  const active = new Set<string>();
  const edgeKeys = new Set(GRAPH_EDGES.map((edge) => `${edge.from}->${edge.to}`));

  for (let i = 0; i < visitedNodes.length - 1; i++) {
    const directKey = `${visitedNodes[i]}->${visitedNodes[i + 1]}`;
    if (edgeKeys.has(directKey)) active.add(directKey);
  }

  return active;
}

function sourceLabel(source: WorkflowEventSource): string {
  const labels: Record<WorkflowEventSource, string> = {
    workflow: "流程",
    langgraph: "图事件",
    sse: "前端流",
    persistence: "持久化",
    error: "错误",
  };
  return labels[source];
}

function statusLabel(status: WorkflowRunSummary["status"]): string {
  const labels: Record<WorkflowRunSummary["status"], string> = {
    completed: "完成",
    interrupted: "中断",
    error: "错误",
    active: "活跃",
  };
  return labels[status];
}

export function WorkflowEventsInspector() {
  const [runs, setRuns] = useState<WorkflowRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<WorkflowRunSummary | null>(null);
  const [events, setEvents] = useState<WorkflowEventLogEntry[]>([]);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadRuns(nextRunId?: string | null) {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/debug/workflow-events", { cache: "no-store" });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok) throw new Error(data.error ?? "读取运行列表失败");
      setRuns(data.runs);
      const runId = nextRunId ?? selectedRunId ?? data.runs[0]?.runId ?? null;
      setSelectedRunId(runId);
      if (!runId) {
        setSelectedRun(null);
        setEvents([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取运行列表失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadRunDetail(runId: string) {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/debug/workflow-events?runId=${encodeURIComponent(runId)}`, {
        cache: "no-store",
      });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok) throw new Error(data.error ?? "读取运行详情失败");
      setRuns(data.runs);
      setSelectedRun(data.selectedRun ?? null);
      setEvents(data.events);
      setSelectedSeq(data.events[0]?.seq ?? null);
      setSelectedNode(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取运行详情失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedRunId) void loadRunDetail(selectedRunId);
  }, [selectedRunId]);

  const filteredRuns = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return runs;
    return runs.filter((run) =>
      [
        run.runId,
        run.taskId,
        run.novelId ?? "",
        run.chapterId ?? "",
        run.runKind,
        run.status,
        ...run.nodes,
        ...run.agents,
      ].some((value) => value.toLowerCase().includes(text))
    );
  }, [runs, query]);

  const selectedEvent = useMemo(() => {
    return events.find((event) => event.seq === selectedSeq) ?? events[0] ?? null;
  }, [events, selectedSeq]);

  const visitedNodes = useMemo(
    () => buildVisitedNodes(events, selectedRun?.status),
    [events, selectedRun?.status]
  );
  const activeNodeSet = useMemo(() => new Set(visitedNodes), [visitedNodes]);
  const activeEdges = useMemo(() => buildActiveEdges(visitedNodes), [visitedNodes]);
  const nodeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const event of events) {
      for (const node of getEntryNodes(event)) {
        counts.set(node, (counts.get(node) ?? 0) + 1);
      }
    }
    return counts;
  }, [events]);

  const visibleEvents = useMemo(() => {
    if (!selectedNode) return events;
    return events.filter((event) => getEntryNodes(event).includes(selectedNode));
  }, [events, selectedNode]);

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Workflow Inspector</h1>
          <p>按本地 JSONL 审计日志回放 LangGraph 节点、边、状态变更和业务数据流。</p>
        </div>
        <div className={styles.headerActions}>
          <button className="button secondary" type="button" onClick={() => void loadRuns(selectedRunId)}>
            刷新
          </button>
          <a className="button ghost" href="/">
            返回项目
          </a>
        </div>
      </header>

      {error && <div className="notice notice-danger">{error}</div>}

      <section className={styles.layout}>
        <aside className={styles.runsPane}>
          <div className={styles.paneHeader}>
            <div>
              <h2>运行记录</h2>
              <span>{loading ? "读取中" : `${filteredRuns.length} 条`}</span>
            </div>
          </div>
          <div className={styles.searchBox}>
            <input
              className="input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索 runId / taskId / 节点 / Agent"
            />
          </div>
          <div className={styles.runList}>
            {filteredRuns.map((run) => (
              <button
                key={run.runId}
                className={`${styles.runItem} ${run.runId === selectedRunId ? styles.activeRun : ""}`}
                type="button"
                onClick={() => setSelectedRunId(run.runId)}
              >
                <span className={`${styles.statusDot} ${styles[`status_${run.status}`]}`} />
                <span className={styles.runMain}>
                  <strong>{shortId(run.runId, 10)}</strong>
                  <small>{formatTime(run.startedAt)} · {run.eventCount} events</small>
                  <small>{shortId(run.taskId, 8)}</small>
                </span>
                <span className={styles.runStatus}>{statusLabel(run.status)}</span>
              </button>
            ))}
            {!loading && filteredRuns.length === 0 && (
              <div className="empty">还没有可读取的 workflow event 日志。</div>
            )}
          </div>
        </aside>

        <section className={styles.graphPane}>
          <div className={styles.graphToolbar}>
            <div>
              <h2>节点与边</h2>
              <span>
                {selectedRun ? `${shortId(selectedRun.runId, 12)} · ${statusLabel(selectedRun.status)}` : "未选择运行"}
              </span>
            </div>
            <button
              className="button ghost sm"
              type="button"
              onClick={() => setSelectedNode(null)}
              disabled={!selectedNode}
            >
              显示全部事件
            </button>
          </div>

          <div className={styles.graphCanvas}>
            <svg className={styles.edgeLayer} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <marker id="workflow-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                  <path d="M0,0 L6,3 L0,6 Z" fill="currentColor" />
                </marker>
              </defs>
              {GRAPH_EDGES.map((edge) => {
                const from = GRAPH_NODES.find((node) => node.id === edge.from);
                const to = GRAPH_NODES.find((node) => node.id === edge.to);
                if (!from || !to) return null;
                const key = `${edge.from}->${edge.to}`;
                const active = activeEdges.has(key);
                const midX = (from.x + to.x) / 2;
                const bend = from.y === to.y ? from.y : (from.y + to.y) / 2;
                const path = `M ${from.x} ${from.y} C ${midX} ${from.y}, ${midX} ${bend}, ${to.x} ${to.y}`;
                return (
                  <path
                    key={key}
                    className={`${styles.edge} ${active ? styles.activeEdge : ""}`}
                    d={path}
                    markerEnd="url(#workflow-arrow)"
                  />
                );
              })}
            </svg>

            {GRAPH_NODES.map((node) => {
              const active = activeNodeSet.has(node.id);
              const selected = selectedNode === node.id;
              const count = nodeCounts.get(node.id) ?? 0;
              return (
                <button
                  key={node.id}
                  className={[
                    styles.graphNode,
                    styles[`node_${node.kind}`],
                    active ? styles.activeNode : "",
                    selected ? styles.selectedNode : "",
                  ].join(" ")}
                  style={{ left: `${node.x}%`, top: `${node.y}%` }}
                  type="button"
                  title={`筛选 ${node.label} 节点事件`}
                  onClick={() => setSelectedNode(selected ? null : node.id)}
                >
                  <span>{node.label}</span>
                  {count > 0 && <em>{count}</em>}
                </button>
              );
            })}
          </div>

          <div className={styles.timeline}>
            <div className={styles.timelineHeader}>
              <h2>{selectedNode ? `${selectedNode} 事件` : "执行时间线"}</h2>
              <span>{visibleEvents.length} / {events.length}</span>
            </div>
            <div className={styles.eventList}>
              {visibleEvents.map((event) => {
                const isSelected = selectedEvent?.seq === event.seq;
                const nodes = getEntryNodes(event);
                return (
                  <button
                    key={`${event.runId}-${event.seq}`}
                    className={`${styles.eventItem} ${isSelected ? styles.activeEvent : ""}`}
                    type="button"
                    onClick={() => setSelectedSeq(event.seq)}
                  >
                    <span className={styles.seq}>#{event.seq}</span>
                    <span className={`${styles.source} ${styles[`source_${event.source}`]}`}>
                      {sourceLabel(event.source)}
                    </span>
                    <span className={styles.eventText}>
                      <strong>{event.eventType}</strong>
                      <small>
                        {nodes.join(", ") || event.agentId || event.langGraphEvent || "全局"} · {formatTime(event.timestamp)}
                      </small>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        <aside className={styles.detailPane}>
          <div className={styles.paneHeader}>
            <div>
              <h2>状态内容</h2>
              <span>{selectedEvent ? `#${selectedEvent.seq} ${selectedEvent.eventType}` : "未选择事件"}</span>
            </div>
          </div>

          {selectedRun && (
            <div className={styles.summaryBlock}>
              <dl>
                <div>
                  <dt>runId</dt>
                  <dd>{selectedRun.runId}</dd>
                </div>
                <div>
                  <dt>taskId</dt>
                  <dd>{selectedRun.taskId}</dd>
                </div>
                <div>
                  <dt>时间</dt>
                  <dd>{formatTime(selectedRun.startedAt)} → {formatTime(selectedRun.endedAt)}</dd>
                </div>
              </dl>
            </div>
          )}

          {selectedEvent ? (
            <>
              <div className={styles.metaGrid}>
                <div>
                  <span>来源</span>
                  <strong>{sourceLabel(selectedEvent.source)}</strong>
                </div>
                <div>
                  <span>节点</span>
                  <strong>{getEntryNodes(selectedEvent).join(", ") || selectedEvent.node || "-"}</strong>
                </div>
                <div>
                  <span>Agent</span>
                  <strong>{selectedEvent.agentId || "-"}</strong>
                </div>
                <div>
                  <span>变更字段</span>
                  <strong>{getChangedKeyText(selectedEvent) || "-"}</strong>
                </div>
              </div>

              <pre className={styles.payloadView}>{getPayloadText(selectedEvent)}</pre>
            </>
          ) : (
            <div className="empty">选择一个事件后查看状态 patch 和 payload 摘要。</div>
          )}
        </aside>
      </section>
    </main>
  );
}

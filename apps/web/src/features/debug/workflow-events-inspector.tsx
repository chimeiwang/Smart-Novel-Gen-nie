"use client";

import type { components } from "@inkforge/api-client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";

type WorkflowRunSummary = components["schemas"]["WorkflowRunSummary"];

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

export function WorkflowEventsInspector() {
  const [runs, setRuns] = useState<WorkflowRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = requireApiData(await browserApi.GET("/api/v1/debug/workflow-runs", {
        cache: "no-store",
      }));
      setRuns(data.runs);
      setSelectedRunId((current) => current ?? data.runs[0]?.runId ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取运行日志失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRun = useCallback(async (runId: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = requireApiData(await browserApi.GET(
        "/api/v1/debug/workflow-runs/{run_id}",
        { params: { path: { run_id: runId } }, cache: "no-store" },
      ));
      setContent(data.content);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "读取运行日志失败");
      setContent("");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadRuns(), 0);
    return () => window.clearTimeout(timer);
  }, [loadRuns]);

  useEffect(() => {
    if (!selectedRunId) return;
    const timer = window.setTimeout(() => void loadRun(selectedRunId), 0);
    return () => window.clearTimeout(timer);
  }, [loadRun, selectedRunId]);

  return (
    <main className="page stack">
      <div className="row row-between">
        <div>
          <h1 className="title-xl">智能体工作流日志</h1>
          <p className="muted">查看完整模型消息、响应正文和中文状态切换。</p>
        </div>
        <div className="row">
          <button className="button secondary" type="button" onClick={() => void loadRuns()}>
            刷新
          </button>
          <Link href="/dashboard" className="button ghost">返回工作台</Link>
        </div>
      </div>

      {error ? <div className="notice notice-danger">{error}</div> : null}
      <div className="grid-two">
        <section className="panel">
          <div className="panel-header"><h2 className="title-lg">运行记录</h2></div>
          <div className="panel-body list">
            {runs.map((run) => (
              <button
                key={run.runId}
                className={`list-item ${selectedRunId === run.runId ? "active" : ""}`}
                type="button"
                onClick={() => setSelectedRunId(run.runId)}
              >
                <strong>{run.runKind}</strong>
                <span className="muted small-text">{formatTime(run.startedAt)}</span>
                <span className="badge">{run.status}</span>
              </button>
            ))}
            {!loading && runs.length === 0 ? <div className="empty">暂无运行日志。</div> : null}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header"><h2 className="title-lg">完整日志</h2></div>
          <div className="panel-body">
            {loading && !content ? <div className="empty">正在读取...</div> : null}
            {content ? <pre className="workflow-human-log">{content}</pre> : null}
          </div>
        </section>
      </div>
    </main>
  );
}

"use client";

import type { components } from "@inkforge/api-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { filterNonEmptyWritingSessions } from "@/features/writing/session-presentation";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";

type Session = components["schemas"]["WritingSessionListItem"];
type SessionDetail = components["schemas"]["WritingSessionDetail"];
type VersionReference = components["schemas"]["ShortStoryVersionReference"];
export type ShortStoryVersionAttachment = {
  reference: VersionReference;
  label: string;
};
type Operation = "answer_question" | "develop_short_outline" | "write_short_story";

type ShortStoryChatPaneProps = {
  novelId: string;
  chapterId: string;
  targetWordCount: number | null;
  initialSessionId: string | null;
  references: ShortStoryVersionAttachment[];
  disabled: boolean;
  onRemoveReference: (reference: VersionReference) => void;
  onSubmitted: () => void;
};

const OPERATION_LABELS: Record<Operation, string> = {
  answer_question: "讨论",
  develop_short_outline: "修改大纲",
  write_short_story: "修改正文",
};

function formatSessionTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ShortStoryChatPane({
  novelId,
  chapterId,
  targetWordCount,
  initialSessionId,
  references,
  disabled,
  onRemoveReference,
  onSubmitted,
}: ShortStoryChatPaneProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [message, setMessage] = useState("");
  const [operation, setOperation] = useState<Operation>("answer_question");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => () => { mountedRef.current = false; }, []);

  const loadSession = useCallback(async (sessionId: string) => {
    const detail = requireApiData(await browserApi.GET(
      "/api/v1/writing/sessions/{session_id}",
      { params: { path: { session_id: sessionId } }, cache: "no-store" },
    ));
    if (sessionIdRef.current === sessionId) setSession(detail);
    return detail;
  }, []);

  const loadSessions = useCallback(async () => {
    const values = requireApiData(await browserApi.GET("/api/v1/writing/sessions", {
      params: { query: { novelId, chapterId } },
      cache: "no-store",
    }));
    const visibleSessions = filterNonEmptyWritingSessions(values);
    setSessions(visibleSessions);
    return visibleSessions;
  }, [chapterId, novelId]);

  const selectSession = useCallback(async (sessionId: string) => {
    sessionIdRef.current = sessionId;
    setSession(null);
    setShowHistory(false);
    setLoading(true);
    setError(null);
    try {
      await loadSession(sessionId);
    } catch (cause) {
      if (sessionIdRef.current === sessionId) {
        setError(cause instanceof Error ? cause.message : "读取对话失败");
      }
    } finally {
      if (sessionIdRef.current === sessionId) setLoading(false);
    }
  }, [loadSession]);

  const startNewConversation = useCallback(() => {
    sessionIdRef.current = null;
    setSession(null);
    setShowHistory(false);
    setLoading(false);
    setMessage("");
    setOperation("answer_question");
    setError(null);
  }, []);

  const createSession = useCallback(async () => {
    setError(null);
    try {
      const created = requireApiData(await browserApi.POST("/api/v1/writing/sessions", {
        body: {
          novelId,
          chapterId,
          title: `中短篇讨论 ${new Intl.DateTimeFormat("zh-CN", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          }).format(new Date())}`,
        },
      }));
      await loadSessions();
      await selectSession(created.id);
      return created.id;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建对话失败");
      return null;
    }
  }, [chapterId, loadSessions, novelId, selectSession]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setLoading(true);
      try {
        const values = await loadSessions();
        if (cancelled) return;
        const selected = initialSessionId && values.some((item) => item.id === initialSessionId)
          ? initialSessionId
          : values[0]?.id ?? null;
        if (selected) await selectSession(selected);
        else setLoading(false);
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "读取对话失败");
          setLoading(false);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [initialSessionId, loadSessions, selectSession]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [session?.messages.length]);

  const waitForTask = useCallback(async (sessionId: string, taskId: string) => {
    setProcessing(true);
    try {
      for (let attempt = 0; attempt < 400 && mountedRef.current; attempt += 1) {
        const detail = await loadSession(sessionId);
        await loadSessions();
        const current = detail.currentTask;
        const last = detail.lastTask;
        const finished = last?.id === taskId || (
          current?.id === taskId
          && ["completed", "error", "waiting_user", "awaiting_user_review"].includes(current.phase)
        );
        if (finished) return;
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
      }
    } finally {
      if (mountedRef.current) setProcessing(false);
    }
  }, [loadSession, loadSessions]);

  const send = useCallback(async () => {
    const content = message.trim();
    if (!content || sending || processing || disabled) return;
    setSending(true);
    setError(null);
    try {
      const sessionId = sessionIdRef.current ?? await createSession();
      if (!sessionId) return;
      const run = requireApiData(await browserApi.POST("/api/v1/writing/runs", {
        body: {
          clientRequestId: `short-chat-${crypto.randomUUID()}`,
          novelId,
          chapterId,
          writingSessionId: sessionId,
          workflowKind: "short_medium",
          operation,
          targetWordCount,
          selectedAgents: ["剧情", "写作", "编辑", "校验"],
          userMessage: content,
          versionReferences: references.map((item) => item.reference),
        },
      }));
      setMessage("");
      references.forEach((item) => onRemoveReference(item.reference));
      await loadSession(sessionId);
      await loadSessions();
      onSubmitted();
      setSending(false);
      await waitForTask(sessionId, run.id);
      onSubmitted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "发送失败");
    } finally {
      setSending(false);
    }
  }, [
    chapterId,
    createSession,
    disabled,
    loadSession,
    loadSessions,
    message,
    novelId,
    onSubmitted,
    onRemoveReference,
    operation,
    processing,
    references,
    sending,
    targetWordCount,
    waitForTask,
  ]);

  return (
    <aside className="panel short-story-chat-pane" aria-label="中短篇写作对话">
      <header className="short-story-chat-header">
        <div>
          <strong>{session?.title || "写作对话"}</strong>
          <small>{session ? formatSessionTime(session.updatedAt) : "选择或新建一段对话"}</small>
        </div>
        <div className="meta">
          <button className="button ghost compact" type="button" onClick={() => setShowHistory((value) => !value)}>
            历史对话
          </button>
          <button className="button secondary compact" type="button" disabled={sending} onClick={startNewConversation}>
            开始新对话
          </button>
        </div>
      </header>

      {showHistory ? (
        <div className="short-story-session-list">
          {sessions.length === 0 ? <p className="muted">还没有历史对话。</p> : null}
          {sessions.map((item) => (
            <button
              className={item.id === session?.id ? "active" : ""}
              type="button"
              key={item.id}
              onClick={() => void selectSession(item.id)}
            >
              <strong>{item.title || "未命名对话"}</strong>
              <span>{item.lastMessage?.content || "尚无消息"}</span>
              <small>{formatSessionTime(item.updatedAt)}</small>
            </button>
          ))}
        </div>
      ) : null}

      <div className="short-story-chat-messages" aria-live="polite">
        {loading ? <p className="muted">正在读取对话…</p> : null}
        {!loading && !session?.messages.length ? (
          <p className="muted">可以讨论作品，也可以选择“修改大纲”或“修改正文”后提出具体要求。</p>
        ) : null}
        {session?.messages.filter((item) => item.role !== "system").map((item) => (
          <article className={`short-story-chat-message ${item.role === "user" ? "user" : "agent"}`} key={item.id}>
            <strong>{item.role === "user" ? "你" : item.agentId || "创作助手"}</strong>
            <p>{item.content}</p>
          </article>
        ))}
        {processing ? <p className="muted">创作助手正在处理本轮请求…</p> : null}
        <div ref={endRef} />
      </div>

      <div className="short-story-chat-composer">
        {references.length ? (
          <div className="short-story-chat-references" aria-label="本轮引用版本">
            {references.map((attachment) => (
              <button
                type="button"
                key={`${attachment.reference.kind}:${attachment.reference.artifactId}:${attachment.reference.revision}`}
                onClick={() => onRemoveReference(attachment.reference)}
              >
                引用：{attachment.label} ×
              </button>
            ))}
          </div>
        ) : null}
        <div className="short-story-chat-modes" aria-label="本轮对话方式">
          {(Object.keys(OPERATION_LABELS) as Operation[]).map((value) => (
            <button
              className={operation === value ? "active" : ""}
              type="button"
              key={value}
              onClick={() => setOperation(value)}
            >{OPERATION_LABELS[value]}</button>
          ))}
        </div>
        <textarea
          className="textarea"
          rows={5}
          value={message}
          placeholder="说说你的想法；如需精确比较或微调，可先从左侧引用某个版本。"
          disabled={sending || processing || disabled}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        {error ? <p className="short-story-error" role="alert">{error}</p> : null}
        <div className="short-story-chat-actions">
          <button className="button primary" type="button" disabled={!message.trim() || sending || processing || disabled} onClick={() => void send()}>
            {sending ? "正在发送…" : processing ? "正在处理…" : "发送"}
          </button>
        </div>
      </div>
    </aside>
  );
}

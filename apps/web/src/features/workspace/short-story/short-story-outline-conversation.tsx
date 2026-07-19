"use client";

import { useEffect, useRef } from "react";

import { formatShortStoryVersion } from "./short-story-display-labels";
import type { ShortStoryOutlineConversationEntry } from "./short-story-outline-conversation-model";

type ShortStoryOutlineConversationProps = {
  entries: ShortStoryOutlineConversationEntry[];
  currentRevision: number;
  loading: boolean;
  error: string | null;
  value: string;
  canSubmit: boolean;
  submitting: boolean;
  readOnlyReason: string | null;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onSelectRevision: (revision: number) => void;
};

function formatEntryTime(value: string | null): string | null {
  if (!value) return null;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ShortStoryOutlineConversation({
  entries,
  currentRevision,
  loading,
  error,
  value,
  canSubmit,
  submitting,
  readOnlyReason,
  onChange,
  onSubmit,
  onSelectRevision,
}: ShortStoryOutlineConversationProps) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest" });
  }, [entries.length]);

  return (
    <section className="stack short-story-outline-conversation">
      <div className="short-story-section-toolbar">
        <h2 className="title-sm">改纲对话</h2>
        <span className="badge">当前{formatShortStoryVersion(currentRevision)}</span>
      </div>

      <div className="short-story-conversation-log" aria-live="polite">
        {loading ? <p className="muted">正在读取改纲对话…</p> : null}
        {!loading && entries.length === 0 ? (
          <p className="muted">尚未提出修改要求。初始大纲生成后，你可以在这里连续讨论和修改。</p>
        ) : null}
        {entries.map((entry) => {
          const time = formatEntryTime(entry.createdAt);
          const isUser = entry.kind === "user_request";
          return (
            <article
              className={`short-story-conversation-entry ${isUser ? "user" : "agent"} ${entry.state}`}
              key={entry.key}
            >
              <div className="short-story-conversation-entry-head">
                <strong>{isUser ? "你的修改要求" : "完整大纲结果"}</strong>
                {time ? <time dateTime={entry.createdAt ?? undefined}>{time}</time> : null}
              </div>
              <p>{entry.content}</p>
              {entry.revision !== null ? (
                <button
                  className="short-story-conversation-version"
                  type="button"
                  onClick={() => onSelectRevision(entry.revision as number)}
                >
                  {isUser ? `基于${formatShortStoryVersion(entry.revision)}` : `查看${formatShortStoryVersion(entry.revision)}`}
                </button>
              ) : null}
            </article>
          );
        })}
        <div ref={endRef} />
      </div>

      {error ? <p className="short-story-error" role="alert">{error}</p> : null}

      {readOnlyReason ? (
        <p className="muted short-story-conversation-readonly">{readOnlyReason}</p>
      ) : (
        <div className="stack short-story-conversation-composer">
          <label className="label" htmlFor="short-story-outline-revision-request">
            继续修改当前完整大纲
          </label>
          <textarea
            className="textarea"
            id="short-story-outline-revision-request"
            rows={4}
            value={value}
            placeholder="例如：只修改第 3 节，让冲突更早爆发；其他分节和结局保持不变。"
            disabled={submitting}
            onChange={(event) => onChange(event.target.value)}
          />
          <button
            className="button secondary"
            type="button"
            disabled={!canSubmit || submitting || !value.trim()}
            onClick={onSubmit}
          >
            {submitting ? "正在修改完整大纲…" : "发送修改要求"}
          </button>
        </div>
      )}
    </section>
  );
}

"use client";

import { useState } from "react";
import type { Episode, EpisodeListResponse } from "./types";

export function EpisodeList({ data, currentId, busy, enabled, onSelect, onCreate, onMove }: {
  data: EpisodeListResponse | null;
  currentId: string | null;
  busy: boolean;
  enabled: boolean;
  onSelect: (episode: Episode) => void;
  onCreate: (title: string) => Promise<void>;
  onMove: (episodeId: string, offset: -1 | 1) => void;
}) {
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  return <aside className="episode-list" aria-label="分集列表">
    <header><h2>剧集</h2><span className="muted">{data?.episodes.length ?? 0} 集</span></header>
    <ol>{(data?.episodes ?? []).map((episode, index) => <li key={episode.id} className={episode.id === currentId ? "active" : ""}>
      <button type="button" className="episode-list-item" disabled={busy} aria-current={episode.id === currentId ? "page" : undefined} onClick={() => onSelect(episode)}><span className="muted">第 {index + 1} 集</span><strong>{episode.title}</strong><small>{episode.currentScriptVersionId ? "已有正式剧本" : "剧本工作稿"}{episode.currentProductionBaselineId ? " · 已有制作" : ""}</small></button>
      <div className="episode-order-actions"><button type="button" className="button ghost sm" disabled={!enabled || busy || index === 0} aria-label={`上移${episode.title}`} onClick={() => onMove(episode.id, -1)}>↑</button><button type="button" className="button ghost sm" disabled={!enabled || busy || index === (data?.episodes.length ?? 0) - 1} aria-label={`下移${episode.title}`} onClick={() => onMove(episode.id, 1)}>↓</button></div>
    </li>)}</ol>
    <form onSubmit={(event) => { event.preventDefault(); if (!title.trim() || busy) return; setError(null); void onCreate(title.trim()).then(() => setTitle("")).catch((failure) => setError(failure instanceof Error ? failure.message : "创建分集失败")); }}>
      <label>新的一集<input className="input" value={title} maxLength={240} placeholder="例如：雨夜送信" disabled={!enabled || busy} onChange={(event) => setTitle(event.target.value)} /></label>
      <button type="submit" className="button primary" disabled={!enabled || busy || !title.trim()}>创建一集</button>
      {error ? <p role="alert" className="notice notice-danger">{error}</p> : null}
    </form>
    <p className="muted">集号只表示排列顺序。改名、调序不会改变本集的来源和版本。</p>
  </aside>;
}

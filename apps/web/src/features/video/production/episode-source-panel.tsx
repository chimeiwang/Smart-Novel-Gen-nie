"use client";

import type { components } from "@inkforge/api-client";
import { useEffect, useState } from "react";
import { countTextLength } from "@/shared/lib/word-count";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import { sha256Text } from "@/features/short-medium/selection-range";
import { registerEpisodeSave } from "./episode-save-navigation";
import type { SourceSelection, SourceSet } from "./types";

type SelectedSource = { request: SourceSelection; title: string; content: string };

export function unicodeSelectionRange(content: string, start: number, end: number) {
  return { start: Array.from(content.slice(0, start)).length, end: Array.from(content.slice(0, end)).length };
}

export function EpisodeSourcePanel({ novelId, episodeId, sourceSet, disabled, onSave }: { novelId: string; episodeId: string; sourceSet: SourceSet | null; disabled: boolean; onSave: (sources: SourceSelection[]) => Promise<void> }) {
  const [chapters, setChapters] = useState<components["schemas"]["WorkspaceChapter"][]>([]);
  const [chapter, setChapter] = useState<components["schemas"]["WorkspaceChapter"] | null>(null);
  const [selected, setSelected] = useState<SelectedSource[]>(() => (sourceSet?.sources ?? []).flatMap((source) => source.chapterId ? [{ title: source.chapterTitle, content: source.sourceText, request: { chapterId: source.chapterId, expectedUpdatedAt: source.chapterUpdatedAt, sourceHash: source.sourceHash, ranges: source.ranges } }] : []));
  const [range, setRange] = useState<{ start: number; end: number } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void browserApi.GET("/api/v1/novels/{novel_id}/chapters", { params: { path: { novel_id: novelId } }, signal: controller.signal }).then(requireApiData).then((result) => { if (!controller.signal.aborted) setChapters(result.chapters); }).catch((failure) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "读取取材章节失败"); });
    return () => controller.abort();
  }, [novelId]);
  useEffect(() => registerEpisodeSave({ novelId, episodeId, pending: () => dirty || busy, flush: async () => { if (busy) throw new Error("正在保存本集取材，请稍候"); if (dirty) throw new Error("本集取材尚未确认，请先保存取材或撤销选择"); } }), [novelId, episodeId, dirty, busy]);

  const readChapter = async (chapterId: string) => {
    setRange(null);
    if (!chapterId) { setChapter(null); return; }
    setBusy(true);
    setError(null);
    try { setChapter(requireApiData(await browserApi.GET("/api/v1/chapters/{chapter_id}", { params: { path: { chapter_id: chapterId } } }))); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "读取章节最新原文失败"); }
    finally { setBusy(false); }
  };

  const addSource = async (selectedRange: { start: number; end: number } | null) => {
    if (!chapter || !chapter.content || busy) return;
    setBusy(true);
    setError(null);
    try {
      const sourceHash = await sha256Text(chapter.content);
      const nextRange = selectedRange ?? { start: 0, end: Array.from(chapter.content).length };
      setSelected((current) => {
        const existing = current.find((source) => source.request.chapterId === chapter.id);
        const ranges = existing?.request.sourceHash === sourceHash && selectedRange ? [...existing.request.ranges, nextRange].filter((item, index, items) => items.findIndex((candidate) => candidate.start === item.start && candidate.end === item.end) === index) : [nextRange];
        const next = { title: chapter.title, content: chapter.content, request: { chapterId: chapter.id, expectedUpdatedAt: chapter.updatedAt, sourceHash, ranges } };
        return existing ? current.map((source) => source.request.chapterId === chapter.id ? next : source) : [...current, next];
      });
      setDirty(true);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "读取取材内容失败"); }
    finally { setBusy(false); }
  };

  return <section className="episode-source-panel"><header className="episode-toolbar"><h3>小说取材</h3><span className="muted">{sourceSet ? `已冻结来源 v${sourceSet.versionNo}` : "尚未确认来源"}</span></header><p className="muted">可从多章取材，同一章也可用于不同集。这里读取原文，不修改小说。</p>
    {error ? <p role="alert" className="notice notice-danger">{error}</p> : null}
    {(sourceSet?.sources ?? []).filter((source) => !source.chapterId).map((source) => <article key={source.id}><strong>{source.chapterTitle}</strong><p className="notice">原章节已不可用，冻结的取材仍可阅读。新一版取材需要重新选择来源。</p><details><summary>查看历史原文</summary>{source.ranges.map((item, index) => <p className="episode-source-text" key={index}>{Array.from(source.sourceText).slice(item.start, item.end).join("")}</p>)}</details></article>)}
    <div className="episode-selected-sources">{selected.map((source, index) => <article key={source.request.chapterId}><strong>{index + 1}. {source.title}</strong><span className="muted">{source.request.ranges.length} 段 · {source.request.ranges.reduce((sum, item) => sum + countTextLength(Array.from(source.content).slice(item.start, item.end).join("")), 0)} 字</span>{sourceSet?.sources.find((saved) => saved.chapterId === source.request.chapterId)?.sourceStatus === "updated" ? <p className="notice">小说来源有新版。当前剧本仍依据旧快照；在下方打开原章后重新取材才会同步。</p> : null}<details><summary>查看已选原文</summary>{source.request.ranges.map((item, rangeIndex) => <p className="episode-source-text" key={rangeIndex}>{Array.from(source.content).slice(item.start, item.end).join("")}</p>)}</details><div className="episode-inline-actions"><button className="button ghost sm" type="button" disabled={disabled || busy || index === 0} onClick={() => { setSelected((current) => { const next = [...current]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; return next; }); setDirty(true); }}>上移</button><button className="button ghost sm" type="button" disabled={disabled || busy} onClick={() => { setSelected((current) => current.filter((item) => item.request.chapterId !== source.request.chapterId)); setDirty(true); }}>移除</button></div></article>)}</div>
    <details open={!sourceSet}><summary>选择章节与原文范围</summary><label>章节<select className="select" disabled={disabled || busy} value={chapter?.id ?? ""} onChange={(event) => void readChapter(event.target.value)}><option value="">选择取材章节</option>{chapters.map((item) => <option key={item.id} value={item.id}>{item.order}. {item.title}</option>)}</select></label>{chapter ? <><textarea className="textarea episode-source-text" aria-label="小说原文（只读）" readOnly value={chapter.content} rows={12} onSelect={(event) => { const element = event.currentTarget; setRange(element.selectionEnd > element.selectionStart ? unicodeSelectionRange(chapter.content, element.selectionStart, element.selectionEnd) : null); }} /><div className="episode-inline-actions"><button className="button" type="button" disabled={disabled || busy || !chapter.content} onClick={() => void addSource(null)}>整章取材</button><button className="button ghost" type="button" disabled={disabled || busy} onClick={() => void readChapter(chapter.id)}>刷新原文</button><button className="button" type="button" disabled={disabled || busy || !range} onClick={() => void addSource(range)}>加入选中段落{range ? `（${countTextLength(Array.from(chapter.content).slice(range.start, range.end).join(""))} 字）` : ""}</button></div></> : null}</details>
    <div className="episode-toolbar"><button className="button primary" type="button" disabled={disabled || busy || !dirty || !selected.length} onClick={() => { setBusy(true); setError(null); void onSave(selected.map((source) => source.request)).then(() => setDirty(false)).catch((failure) => setError(failure instanceof Error ? failure.message : "保存取材失败，选择已保留")).finally(() => setBusy(false)); }}>{busy ? "正在处理…" : "确认本集取材"}</button>{dirty ? <button className="button ghost" type="button" disabled={busy} onClick={() => { setSelected((sourceSet?.sources ?? []).flatMap((source) => source.chapterId ? [{ title: source.chapterTitle, content: source.sourceText, request: { chapterId: source.chapterId, expectedUpdatedAt: source.chapterUpdatedAt, sourceHash: source.sourceHash, ranges: source.ranges } }] : [])); setDirty(false); }}>撤销未保存选择</button> : null}</div>
  </section>;
}

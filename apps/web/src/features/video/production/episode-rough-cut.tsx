"use client";

import { useEffect, useMemo, useState } from "react";

import { loadLocalDraft, saveLocalDraft } from "./episode-api";
import { registerEpisodeSave } from "./episode-save-navigation";
import { getTakeAdoption, listTakeCandidates } from "./production-api";
import { editDraftFromVersion, editDraftProblems, type EpisodeEditDraft } from "./post-production-state";
import type {
  EpisodeEditClipInput,
  EpisodeEditVersion,
  EpisodeEditVersionList,
  ProductionBaseline,
  TakeCandidate,
  TakeCandidateList,
} from "./types";
import { episodeTakeContentUrl } from "./production-api";

type Props = {
  novelId: string;
  episodeId: string;
  baseline: ProductionBaseline;
  page: EpisodeEditVersionList;
  current: EpisodeEditVersion | null;
  busy: boolean;
  enabled: boolean;
  onSave: (draft: EpisodeEditDraft) => Promise<void>;
  onLoadVersion: (versionId: string) => Promise<EpisodeEditVersion>;
  onLoadMore: () => void;
};

const createKey = () => crypto.randomUUID();

function initialDraft(baselineId: string, page: EpisodeEditVersionList, current: EpisodeEditVersion | null): EpisodeEditDraft {
  const stored = loadLocalDraft<{ baselineId: string; draft: EpisodeEditDraft }>(`inkforge:episode-edit-draft:${page.episodeId}:${baselineId}`);
  if (stored?.baselineId === baselineId && Array.isArray(stored.draft?.clips) && Array.isArray(stored.draft?.omissions)) return stored.draft;
  return current ? editDraftFromVersion(current, createKey) : { basedOnVersionId: null, expectedHeadRevision: page.headRevision, clips: [], omissions: [] };
}

export function EpisodeRoughCut({ novelId, episodeId, baseline, page, current, busy, enabled, onSave, onLoadVersion, onLoadMore }: Props) {
  const storageKey = `inkforge:episode-edit-draft:${episodeId}:${baseline.id}`;
  const [draft, setDraft] = useState(() => initialDraft(baseline.id, page, current));
  const [initialFingerprint, setInitialFingerprint] = useState(() => JSON.stringify(draft));
  const [activeIndex, setActiveIndex] = useState(0);
  const [takePages, setTakePages] = useState<Record<string, TakeCandidateList>>({});
  const [versionMedia, setVersionMedia] = useState<Record<string, { id: string; durationMs: number; takeNo: number | null }>>(() => Object.fromEntries((current?.clips ?? []).map((clip) => [clip.takeId, { id: clip.takeId, durationMs: clip.asset.durationMs, takeNo: null }])));
  const [adoptionTakeIds, setAdoptionTakeIds] = useState<Record<string, string>>({});
  const [loadingTakes, setLoadingTakes] = useState(() => baseline.shots.some((shot) => shot.adoptionId));
  const [historyLoading, setHistoryLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dirty = JSON.stringify(draft) !== initialFingerprint;
  const takeById = useMemo(() => ({ ...versionMedia, ...Object.fromEntries(Object.values(takePages).flatMap((value) => value.takes).map((take) => [take.id, { id: take.id, durationMs: take.durationMs, takeNo: take.takeNo }])) }), [takePages, versionMedia]);
  const problems = editDraftProblems(baseline, draft, takeById, adoptionTakeIds);
  const activeClip = draft.clips[activeIndex] ?? null;
  const activeTake = activeClip ? takeById[activeClip.takeId] ?? null : null;
  const totalDurationMs = draft.clips.reduce((sum, clip) => sum + clip.sourceOutMs - clip.sourceInMs, 0);

  useEffect(() => {
    let alive = true;
    const shots = baseline.shots.filter((shot) => shot.adoptionId);
    if (!shots.length) return () => { alive = false; };
    const workers = Array.from({ length: Math.min(4, shots.length) }, async (_, worker) => {
      const collected: Array<{ shotVersionId: string; page: TakeCandidateList; adoptionId: string; takeId: string }> = [];
      for (let index = worker; index < shots.length; index += 4) {
        const shot = shots[index]!;
        const [page, adoption] = await Promise.all([listTakeCandidates(episodeId, shot.shotVersionId, undefined, 100), getTakeAdoption(episodeId, shot.adoptionId!)]);
        collected.push({ shotVersionId: shot.shotVersionId, page, adoptionId: adoption.id, takeId: adoption.sourceTakeId });
      }
      return collected;
    });
    void Promise.all(workers).then((groups) => {
      if (!alive) return;
      const values = groups.flat();
      setTakePages(Object.fromEntries(values.map((value) => [value.shotVersionId, value.page])));
      setAdoptionTakeIds(Object.fromEntries(values.map((value) => [value.adoptionId, value.takeId])));
    }).catch((failure) => { if (alive) setError(failure instanceof Error ? failure.message : "读取基线 Take 失败"); }).finally(() => { if (alive) setLoadingTakes(false); });
    return () => { alive = false; };
  }, [baseline.id, baseline.shots, episodeId]);

  useEffect(() => {
    saveLocalDraft(storageKey, dirty ? { baselineId: baseline.id, draft } : null);
  }, [baseline.id, dirty, draft, storageKey]);

  useEffect(() => registerEpisodeSave({
    novelId,
    episodeId: `${episodeId}:edit:${baseline.id}`,
    pending: () => dirty || busy,
    flush: async () => { if (dirty || busy) throw new Error("粗剪工作区有尚未保存或尚未核对的内容"); },
  }), [baseline.id, busy, dirty, episodeId, novelId]);

  const change = (next: EpisodeEditDraft) => { setDraft(next); setError(null); };
  const updateClip = (index: number, patch: Partial<EpisodeEditClipInput>) => change({ ...draft, clips: draft.clips.map((clip, position) => position === index ? { ...clip, ...patch } : clip) });
  const moveClip = (index: number, offset: -1 | 1) => {
    const target = index + offset;
    if (target < 0 || target >= draft.clips.length) return;
    const clips = [...draft.clips];
    [clips[index], clips[target]] = [clips[target]!, clips[index]!];
    change({ ...draft, clips });
    setActiveIndex(target);
  };
  const addClip = (shot: ProductionBaseline["shots"][number], take: TakeCandidate) => {
    if (!shot.adoptionId || adoptionTakeIds[shot.adoptionId] !== take.id) return;
    change({
      ...draft,
      clips: [...draft.clips, { tempKey: createKey(), adoptionId: shot.adoptionId, takeId: take.id, sourceInMs: 0, sourceOutMs: take.durationMs, sourceAudioMode: "keep", transitionAfter: "cut", transitionDurationMs: 0 }],
      omissions: draft.omissions.filter((item) => item.shotVersionId !== shot.shotVersionId),
    });
    setActiveIndex(draft.clips.length);
  };
  const setOmission = (shotVersionId: string, reason: string) => change({
    ...draft,
    omissions: reason ? [...draft.omissions.filter((item) => item.shotVersionId !== shotVersionId), { shotVersionId, reason }] : draft.omissions.filter((item) => item.shotVersionId !== shotVersionId),
  });
  const loadEarlierTake = (shotVersionId: string) => {
    const existing = takePages[shotVersionId];
    if (!existing?.nextBeforeTakeId) return;
    setLoadingTakes(true);
    void listTakeCandidates(episodeId, shotVersionId, existing.nextBeforeTakeId, 100).then((next) => setTakePages((pages) => ({ ...pages, [shotVersionId]: { ...next, takes: [...existing.takes, ...next.takes.filter((take) => !existing.takes.some((old) => old.id === take.id))] } }))).catch((failure) => setError(failure instanceof Error ? failure.message : "读取更早 Take 失败")).finally(() => setLoadingTakes(false));
  };
  const loadHistorical = async (versionId: string) => {
    setHistoryLoading(versionId);
    setError(null);
    try {
      const version = await onLoadVersion(versionId);
      setDraft(editDraftFromVersion(version, createKey));
      setVersionMedia(Object.fromEntries(version.clips.map((clip) => [clip.takeId, { id: clip.takeId, durationMs: clip.asset.durationMs, takeNo: null }])));
      setActiveIndex(0);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "读取粗剪版本失败");
    } finally {
      setHistoryLoading(null);
    }
  };
  const save = async () => {
    setError(null);
    try {
      await onSave(draft);
      saveLocalDraft(storageKey, null);
      setInitialFingerprint(JSON.stringify(draft));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "保存粗剪版本失败");
    }
  };

  return <section className="episode-post-section episode-rough-cut">
    <header><div><span>制作 v{baseline.versionNo}</span><h3>基础粗剪</h3><p>片段使用独立临时身份；同一素材可以重复、裁切或调序。每个基线镜头必须进入时间线或写明省略原因。</p></div><div><strong>{draft.clips.length} 段 · {(totalDurationMs / 1000).toFixed(1)} 秒</strong><small>head revision {page.headRevision}</small></div></header>
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}
    {draft.expectedHeadRevision !== page.headRevision ? <section className="notice notice-warning"><strong>粗剪 head 已变化，本地输入仍保留</strong><p>先核对最新版本，再明确把本稿的 CAS 依据更新到 revision {page.headRevision}。</p><button className="button ghost sm" type="button" onClick={() => change({ ...draft, expectedHeadRevision: page.headRevision })}>保留本稿并使用最新 revision</button></section> : null}
    <div className="episode-edit-layout"><aside className="episode-edit-shot-checklist">{baseline.shots.map((shot) => {
      const pageForShot = takePages[shot.shotVersionId];
      const take = pageForShot?.takes.find((item) => item.id === (shot.adoptionId ? adoptionTakeIds[shot.adoptionId] : undefined)) ?? null;
      const clipCount = draft.clips.filter((clip) => clip.adoptionId === shot.adoptionId && Boolean(shot.adoptionId)).length;
      const omission = draft.omissions.find((item) => item.shotVersionId === shot.shotVersionId)?.reason ?? "";
      return <article key={shot.shotVersionId}><header><div><span>镜头 {shot.ordinal}</span><strong>{shot.inputSnapshot.prompt}</strong></div><em>{clipCount ? `${clipCount} 段` : omission.trim() ? "已说明省略" : "待处理"}</em></header>{shot.adoptionId ? take ? <button className="button ghost sm" type="button" disabled={busy} onClick={() => addClip(shot, take)}>添加整段 Take {take.takeNo}</button> : <p className="muted">{loadingTakes ? "正在查找本基线采用的 Take…" : "首批候选中未找到采用素材。"}</p> : <p className="muted">本镜在制作基线中尚无 Adoption，只能先说明省略或返回生产。</p>}{!take && pageForShot?.nextBeforeTakeId ? <button className="button ghost sm" type="button" disabled={loadingTakes} onClick={() => loadEarlierTake(shot.shotVersionId)}>继续查找更早 Take</button> : null}<label>省略原因<textarea className="textarea" rows={2} maxLength={1000} disabled={busy || clipCount > 0} value={omission} onChange={(event) => setOmission(shot.shotVersionId, event.target.value)} /></label></article>;
    })}</aside><main className="episode-edit-main">
      <div className="episode-edit-player">{activeClip ? <video key={activeClip.tempKey} controls preload="metadata" src={episodeTakeContentUrl(episodeId, activeClip.takeId)} onLoadedMetadata={(event) => { event.currentTarget.currentTime = activeClip.sourceInMs / 1000; }} /> : <div className="episode-empty compact"><h4>时间线尚无片段</h4><p>从左侧已采用镜头添加真实 Take，或逐镜填写省略原因。</p></div>}</div>
      {activeClip ? <section className="episode-edit-inspector"><header><strong>片段 {activeIndex + 1}</strong><span>{activeClip.tempKey}</span></header><div className="grid-two"><label>入点（秒）<input className="input" type="number" min={0} step={0.1} value={activeClip.sourceInMs / 1000} onChange={(event) => updateClip(activeIndex, { sourceInMs: Math.max(0, Math.round(Number(event.target.value) * 1000)) })} /></label><label>出点（秒）<input className="input" type="number" min={0.5} max={activeTake ? activeTake.durationMs / 1000 : undefined} step={0.1} value={activeClip.sourceOutMs / 1000} onChange={(event) => updateClip(activeIndex, { sourceOutMs: Math.round(Number(event.target.value) * 1000) })} /></label></div><label>片段原声<select className="select" value={activeClip.sourceAudioMode} onChange={(event) => updateClip(activeIndex, { sourceAudioMode: event.target.value as EpisodeEditClipInput["sourceAudioMode"] })}><option value="keep">保留原声</option><option value="mute">静音</option></select></label><div className="grid-two"><label>镜后转场<select className="select" value={activeClip.transitionAfter} onChange={(event) => updateClip(activeIndex, event.target.value === "fade_black" ? { transitionAfter: "fade_black", transitionDurationMs: 300 } : { transitionAfter: "cut", transitionDurationMs: 0 })}><option value="cut">硬切</option><option value="fade_black">淡黑</option></select></label>{activeClip.transitionAfter === "fade_black" ? <label>淡黑（秒）<input className="input" type="number" min={0.1} max={2} step={0.1} value={activeClip.transitionDurationMs / 1000} onChange={(event) => updateClip(activeIndex, { transitionDurationMs: Math.round(Number(event.target.value) * 1000) })} /></label> : null}</div><div className="episode-inline-actions"><button className="button ghost sm" type="button" disabled={activeIndex === 0} onClick={() => moveClip(activeIndex, -1)}>前移</button><button className="button ghost sm" type="button" disabled={activeIndex === draft.clips.length - 1} onClick={() => moveClip(activeIndex, 1)}>后移</button><button className="button ghost sm" type="button" onClick={() => { const copy = { ...activeClip, tempKey: createKey() }; change({ ...draft, clips: [...draft.clips.slice(0, activeIndex + 1), copy, ...draft.clips.slice(activeIndex + 1)] }); setActiveIndex(activeIndex + 1); }}>重复片段</button><button className="button ghost sm text-danger" type="button" onClick={() => { change({ ...draft, clips: draft.clips.filter((_, index) => index !== activeIndex) }); setActiveIndex(Math.max(0, activeIndex - 1)); }}>移除</button></div></section> : null}
      <div className="episode-edit-timeline">{draft.clips.map((clip, index) => <button type="button" className={index === activeIndex ? "active" : ""} key={clip.tempKey} style={{ flexGrow: Math.max(1, (clip.sourceOutMs - clip.sourceInMs) / 1000) }} onClick={() => setActiveIndex(index)}><span>{index + 1}</span><strong>Take {takeById[clip.takeId]?.takeNo ?? clip.takeId.slice(-6)}</strong><small>{((clip.sourceOutMs - clip.sourceInMs) / 1000).toFixed(1)} 秒 · {clip.sourceAudioMode === "keep" ? "保留原声" : "静音"}</small></button>)}</div>
    </main></div>
    {problems.length ? <section className="notice notice-warning"><strong>保存前还需处理</strong><p>{problems.join("；")}</p></section> : null}
    <div className="episode-inline-actions"><button className="button primary" type="button" disabled={!enabled || busy || !dirty || Boolean(problems.length) || draft.expectedHeadRevision !== page.headRevision} onClick={() => void save()}>{busy ? "保存中…" : "保存新的粗剪版本"}</button>{current ? <span className="muted">当前 head：v{current.versionNo}</span> : <span className="muted">尚无粗剪版本</span>}</div>
    <section className="episode-version-history"><header><div><h4>粗剪历史</h4><p>历史列表只含摘要；选择后精确读取完整片段，并以它创建新分支。</p></div></header><div>{page.versions.map((version) => <button type="button" key={version.id} className={draft.basedOnVersionId === version.id ? "active" : ""} disabled={busy || historyLoading !== null} onClick={() => void loadHistorical(version.id)}><strong>v{version.versionNo}{version.id === page.currentVersionId ? " · 当前" : ""}</strong><span>{version.clipCount} 段 · {version.omissionCount} 省略 · {(version.totalDurationMs / 1000).toFixed(1)} 秒</span>{historyLoading === version.id ? <small>读取中…</small> : null}</button>)}</div>{page.nextBeforeVersionNo ? <button className="button ghost sm" type="button" disabled={busy} onClick={onLoadMore}>加载更早粗剪</button> : null}</section>
  </section>;
}

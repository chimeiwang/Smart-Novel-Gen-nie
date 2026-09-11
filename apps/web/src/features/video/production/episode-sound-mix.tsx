"use client";

import { useEffect, useMemo, useState } from "react";

import { loadLocalDraft, saveLocalDraft } from "./episode-api";
import { registerEpisodeSave } from "./episode-save-navigation";
import { mixDraftFromVersion, mixDraftProblems, type EpisodeMixDraft } from "./post-production-state";
import type {
  EpisodeAudioClipInput,
  EpisodeEditVersion,
  EpisodeMixVersion,
  EpisodeMixVersionList,
  EpisodePostAsset,
  ProductionBaseline,
  ScriptVersion,
  StoryboardVersion,
  VideoAsset,
} from "./types";

type TrackKind = EpisodeAudioClipInput["trackKind"];
type Props = {
  novelId: string;
  episodeId: string;
  baseline: ProductionBaseline;
  storyboard: StoryboardVersion;
  script: ScriptVersion;
  edit: EpisodeEditVersion | null;
  page: EpisodeMixVersionList;
  current: EpisodeMixVersion | null;
  audioAssets: VideoAsset[];
  busy: boolean;
  enabled: boolean;
  onSave: (draft: EpisodeMixDraft) => Promise<void>;
  onLoadVersion: (versionId: string) => Promise<EpisodeMixVersion>;
  onLoadMore: () => void;
  onUpload: (trackKind: TrackKind, file: File) => Promise<void>;
};

const TRACK_LABEL: Record<TrackKind, string> = { dialogue: "对白", narration: "旁白", ambience: "环境声", sfx: "音效", music: "音乐" };
const dutyForTrack = (kind: TrackKind): "voice" | "ambience" | "sfx" | "music" => kind === "dialogue" || kind === "narration" ? "voice" : kind;
const audioContentUrl = (assetId: string) => `/api/v1/video/assets/${encodeURIComponent(assetId)}/content`;

function asPostAssets(assets: VideoAsset[]): EpisodePostAsset[] {
  return assets.flatMap((asset) => asset.modality === "audio" && asset.durationMs && asset.durationMs > 0 ? [{ id: asset.id, name: asset.name, modality: "audio", mimeType: asset.mimeType, durationMs: asset.durationMs, byteSize: asset.byteSize, sha256: asset.sha256 }] : []);
}

function initialDraft(episodeId: string, baselineId: string, page: EpisodeMixVersionList, current: EpisodeMixVersion | null, edit: EpisodeEditVersion | null): EpisodeMixDraft {
  const stored = loadLocalDraft<{ baselineId: string; draft: EpisodeMixDraft }>(`inkforge:episode-mix-draft:${episodeId}:${baselineId}`);
  if (stored?.baselineId === baselineId && stored.draft?.editVersionId === edit?.id && Array.isArray(stored.draft.audioClips) && Array.isArray(stored.draft.subtitleCues)) return stored.draft;
  if (current && current.editVersionId === edit?.id) return mixDraftFromVersion(current);
  return { basedOnVersionId: current?.id ?? null, expectedHeadRevision: page.headRevision, editVersionId: edit?.id ?? "", audioClips: [], subtitleCues: [] };
}

export function EpisodeSoundMix({ novelId, episodeId, baseline, storyboard, script, edit, page, current, audioAssets, busy, enabled, onSave, onLoadVersion, onLoadMore, onUpload }: Props) {
  const storageKey = `inkforge:episode-mix-draft:${episodeId}:${baseline.id}`;
  const [draft, setDraft] = useState(() => initialDraft(episodeId, baseline.id, page, current, edit));
  const [initialFingerprint, setInitialFingerprint] = useState(() => JSON.stringify(draft));
  const [trackKind, setTrackKind] = useState<TrackKind>("music");
  const [assetId, setAssetId] = useState("");
  const [subtitleShotId, setSubtitleShotId] = useState(storyboard.shots[0]?.id ?? "");
  const [subtitleLineId, setSubtitleLineId] = useState("");
  const [historyLoading, setHistoryLoading] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const postAssets = useMemo(() => asPostAssets(audioAssets), [audioAssets]);
  const effectiveAssetId = postAssets.some((asset) => asset.id === assetId) ? assetId : postAssets.find((asset) => audioAssets.find((item) => item.id === asset.id)?.duty === dutyForTrack(trackKind))?.id ?? postAssets[0]?.id ?? "";
  const subtitleShot = storyboard.shots.find((shot) => shot.id === subtitleShotId) ?? storyboard.shots[0] ?? null;
  const scriptLines = useMemo(() => new Map((script.document.scenes ?? []).flatMap((scene) => (scene.lines ?? []).flatMap((line) => line.id ? [[line.id, line] as const] : []))), [script.document.scenes]);
  const lineOptions = (subtitleShot?.scriptLineIds ?? []).flatMap((lineId) => scriptLines.has(lineId) ? [{ id: lineId, line: scriptLines.get(lineId)! }] : []);
  const effectiveLineId = lineOptions.some((item) => item.id === subtitleLineId) ? subtitleLineId : lineOptions[0]?.id ?? "";
  const dirty = JSON.stringify(draft) !== initialFingerprint;
  const mixAlreadyCurrent = Boolean(!dirty && current && current.editVersionId === edit?.id);
  const problems = edit ? mixDraftProblems(edit, draft, postAssets, storyboard, script) : ["先保存一份有效粗剪版本"];

  useEffect(() => {
    saveLocalDraft(storageKey, dirty ? { baselineId: baseline.id, draft } : null);
  }, [baseline.id, dirty, draft, storageKey]);

  useEffect(() => registerEpisodeSave({
    novelId,
    episodeId: `${episodeId}:mix:${baseline.id}`,
    pending: () => dirty || busy || uploading,
    flush: async () => { if (dirty || busy || uploading) throw new Error("声音字幕工作区有尚未保存或尚未核对的内容"); },
  }), [baseline.id, busy, dirty, episodeId, novelId, uploading]);

  const change = (next: EpisodeMixDraft) => { setDraft(next); setError(null); };
  const updateAudio = (index: number, patch: Partial<EpisodeAudioClipInput>) => change({ ...draft, audioClips: draft.audioClips.map((clip, position) => position === index ? { ...clip, ...patch } : clip) });
  const addAudio = () => {
    const asset = postAssets.find((item) => item.id === effectiveAssetId);
    if (!asset || !edit) return;
    change({ ...draft, audioClips: [...draft.audioClips, { trackKind, assetId: asset.id, shotVersionId: null, timelineStartMs: 0, sourceInMs: 0, sourceOutMs: Math.min(asset.durationMs, edit.totalDurationMs), gainMillibels: trackKind === "music" ? -1200 : 0, fadeInMs: 0, fadeOutMs: 0 }] });
  };
  const addSubtitle = () => {
    if (!edit || !subtitleShot || !effectiveLineId) return;
    const line = scriptLines.get(effectiveLineId);
    if (!line) return;
    const clip = edit.clips.find((item) => item.shotVersionId === subtitleShot.id);
    const startMs = clip?.timelineStartMs ?? 0;
    const endMs = Math.min(edit.totalDurationMs, startMs + Math.max(500, Math.min(3_000, clip?.outputDurationMs ?? 3_000)));
    change({ ...draft, subtitleCues: [...draft.subtitleCues, { shotVersionId: subtitleShot.id, scriptLineId: effectiveLineId, startMs, endMs, speaker: null, text: line.text }] });
  };
  const loadHistorical = async (versionId: string) => {
    setHistoryLoading(versionId);
    setError(null);
    try {
      const version = await onLoadVersion(versionId);
      if (version.editVersionId !== edit?.id && !window.confirm("这份声音版本绑定的是其他粗剪。可以只读核对，但必须先切换到对应粗剪才能据此保存。继续加载吗？")) return;
      setDraft(mixDraftFromVersion(version));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "读取声音版本失败");
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
      setError(failure instanceof Error ? failure.message : "保存声音字幕版本失败");
    }
  };

  return <section className="episode-post-section episode-sound-mix">
    <header><div><span>{edit ? `粗剪 v${edit.versionNo}` : "尚无粗剪"}</span><h3>声音与字幕</h3><p>粗剪片段已经逐项决定保留原声或静音；附加音轨和字幕只能绑定本基线的明确素材与剧本节点。</p></div><div><strong>{draft.audioClips.length} 条音轨 · {draft.subtitleCues.length} 条字幕</strong><small>head revision {page.headRevision}</small></div></header>
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}
    {current && edit && current.editVersionId !== edit.id ? <p className="notice notice-warning">当前声音 v{current.versionNo} 基于粗剪 {current.editVersionId}，不会自动迁移到粗剪 v{edit.versionNo}。</p> : null}
    {draft.expectedHeadRevision !== page.headRevision ? <section className="notice notice-warning"><strong>声音 head 已变化，本地输入仍保留</strong><button className="button ghost sm" type="button" onClick={() => change({ ...draft, expectedHeadRevision: page.headRevision })}>核对后使用最新 revision</button></section> : null}
    <section className="episode-audio-add"><div className="grid-two"><label>音轨类型<select className="select" value={trackKind} onChange={(event) => { setTrackKind(event.target.value as TrackKind); setAssetId(""); }}>{Object.entries(TRACK_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>受控音频<select className="select" value={effectiveAssetId} onChange={(event) => setAssetId(event.target.value)}><option value="">选择已确认素材</option>{postAssets.map((asset) => <option value={asset.id} key={asset.id}>{asset.name} · {(asset.durationMs / 1000).toFixed(1)}s</option>)}</select></label></div><div className="episode-inline-actions"><button className="button" type="button" disabled={!edit || !effectiveAssetId || busy} onClick={addAudio}>加入音轨</button><label className="button ghost file-button">上传并确认权利<input type="file" accept="audio/*" disabled={busy || uploading || !enabled} onChange={(event) => { const file = event.target.files?.[0]; event.currentTarget.value = ""; if (!file || !window.confirm(`确认你有权将“${file.name}”用于本视频项目？`)) return; setUploading(true); void onUpload(trackKind, file).catch((failure) => setError(failure instanceof Error ? failure.message : "上传音频失败")).finally(() => setUploading(false)); }} /></label></div></section>
    <div className="episode-audio-list">{draft.audioClips.map((clip, index) => { const asset = postAssets.find((item) => item.id === clip.assetId); return <article key={`${clip.assetId}:${index}`}><header><div><strong>{TRACK_LABEL[clip.trackKind]} · {asset?.name ?? clip.assetId}</strong><small>{asset ? `${(asset.durationMs / 1000).toFixed(1)} 秒素材` : "素材待核对"}</small></div><audio controls preload="metadata" src={audioContentUrl(clip.assetId)} /></header><div className="grid-three"><label>时间线起点<input className="input" type="number" min={0} step={0.1} value={clip.timelineStartMs / 1000} onChange={(event) => updateAudio(index, { timelineStartMs: Math.round(Number(event.target.value) * 1000) })} /></label><label>素材入点<input className="input" type="number" min={0} step={0.1} value={clip.sourceInMs / 1000} onChange={(event) => updateAudio(index, { sourceInMs: Math.round(Number(event.target.value) * 1000) })} /></label><label>素材出点<input className="input" type="number" min={0} max={asset ? asset.durationMs / 1000 : undefined} step={0.1} value={clip.sourceOutMs / 1000} onChange={(event) => updateAudio(index, { sourceOutMs: Math.round(Number(event.target.value) * 1000) })} /></label></div><div className="grid-three"><label>增益（dB）<input className="input" type="number" min={-60} max={12} step={0.5} value={clip.gainMillibels / 100} onChange={(event) => updateAudio(index, { gainMillibels: Math.round(Number(event.target.value) * 100) })} /></label><label>淡入（秒）<input className="input" type="number" min={0} max={10} step={0.1} value={clip.fadeInMs / 1000} onChange={(event) => updateAudio(index, { fadeInMs: Math.round(Number(event.target.value) * 1000) })} /></label><label>淡出（秒）<input className="input" type="number" min={0} max={10} step={0.1} value={clip.fadeOutMs / 1000} onChange={(event) => updateAudio(index, { fadeOutMs: Math.round(Number(event.target.value) * 1000) })} /></label></div><label>关联镜头版本<select className="select" value={clip.shotVersionId ?? ""} onChange={(event) => updateAudio(index, { shotVersionId: event.target.value || null })}><option value="">整集音轨</option>{storyboard.shots.map((shot) => <option key={shot.id} value={shot.id}>镜头 {shot.ordinal} · {shot.content.title}</option>)}</select></label><button className="button ghost sm text-danger" type="button" onClick={() => change({ ...draft, audioClips: draft.audioClips.filter((_, position) => position !== index) })}>移除音轨</button></article>; })}{!draft.audioClips.length ? <p className="muted">没有附加音轨；粗剪里选择“保留原声”的片段仍会保留视频原声。</p> : null}</div>
    <section className="episode-subtitle-add"><div className="grid-two"><label>镜头版本<select className="select" value={subtitleShot?.id ?? ""} onChange={(event) => { setSubtitleShotId(event.target.value); setSubtitleLineId(""); }}>{storyboard.shots.map((shot) => <option key={shot.id} value={shot.id}>镜头 {shot.ordinal} · {shot.content.title}</option>)}</select></label><label>正式剧本节点<select className="select" value={effectiveLineId} onChange={(event) => setSubtitleLineId(event.target.value)}><option value="">选择该镜头绑定的台词</option>{lineOptions.map(({ id, line }) => <option value={id} key={id}>{line.kind === "dialogue" ? "对白" : line.kind === "narration" ? "旁白" : "行动"} · {line.text}</option>)}</select></label></div><button className="button" type="button" disabled={!edit || !effectiveLineId || busy} onClick={addSubtitle}>加入字幕</button></section>
    <div className="episode-subtitle-list">{draft.subtitleCues.map((cue, index) => <article key={`${cue.shotVersionId}:${cue.scriptLineId}:${index}`}><header><strong>字幕 {index + 1}</strong><span>{cue.scriptLineId}</span></header><div className="grid-two"><label>开始（秒）<input className="input" type="number" min={0} step={0.1} value={cue.startMs / 1000} onChange={(event) => change({ ...draft, subtitleCues: draft.subtitleCues.map((item, position) => position === index ? { ...item, startMs: Math.round(Number(event.target.value) * 1000) } : item) })} /></label><label>结束（秒）<input className="input" type="number" min={0.1} max={edit ? edit.totalDurationMs / 1000 : undefined} step={0.1} value={cue.endMs / 1000} onChange={(event) => change({ ...draft, subtitleCues: draft.subtitleCues.map((item, position) => position === index ? { ...item, endMs: Math.round(Number(event.target.value) * 1000) } : item) })} /></label></div><label>说话人<input className="input" maxLength={120} value={cue.speaker ?? ""} onChange={(event) => change({ ...draft, subtitleCues: draft.subtitleCues.map((item, position) => position === index ? { ...item, speaker: event.target.value || null } : item) })} /></label><label>字幕文案<textarea className="textarea" rows={2} maxLength={2000} value={cue.text} onChange={(event) => change({ ...draft, subtitleCues: draft.subtitleCues.map((item, position) => position === index ? { ...item, text: event.target.value } : item) })} /></label><button className="button ghost sm text-danger" type="button" onClick={() => change({ ...draft, subtitleCues: draft.subtitleCues.filter((_, position) => position !== index) })}>移除字幕</button></article>)}</div>
    {problems.length ? <section className="notice notice-warning"><strong>保存前还需处理</strong><p>{problems.join("；")}</p></section> : null}
    <div className="episode-inline-actions"><button className="button primary" type="button" disabled={!enabled || busy || uploading || mixAlreadyCurrent || Boolean(problems.length) || draft.expectedHeadRevision !== page.headRevision} onClick={() => void save()}>{busy ? "保存中…" : "保存声音字幕版本"}</button>{current ? <span className="muted">当前 head：v{current.versionNo}</span> : <span className="muted">尚无声音字幕版本</span>}</div>
    <section className="episode-version-history"><header><div><h4>声音字幕历史</h4><p>完整音轨和字幕仅在选择后精确读取。</p></div></header><div>{page.versions.map((version) => <button type="button" key={version.id} className={draft.basedOnVersionId === version.id ? "active" : ""} disabled={busy || historyLoading !== null} onClick={() => void loadHistorical(version.id)}><strong>v{version.versionNo}{version.id === page.currentVersionId ? " · 当前" : ""}</strong><span>粗剪 {version.editVersionId} · {version.audioClipCount} 音轨 · {version.subtitleCueCount} 字幕</span>{historyLoading === version.id ? <small>读取中…</small> : null}</button>)}</div>{page.nextBeforeVersionNo ? <button className="button ghost sm" type="button" disabled={busy} onClick={onLoadMore}>加载更早声音版本</button> : null}</section>
  </section>;
}

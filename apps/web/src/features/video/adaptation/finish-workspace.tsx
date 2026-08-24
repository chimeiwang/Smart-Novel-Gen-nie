"use client";

import { useEffect, useRef, useState } from "react";

import type {
  AudioTrackKind,
  EpisodeAudioClip,
  EpisodeMixVersion,
  EpisodeSubtitleCue,
  PostProductionWorkspace,
} from "./types";

const TRACK_LABEL: Record<AudioTrackKind, string> = {
  dialogue: "对白",
  narration: "旁白",
  ambience: "环境声",
  sfx: "音效",
  music: "音乐",
};

type Props = {
  workspace: PostProductionWorkspace | null;
  working: string | null;
  onLoadMixVersion: (versionId: string) => Promise<EpisodeMixVersion>;
  onSaveMix: (episodeNo: number, editVersionId: string, audioClips: EpisodeAudioClip[], subtitleCues: EpisodeSubtitleCue[], basedOnVersionId: string | null) => void;
  onUploadAudio: (trackKind: AudioTrackKind, file: File) => void;
  onStartExport: (episodeNo: number, editVersionId: string, mixVersionId: string, resolution: "720p" | "1080p", framesPerSecond: 24 | 25 | 30, burnSubtitles: boolean) => void;
  onRetryExport: (taskId: string) => void;
};

export function FinishWorkspace({
  workspace,
  working,
  onLoadMixVersion,
  onSaveMix,
  onUploadAudio,
  onStartExport,
  onRetryExport,
}: Props) {
  const [episodeNo, setEpisodeNo] = useState(1);
  const episode = workspace?.episodes.find((item) => item.episodeNo === episodeNo)
    ?? workspace?.episodes[0]
    ?? null;
  const edit = episode?.editHead.currentVersion ?? null;
  const mix = episode?.mixHead.currentVersion ?? null;
  const [audioClips, setAudioClips] = useState<EpisodeAudioClip[]>([]);
  const [subtitleCues, setSubtitleCues] = useState<EpisodeSubtitleCue[]>([]);
  const [basedOnVersionId, setBasedOnVersionId] = useState<string | null>(null);
  const [loadedVersionNo, setLoadedVersionNo] = useState<number | null>(null);
  const [historyLoading, setHistoryLoading] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [loadedAssetNames, setLoadedAssetNames] = useState<Record<string, string>>({});
  const [resolution, setResolution] = useState<"720p" | "1080p">("720p");
  const [framesPerSecond, setFramesPerSecond] = useState<24 | 25 | 30>(24);
  const [burnSubtitles, setBurnSubtitles] = useState(true);
  const formSourceKey = episode
    ? `${episode.episodeNo}:${edit?.id ?? "none"}:${mix?.id ?? "none"}:${mix?.editVersionId === edit?.id ? "aligned" : "stale"}`
    : "none";
  const loadedFormSourceKey = useRef<string | null>(null);

  useEffect(() => {
    if (!episode) return;
    if (loadedFormSourceKey.current === formSourceKey) return;
    loadedFormSourceKey.current = formSourceKey;
    const useCurrentMix = Boolean(mix && edit && mix.editVersionId === edit.id);
    const timer = window.setTimeout(() => {
      setEpisodeNo(episode.episodeNo);
      setAudioClips(useCurrentMix && mix ? mix.audioClips.map(({ trackKind, assetId, shotId, timelineStartMs, sourceInMs, sourceOutMs, gainMillibels, fadeInMs, fadeOutMs }) => ({
        trackKind,
        assetId,
        shotId,
        timelineStartMs,
        sourceInMs,
        sourceOutMs,
        gainMillibels,
        fadeInMs,
        fadeOutMs,
      })) : []);
      setSubtitleCues(useCurrentMix && mix ? mix.subtitleCues.map(({ shotId, startMs, endMs, speaker, text }) => ({ shotId, startMs, endMs, speaker, text })) : episode.suggestedSubtitleCues);
      setLoadedAssetNames(Object.fromEntries((useCurrentMix && mix ? mix.audioClips : []).map((clip) => [clip.assetId, clip.asset.name])));
      setBasedOnVersionId(mix?.id ?? null);
      setLoadedVersionNo(mix?.versionNo ?? null);
      setHistoryError(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [edit, episode, formSourceKey, mix]);

  if (!workspace || !episode) {
    return <div className="chapter-adaptation-empty"><strong>正在加载声音与输出工作区...</strong></div>;
  }
  const updateAudio = (index: number, patch: Partial<EpisodeAudioClip>) => setAudioClips((current) => current.map((clip, clipIndex) => clipIndex === index ? { ...clip, ...patch } : clip));
  const updateSubtitle = (index: number, patch: Partial<EpisodeSubtitleCue>) => setSubtitleCues((current) => current.map((cue, cueIndex) => cueIndex === index ? { ...cue, ...patch } : cue));
  const usableAudioAssets = workspace.audioAssets.filter((asset) => asset.durationMs !== null);
  const addAudio = (trackKind: AudioTrackKind) => {
    const asset = usableAudioAssets.find((item) => item.duty === dutyForTrack(trackKind)) ?? usableAudioAssets[0];
    if (!asset?.durationMs) return;
    setAudioClips((current) => [...current, {
      trackKind,
      assetId: asset.id,
      shotId: null,
      timelineStartMs: 0,
      sourceInMs: 0,
      sourceOutMs: Math.min(asset.durationMs ?? 1_000, edit?.totalDurationMs ?? asset.durationMs ?? 1_000),
      gainMillibels: trackKind === "music" ? -1200 : 0,
      fadeInMs: 0,
      fadeOutMs: 0,
    }]);
  };
  const loadHistoricalMix = async (versionId: string) => {
    setHistoryLoading(versionId);
    setHistoryError(null);
    try {
      const version = await onLoadMixVersion(versionId);
      setAudioClips(version.audioClips.map(({ trackKind, assetId, shotId, timelineStartMs, sourceInMs, sourceOutMs, gainMillibels, fadeInMs, fadeOutMs }) => ({
        trackKind,
        assetId,
        shotId,
        timelineStartMs,
        sourceInMs,
        sourceOutMs,
        gainMillibels,
        fadeInMs,
        fadeOutMs,
      })));
      setSubtitleCues(version.subtitleCues.map(({ shotId, startMs, endMs, speaker, text }) => ({ shotId, startMs, endMs, speaker, text })));
      setLoadedAssetNames(Object.fromEntries(version.audioClips.map((clip) => [clip.assetId, clip.asset.name])));
      setBasedOnVersionId(version.id);
      setLoadedVersionNo(version.versionNo);
    } catch (loadError) {
      setHistoryError(loadError instanceof Error ? loadError.message : "读取声音字幕历史版本失败");
    } finally {
      setHistoryLoading(null);
    }
  };
  const canExport = Boolean(
    edit
    && mix
    && mix.editVersionId === edit.id
    && !edit.clips.some((clip) => clip.takeId === null)
    && workspace.readiness.ffmpegAvailable
    && workspace.readiness.ffprobeAvailable,
  );
  const unavailableAudioAssetIds = audioClips
    .map((clip) => clip.assetId)
    .filter((assetId, index, values) => (
      values.indexOf(assetId) === index
      && !workspace.audioAssets.some((asset) => asset.id === assetId && asset.durationMs !== null)
    ));

  return (
    <div className="finish-workspace">
      <header className="post-production-toolbar">
        <label>分集
          <select className="select" value={episode.episodeNo} onChange={(event) => setEpisodeNo(Number(event.target.value))}>
            {workspace.episodes.map((item) => <option key={item.episodeNo} value={item.episodeNo}>第 {item.episodeNo} 集</option>)}
          </select>
        </label>
        <div><strong>声音与字幕 v{mix?.versionNo ?? 0}</strong><span>{loadedVersionNo ? `工作区基于声音 v${loadedVersionNo} · ` : ""}{edit ? `目标粗剪 v${edit.versionNo} · ${(edit.totalDurationMs / 1000).toFixed(1)} 秒` : "请先保存粗剪"}</span></div>
        <button className="button primary" type="button" disabled={!edit || working !== null || historyLoading !== null || unavailableAudioAssetIds.length > 0} onClick={() => edit && onSaveMix(episode.episodeNo, edit.id, audioClips, subtitleCues, basedOnVersionId)}>{working === "mix-save" ? "保存中..." : "保存声音字幕版本"}</button>
      </header>
      {episode.mixHead.staleAgainstCurrentEdit ? <div className="notice notice-warning">粗剪已经变化。当前表单以新粗剪和对白建议重新开始；旧声音版本仍保留，不会被静默套用。</div> : null}
      {unavailableAudioAssetIds.length ? <div className="notice notice-warning">历史版本引用了当前未锁定或授权已失效的音频，请逐轨替换后再保存。</div> : null}
      <div className="finish-grid">
        <section className="audio-track-editor">
          <header><div><h3>附加音轨</h3><span>Seedance Take 原声作为底声保留；这里叠加并可单轨替换。</span></div><div className="inline-actions"><button className="button ghost sm" type="button" disabled={!usableAudioAssets.length} onClick={() => addAudio("dialogue")}>+ 配音</button><button className="button ghost sm" type="button" disabled={!usableAudioAssets.length} onClick={() => addAudio("ambience")}>+ 环境</button><button className="button ghost sm" type="button" disabled={!usableAudioAssets.length} onClick={() => addAudio("sfx")}>+ 音效</button><button className="button ghost sm" type="button" disabled={!usableAudioAssets.length} onClick={() => addAudio("music")}>+ 音乐</button></div></header>
          {!usableAudioAssets.length ? <div className="post-production-empty-row">尚无已锁定且时长有效的音频。先上传配音、环境声、音效或音乐，再加入时间线。</div> : null}
          {audioClips.map((clip, index) => {
            const selectedAsset = workspace.audioAssets.find((asset) => asset.id === clip.assetId);
            return (
              <div className="audio-clip-row" key={`${clip.assetId}:${index}`}>
                <select className="select" value={clip.trackKind} onChange={(event) => updateAudio(index, { trackKind: event.target.value as AudioTrackKind })}>{Object.entries(TRACK_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                <select className="select" value={clip.assetId} onChange={(event) => {
                  const asset = workspace.audioAssets.find((item) => item.id === event.target.value);
                  updateAudio(index, { assetId: event.target.value, sourceInMs: 0, sourceOutMs: Math.min(asset?.durationMs ?? 1_000, edit?.totalDurationMs ?? 1_000) });
                }}>{!selectedAsset ? <option value={clip.assetId}>{loadedAssetNames[clip.assetId] ?? clip.assetId} · 当前不可用</option> : null}{workspace.audioAssets.map((asset) => <option disabled={asset.durationMs === null} key={asset.id} value={asset.id}>{asset.name}{asset.durationMs === null ? " · 时长未知" : ""}</option>)}</select>
                <label>开始<input className="input" type="number" min={0} step={0.1} value={clip.timelineStartMs / 1000} onChange={(event) => updateAudio(index, { timelineStartMs: Math.round(Number(event.target.value) * 1000) })} /></label>
                <label>源入<input className="input" type="number" min={0} step={0.1} value={clip.sourceInMs / 1000} onChange={(event) => updateAudio(index, { sourceInMs: Math.round(Number(event.target.value) * 1000) })} /></label>
                <label>源出<input className="input" type="number" min={0.1} max={(selectedAsset?.durationMs ?? 1000) / 1000} step={0.1} value={clip.sourceOutMs / 1000} onChange={(event) => updateAudio(index, { sourceOutMs: Math.round(Number(event.target.value) * 1000) })} /></label>
                <label>增益 dB<input className="input" type="number" min={-60} max={12} step={0.5} value={clip.gainMillibels / 100} onChange={(event) => updateAudio(index, { gainMillibels: Math.round(Number(event.target.value) * 100) })} /></label>
                <label>淡入<input className="input" type="number" min={0} max={10} step={0.1} value={clip.fadeInMs / 1000} onChange={(event) => updateAudio(index, { fadeInMs: Math.round(Number(event.target.value) * 1000) })} /></label>
                <label>淡出<input className="input" type="number" min={0} max={10} step={0.1} value={clip.fadeOutMs / 1000} onChange={(event) => updateAudio(index, { fadeOutMs: Math.round(Number(event.target.value) * 1000) })} /></label>
                <button className="button ghost sm" type="button" onClick={() => setAudioClips((current) => current.filter((_item, clipIndex) => clipIndex !== index))}>移除</button>
              </div>
            );
          })}
          <div className="audio-upload-row"><span>没有合适素材？</span>{(["dialogue", "ambience", "sfx", "music"] as AudioTrackKind[]).map((kind) => <label className="button secondary sm file-button" key={kind}>上传{TRACK_LABEL[kind]}<input type="file" accept="audio/mpeg,audio/wav" onChange={(event) => { const file = event.target.files?.[0]; if (file) onUploadAudio(kind, file); event.currentTarget.value = ""; }} /></label>)}</div>
        </section>
        <section className="subtitle-editor">
          <header><div><h3>字幕</h3><span>建议来自正式镜头对白，只是可编辑草稿。</span></div><button className="button ghost sm" type="button" disabled={!edit} onClick={() => edit && setSubtitleCues((current) => [...current, { shotId: null, startMs: 0, endMs: Math.min(1500, edit.totalDurationMs), speaker: null, text: "新字幕" }])}>+ 字幕</button></header>
          {subtitleCues.map((cue, index) => <div className="subtitle-cue-row" key={`${cue.startMs}:${index}`}>
            <div className="time-pair"><label>开始<input className="input" type="number" min={0} step={0.1} value={cue.startMs / 1000} onChange={(event) => updateSubtitle(index, { startMs: Math.round(Number(event.target.value) * 1000) })} /></label><label>结束<input className="input" type="number" min={0.1} step={0.1} value={cue.endMs / 1000} onChange={(event) => updateSubtitle(index, { endMs: Math.round(Number(event.target.value) * 1000) })} /></label></div>
            <input className="input" value={cue.speaker ?? ""} placeholder="说话人（可选）" onChange={(event) => updateSubtitle(index, { speaker: event.target.value || null })} />
            <textarea className="textarea" value={cue.text} onChange={(event) => updateSubtitle(index, { text: event.target.value })} />
            <button className="button ghost sm" type="button" onClick={() => setSubtitleCues((current) => current.filter((_item, cueIndex) => cueIndex !== index))}>删除</button>
          </div>)}
        </section>
      </div>
      <section className="version-history-panel">
        <header><div><h3>声音字幕历史</h3><span>可把任一历史轨道加载到当前粗剪，再保存为新分支。</span></div></header>
        {historyError ? <div className="notice notice-danger">{historyError}</div> : null}
        <div className="version-history-list">
          {episode.mixHistory.map((version) => {
            const current = version.id === episode.mixHead.currentVersion?.id;
            const loaded = version.id === basedOnVersionId;
            return <button className={loaded ? "active" : ""} key={version.id} type="button" disabled={historyLoading !== null || loaded} onClick={() => void loadHistoricalMix(version.id)}><strong>v{version.versionNo}{current ? " · 当前" : ""}</strong><span>粗剪 {version.editVersionId.slice(-6)}</span><small>{version.basedOnVersionId ? `基于 ${version.basedOnVersionId.slice(-6)}` : "首个版本"}</small>{historyLoading === version.id ? <i>读取中...</i> : null}</button>;
          })}
          {!episode.mixHistory.length ? <div className="post-production-empty-row">尚无已保存声音字幕版本。</div> : null}
        </div>
      </section>
      <section className="episode-export-panel">
        <header><div><h3>整集输出</h3><span>每次导出冻结粗剪、声音字幕、素材哈希和输出参数。</span></div><div className="export-controls"><label>清晰度<select className="select" value={resolution} onChange={(event) => setResolution(event.target.value as "720p" | "1080p")}><option value="720p">720p</option><option value="1080p">1080p</option></select></label><label>帧率<select className="select" value={framesPerSecond} onChange={(event) => setFramesPerSecond(Number(event.target.value) as 24 | 25 | 30)}><option value={24}>24 fps</option><option value={25}>25 fps</option><option value={30}>30 fps</option></select></label><label className="checkbox-label"><input type="checkbox" checked={burnSubtitles} onChange={(event) => setBurnSubtitles(event.target.checked)} />烧录字幕</label><button className="button primary" type="button" disabled={!canExport || working !== null} onClick={() => edit && mix && onStartExport(episode.episodeNo, edit.id, mix.id, resolution, framesPerSecond, burnSubtitles)}>{working === "export-start" ? "提交中..." : `导出 ${resolution} MP4`}</button></div></header>
        {workspace.readiness.blockers.map((blocker) => <div className="notice notice-warning" key={blocker}>{blocker}</div>)}
        {!edit ? <div className="post-production-empty-row">请先在“粗剪”中保存一个编辑版本。</div> : edit.clips.some((clip) => clip.takeId === null) ? <div className="notice notice-warning">粗剪仍有占位镜头，不能导出正式成片。</div> : !mix || mix.editVersionId !== edit.id ? <div className="notice notice-warning">先保存一个基于当前粗剪的声音字幕版本。</div> : null}
        <div className="export-history">
          {episode.exportTasks.map((task) => <div className="export-history-row" key={task.id}><div><strong>{task.export ? `成片 v${task.export.versionNo}` : `任务 ${task.id.slice(-6)}`}</strong><span>{exportStatus(task.status)} · {task.resolution}/{task.framesPerSecond}fps · {task.burnSubtitles ? "烧录字幕" : "无烧录字幕"} · 粗剪 {task.editVersionId.slice(-6)} · 声音 {task.mixVersionId.slice(-6)}</span>{task.lastErrorMessage ? <small>{task.lastErrorMessage}</small> : null}</div><div className="inline-actions">{task.export ? <a className="button secondary sm" href={task.export.asset.contentUrl} download>下载 MP4</a> : null}{task.status === "failed" ? <button className="button ghost sm" type="button" disabled={working !== null} onClick={() => onRetryExport(task.id)}>按原清单重试</button> : null}</div></div>)}
          {!episode.exportTasks.length ? <div className="post-production-empty-row">尚无导出版本。</div> : null}
        </div>
      </section>
    </div>
  );
}

function dutyForTrack(trackKind: AudioTrackKind): string {
  if (trackKind === "dialogue" || trackKind === "narration") return "voice";
  return trackKind;
}

function exportStatus(status: "pending" | "rendering" | "succeeded" | "failed"): string {
  return { pending: "等待导出", rendering: "导出中", succeeded: "已完成", failed: "导出失败" }[status];
}

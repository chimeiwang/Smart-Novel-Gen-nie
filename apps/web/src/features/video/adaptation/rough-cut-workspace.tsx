"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type {
  EpisodeEditClip,
  EpisodeEditVersion,
  PostProductionWorkspace,
} from "./types";

type Props = {
  workspace: PostProductionWorkspace | null;
  working: string | null;
  onLoadVersion: (versionId: string) => Promise<EpisodeEditVersion>;
  onSave: (episodeNo: number, clips: EpisodeEditClip[], basedOnVersionId: string | null) => void;
};

export function RoughCutWorkspace({ workspace, working, onLoadVersion, onSave }: Props) {
  const [episodeNo, setEpisodeNo] = useState(1);
  const episode = workspace?.episodes.find((item) => item.episodeNo === episodeNo)
    ?? workspace?.episodes[0]
    ?? null;
  const [clips, setClips] = useState<EpisodeEditClip[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [basedOnVersionId, setBasedOnVersionId] = useState<string | null>(null);
  const [loadedVersionNo, setLoadedVersionNo] = useState<number | null>(null);
  const [historyLoading, setHistoryLoading] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!episode) return;
    const source = episode.editHead.currentVersion?.clips ?? episode.defaultClips;
    const timer = window.setTimeout(() => {
      setEpisodeNo(episode.episodeNo);
      setClips(source.map(({ shotId, takeId, sourceInMs, sourceOutMs, outputDurationMs, transitionAfter, transitionDurationMs }) => ({
        shotId,
        takeId,
        sourceInMs,
        sourceOutMs,
        outputDurationMs,
        transitionAfter,
        transitionDurationMs,
      })));
      setActiveIndex(0);
      setBasedOnVersionId(episode.editHead.currentVersion?.id ?? null);
      setLoadedVersionNo(episode.editHead.currentVersion?.versionNo ?? null);
      setHistoryError(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [episode]);

  const shots = useMemo(() => new Map(episode?.shots.map((shot) => [shot.shotId, shot]) ?? []), [episode]);
  const activeClip = clips[activeIndex] ?? null;
  const activeShot = activeClip ? shots.get(activeClip.shotId) : null;
  const activeTake = activeShot?.takes.find((take) => take.id === activeClip?.takeId) ?? null;
  const totalMs = clips.reduce((sum, clip) => sum + clip.outputDurationMs, 0);

  if (!workspace || !episode) {
    return <div className="chapter-adaptation-empty"><strong>正在加载粗剪时间线...</strong></div>;
  }

  const updateClip = (index: number, patch: Partial<EpisodeEditClip>) => {
    setClips((current) => current.map((clip, clipIndex) => clipIndex === index ? { ...clip, ...patch } : clip));
  };
  const chooseTake = (index: number, takeId: string) => {
    const clip = clips[index];
    const shot = shots.get(clip.shotId);
    const take = shot?.takes.find((item) => item.id === takeId);
    if (!takeId || !take?.durationMs) {
      updateClip(index, {
        takeId: null,
        sourceInMs: null,
        sourceOutMs: null,
        outputDurationMs: shot?.timelineDurationMs ?? clip.outputDurationMs,
      });
      return;
    }
    const duration = Math.min(take.durationMs, shot?.timelineDurationMs ?? take.durationMs);
    updateClip(index, {
      takeId,
      sourceInMs: 0,
      sourceOutMs: duration,
      outputDurationMs: duration,
    });
  };
  const move = (index: number, offset: -1 | 1) => {
    const target = index + offset;
    if (target < 0 || target >= clips.length) return;
    setClips((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    setActiveIndex(target);
  };
  const loadHistoricalVersion = async (versionId: string) => {
    setHistoryLoading(versionId);
    setHistoryError(null);
    try {
      const version = await onLoadVersion(versionId);
      setClips(version.clips.map(({ shotId, takeId, sourceInMs, sourceOutMs, outputDurationMs, transitionAfter, transitionDurationMs }) => ({
        shotId,
        takeId,
        sourceInMs,
        sourceOutMs,
        outputDurationMs,
        transitionAfter,
        transitionDurationMs,
      })));
      setBasedOnVersionId(version.id);
      setLoadedVersionNo(version.versionNo);
      setActiveIndex(0);
    } catch (loadError) {
      setHistoryError(loadError instanceof Error ? loadError.message : "读取粗剪历史版本失败");
    } finally {
      setHistoryLoading(null);
    }
  };

  return (
    <div className="rough-cut-workspace">
      <header className="post-production-toolbar">
        <label>分集
          <select className="select" value={episode.episodeNo} onChange={(event) => setEpisodeNo(Number(event.target.value))}>
            {workspace.episodes.map((item) => <option key={item.episodeNo} value={item.episodeNo}>第 {item.episodeNo} 集</option>)}
          </select>
        </label>
        <div><strong>粗剪 v{episode.editHead.currentVersion?.versionNo ?? 0}</strong><span>{loadedVersionNo ? `工作区基于 v${loadedVersionNo} · ` : ""}{clips.length} 镜 · {(totalMs / 1000).toFixed(1)} 秒 · revision {episode.editHead.revision}</span></div>
        <button className="button primary" type="button" disabled={working !== null || historyLoading !== null || !clips.length} onClick={() => onSave(episode.episodeNo, clips, basedOnVersionId)}>{working === "edit-save" ? "保存中..." : "保存新粗剪版本"}</button>
      </header>
      <div className="rough-cut-preview">
        <div className="rough-cut-player">
          {activeTake && activeClip?.sourceInMs !== null ? (
            <video
              key={`${activeTake.id}:${activeIndex}`}
              ref={videoRef}
              src={activeTake.asset.contentUrl}
              controls
              onLoadedMetadata={(event) => { event.currentTarget.currentTime = (activeClip.sourceInMs ?? 0) / 1000; }}
              onTimeUpdate={(event) => {
                const sourceOutMs = activeClip.sourceOutMs;
                if (sourceOutMs != null && event.currentTarget.currentTime * 1000 >= sourceOutMs) {
                  event.currentTarget.pause();
                  if (activeIndex < clips.length - 1) setActiveIndex((index) => index + 1);
                }
              }}
            />
          ) : <div className="rough-cut-placeholder"><strong>占位镜头</strong><span>{activeShot?.title ?? "请选择时间线镜头"}</span></div>}
          <div className="rough-cut-player-caption"><strong>{activeShot?.shotKey} · {activeShot?.title}</strong><span>{activeClip ? `${(activeClip.outputDurationMs / 1000).toFixed(1)} 秒` : ""}</span></div>
        </div>
        <aside className="rough-cut-inspector">
          {activeClip && activeShot ? (
            <>
              <h3>{activeShot.title}</h3>
              <label>采用 Take
                <select className="select" value={activeClip.takeId ?? ""} onChange={(event) => chooseTake(activeIndex, event.target.value)}>
                  <option value="">保留占位</option>
                  {activeShot.takes.map((take) => <option key={take.id} value={take.id}>Take {take.takeNo}{take.id === activeShot.confirmedTakeId ? " · 当前确认" : ""}</option>)}
                </select>
              </label>
              {activeClip.takeId ? (
                <div className="time-pair">
                  <label>入点（秒）<input className="input" type="number" min={0} step={0.1} value={(activeClip.sourceInMs ?? 0) / 1000} onChange={(event) => {
                    const sourceInMs = Math.round(Number(event.target.value) * 1000);
                    const sourceOutMs = activeClip.sourceOutMs ?? sourceInMs + 500;
                    updateClip(activeIndex, { sourceInMs, outputDurationMs: Math.max(500, sourceOutMs - sourceInMs) });
                  }} /></label>
                  <label>出点（秒）<input className="input" type="number" min={0.5} step={0.1} value={(activeClip.sourceOutMs ?? 500) / 1000} onChange={(event) => {
                    const sourceOutMs = Math.round(Number(event.target.value) * 1000);
                    const sourceInMs = activeClip.sourceInMs ?? 0;
                    updateClip(activeIndex, { sourceOutMs, outputDurationMs: Math.max(500, sourceOutMs - sourceInMs) });
                  }} /></label>
                </div>
              ) : <label>占位时长（秒）<input className="input" type="number" min={0.5} step={0.1} value={activeClip.outputDurationMs / 1000} onChange={(event) => updateClip(activeIndex, { outputDurationMs: Math.max(500, Math.round(Number(event.target.value) * 1000)) })} /></label>}
              <label>镜后转场
                <select className="select" value={activeClip.transitionAfter} onChange={(event) => updateClip(activeIndex, event.target.value === "fade_black" ? { transitionAfter: "fade_black", transitionDurationMs: 300 } : { transitionAfter: "cut", transitionDurationMs: 0 })}>
                  <option value="cut">硬切</option><option value="fade_black">淡黑</option>
                </select>
              </label>
              {activeClip.transitionAfter === "fade_black" ? <label>转场时长（秒）<input className="input" type="number" min={0.1} max={2} step={0.1} value={activeClip.transitionDurationMs / 1000} onChange={(event) => updateClip(activeIndex, { transitionDurationMs: Math.round(Number(event.target.value) * 1000) })} /></label> : null}
              <div className="inline-actions"><button className="button ghost sm" type="button" disabled={activeIndex === 0} onClick={() => move(activeIndex, -1)}>前移</button><button className="button ghost sm" type="button" disabled={activeIndex === clips.length - 1} onClick={() => move(activeIndex, 1)}>后移</button></div>
            </>
          ) : null}
        </aside>
      </div>
      <div className="rough-cut-timeline">
        {clips.map((clip, index) => {
          const shot = shots.get(clip.shotId);
          const take = shot?.takes.find((item) => item.id === clip.takeId);
          return (
            <button className={index === activeIndex ? "active" : ""} key={clip.shotId} type="button" style={{ flexGrow: Math.max(1, clip.outputDurationMs / 1000) }} onClick={() => setActiveIndex(index)}>
              <span>{index + 1}</span><strong>{shot?.shotKey} · {shot?.title}</strong><small>{take ? `Take ${take.takeNo}` : "占位"} · {(clip.outputDurationMs / 1000).toFixed(1)}s</small>
            </button>
          );
        })}
      </div>
      <section className="version-history-panel">
        <header><div><h3>粗剪历史</h3><span>加载历史版本只改变当前工作区；保存时创建新分支版本。</span></div></header>
        {historyError ? <div className="notice notice-danger">{historyError}</div> : null}
        <div className="version-history-list">
          {episode.editHistory.map((version) => {
            const current = version.id === episode.editHead.currentVersion?.id;
            const loaded = version.id === basedOnVersionId;
            return <button className={loaded ? "active" : ""} key={version.id} type="button" disabled={historyLoading !== null || loaded} onClick={() => void loadHistoricalVersion(version.id)}><strong>v{version.versionNo}{current ? " · 当前" : ""}</strong><span>{(version.totalDurationMs / 1000).toFixed(1)} 秒</span><small>{version.basedOnVersionId ? `基于 ${version.basedOnVersionId.slice(-6)}` : "首个版本"}</small>{historyLoading === version.id ? <i>读取中...</i> : null}</button>;
          })}
          {!episode.editHistory.length ? <div className="post-production-empty-row">尚无已保存粗剪版本。</div> : null}
        </div>
      </section>
      {episode.mixHead.staleAgainstCurrentEdit ? <div className="notice notice-warning">当前声音版本基于旧粗剪；保存本版后请在“声音与输出”中显式重建或迁移。</div> : null}
    </div>
  );
}

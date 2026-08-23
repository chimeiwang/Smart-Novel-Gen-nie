"use client";

import { durationMetrics, flattenFormalShots, groupFormalEpisodes } from "./adaptation-state";
import { formatDuration } from "./shot-timeline";
import type { FormalPlan } from "./types";

export function EpisodeEditor({
  plan,
  breakAfterShotIds,
  targetEpisodeSeconds,
  onToggle,
}: {
  plan: FormalPlan;
  breakAfterShotIds: string[];
  targetEpisodeSeconds: 60 | 90 | 120;
  onToggle: (shotId: string) => void;
}) {
  const shots = flattenFormalShots(plan);
  const breaks = new Set(breakAfterShotIds);
  const episodes = groupFormalEpisodes(plan, breakAfterShotIds);
  return (
    <div className="adaptation-episode-layout">
      <section className="adaptation-episode-timeline">
        <header><strong>在正式镜头之间分集</strong><span>优先在戏剧节拍完成处结束</span></header>
        <div>
          {shots.map((shot, index) => (
            <div key={shot.id}>
              <div className="adaptation-episode-shot">
                <span>{shot.shotKey}</span><strong>{shot.title}</strong><small>{formatDuration(shot.timelineDurationMs)}</small>
              </div>
              {index < shots.length - 1 ? (
                <button
                  className={`adaptation-episode-boundary ${breaks.has(shot.id) ? "active" : ""}`}
                  type="button"
                  onClick={() => onToggle(shot.id)}
                >
                  {breaks.has(shot.id) ? "下一镜开始新一集 · 点击取消" : "+ 在此分集"}
                </button>
              ) : null}
            </div>
          ))}
        </div>
      </section>
      <aside className="adaptation-episode-summary">
        <header><strong>{episodes.length} 集</strong><span>目标单集 {targetEpisodeSeconds} 秒</span></header>
        {episodes.map((episode, index) => {
          const metrics = durationMetrics(episode);
          const seconds = metrics.totalMs / 1000;
          return (
            <article className={seconds > targetEpisodeSeconds * 1.15 ? "warning" : ""} key={episode[0]?.id}>
              <span>第 {index + 1} 集</span>
              <strong>{episode[0]?.title} → {episode.at(-1)?.title}</strong>
              <small>{episode.length} 镜 · {Number(seconds.toFixed(1))} 秒 · 平均 {formatDuration(metrics.averageMs)}</small>
              <div className="adaptation-duration-distribution">
                <i style={{ flex: metrics.fastCount }} title={`快镜 ${metrics.fastCount}`} />
                <i style={{ flex: metrics.standardCount }} title={`标准镜头 ${metrics.standardCount}`} />
                <i style={{ flex: metrics.slowCount }} title={`慢镜 ${metrics.slowCount}`} />
              </div>
              {seconds > targetEpisodeSeconds * 1.15 ? <em>超出目标时长，建议在节拍结束处继续分集。</em> : null}
            </article>
          );
        })}
      </aside>
    </div>
  );
}

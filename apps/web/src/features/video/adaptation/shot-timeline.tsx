"use client";

import { beatCoverageStatus, purposeLabel } from "./adaptation-state";
import type { CandidateShot, CoverageGoal } from "./types";

export type TimelineShot = CandidateShot & { id?: string };
export type TimelineBeat = {
  beatKey: string;
  title: string;
  dramaticTurn: string;
  coverageGoals: CoverageGoal[];
  shots: TimelineShot[];
};
export type TimelineScene = {
  sceneKey: string;
  title: string;
  locationLabel: string;
  timeLabel: string;
  objective: string;
  beats: TimelineBeat[];
};

export function ShotTimeline({
  scenes,
  selectedShotKey,
  onSelect,
  editable = false,
  onMergeScene,
}: {
  scenes: TimelineScene[];
  selectedShotKey: string | null;
  onSelect: (shotKey: string) => void;
  editable?: boolean;
  onMergeScene?: (sceneKey: string) => void;
}) {
  return (
    <section className="adaptation-timeline-panel">
      <header><strong>电影化镜头时间线</strong><span>Scene → Beat → Shot</span></header>
      <div className="adaptation-timeline-scroll">
        {scenes.map((scene, sceneIndex) => (
          <section className="adaptation-scene" key={scene.sceneKey}>
            <header>
              <span>{scene.sceneKey}</span>
              <div><strong>{scene.title}</strong><small>{scene.locationLabel} · {scene.timeLabel} · {scene.objective}</small></div>
              {editable && onMergeScene && sceneIndex < scenes.length - 1 ? <button className="button ghost sm" type="button" onClick={() => onMergeScene(scene.sceneKey)}>与下一场合并</button> : null}
            </header>
            {scene.beats.map((beat) => (
              <div className="adaptation-beat" key={beat.beatKey}>
                <div className="adaptation-beat-heading">
                  <span>{beat.beatKey}</span>
                  <div><strong>{beat.title}</strong><small>{beat.dramaticTurn}</small></div>
                </div>
                <div className="adaptation-goal-list">
                  {beatCoverageStatus(beat).map((goal) => (
                    <span className={goal.coveredBy.length ? "covered" : "uncovered"} key={goal.goalKey}>
                      {goal.goalKey} · {goal.description}
                      <i>{goal.coveredBy.length ? goal.coveredBy.join(" / ") : "未覆盖"}</i>
                    </span>
                  ))}
                </div>
                <div className="adaptation-shot-list">
                  {beat.shots.map((shot) => (
                    <button
                      className={`adaptation-shot-row ${selectedShotKey === shot.shotKey ? "selected" : ""}`}
                      type="button"
                      key={shot.shotKey}
                      onClick={() => onSelect(shot.shotKey)}
                    >
                      <span className="adaptation-shot-key">{shot.shotKey}</span>
                      <span className="adaptation-shot-copy">
                        <strong>{shot.title}</strong>
                        <small>{shot.storyFunction}</small>
                      </span>
                      <span className="adaptation-shot-meta">
                        <i>{purposeLabel(shot.narrativePurpose)}</i>
                        <i>{shotScaleLabel(shot.shotScale)}</i>
                        <i>{formatDuration(shot.timelineDurationMs)}</i>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ))}
      </div>
    </section>
  );
}

export function formatDuration(durationMs: number): string {
  return `${Number((durationMs / 1000).toFixed(1))}s`;
}

export function shotScaleLabel(value: CandidateShot["shotScale"]): string {
  const labels: Record<CandidateShot["shotScale"], string> = {
    extreme_long: "大全景",
    long: "全景",
    medium: "中景",
    medium_close: "中近景",
    close: "近景",
    extreme_close: "特写",
    over_shoulder: "过肩",
    two_shot: "双人镜头",
    pov: "主观镜头",
  };
  return labels[value];
}

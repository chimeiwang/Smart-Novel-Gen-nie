"use client";

import { flattenFormalShots } from "./adaptation-state";
import { formatDuration } from "./shot-timeline";
import type {
  FormalPlan,
  FormalShot,
  PromptVersion,
  RenderTask,
  RenderWorkspace,
  ShotTake,
} from "./types";

const ACTIVE_RENDER_STATUSES = new Set([
  "pending",
  "submitting",
  "queued",
  "running",
  "archiving",
]);

export function TakeWorkspace({
  plan,
  selectedShot,
  promptVersion,
  workspace,
  breakAfterShotIds,
  durationSeconds,
  resolution,
  compareTakeIds,
  working,
  onSelectShot,
  onDurationChange,
  onResolutionChange,
  onGenerate,
  onRetry,
  onConfirm,
  onToggleCompare,
}: {
  plan: FormalPlan;
  selectedShot: FormalShot | null;
  promptVersion: PromptVersion | null;
  workspace: RenderWorkspace | null;
  breakAfterShotIds: string[];
  durationSeconds: number;
  resolution: "480p" | "720p" | "1080p";
  compareTakeIds: string[];
  working: string | null;
  onSelectShot: (shotKey: string) => void;
  onDurationChange: (value: number) => void;
  onResolutionChange: (value: "480p" | "720p" | "1080p") => void;
  onGenerate: () => void;
  onRetry: (taskId: string) => void;
  onConfirm: (takeId: string) => void;
  onToggleCompare: (takeId: string) => void;
}) {
  const shots = flattenFormalShots(plan);
  const episodes = buildTakeNavigation(plan, breakAfterShotIds);
  const tasks = workspace?.tasks.filter((item) => item.shotId === selectedShot?.id) ?? [];
  const takes = workspace?.takes.filter((item) => item.shotId === selectedShot?.id) ?? [];
  const head = workspace?.takeHeads.find((item) => item.shotId === selectedShot?.id) ?? null;
  const selectedTakes = compareTakeIds
    .map((takeId) => takes.find((item) => item.id === takeId))
    .filter((item): item is ShotTake => Boolean(item));
  const activeTask = tasks.find((item) => ACTIVE_RENDER_STATUSES.has(item.status)) ?? null;
  const latestFailure = tasks.find((item) => isFailed(item.status)) ?? null;

  return (
    <div className="adaptation-take-layout">
      <aside className="adaptation-take-shots">
        <header><strong>正式镜头</strong><span>{shots.length} 镜</span></header>
        <div>{episodes.map((episode) => (
          <section className="adaptation-take-episode" key={episode.number}>
            <header><strong>第 {episode.number} 集</strong><span>{episode.shotCount} 镜</span></header>
            {episode.scenes.map((scene) => (
              <section className="adaptation-take-scene" key={`${episode.number}:${scene.id}`}>
                <header><span>{scene.sceneKey}</span><strong>{scene.title}</strong></header>
                {scene.beats.map((beat) => (
                  <div className="adaptation-take-beat" key={`${episode.number}:${scene.id}:${beat.id}`}>
                    <span>{beat.beatKey} · {beat.title}</span>
                    {beat.shots.map((shot) => {
                      const shotTakes = workspace?.takes.filter((item) => item.shotId === shot.id) ?? [];
                      const shotHead = workspace?.takeHeads.find((item) => item.shotId === shot.id) ?? null;
                      const shotActive = workspace?.tasks.some(
                        (item) => item.shotId === shot.id && ACTIVE_RENDER_STATUSES.has(item.status),
                      );
                      return (
                        <button
                          className={selectedShot?.id === shot.id ? "selected" : ""}
                          type="button"
                          key={shot.id}
                          onClick={() => onSelectShot(shot.shotKey)}
                        >
                          <span>{shot.shotKey}</span>
                          <span>
                            <strong>{shot.title}</strong>
                            <small>{takeStatusLabel(shotTakes.length, Boolean(shotHead?.currentTakeId), Boolean(shotActive))}</small>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ))}
              </section>
            ))}
          </section>
        ))}</div>
      </aside>

      <section className="adaptation-take-main">
        {selectedShot ? (
          <>
            <header className="adaptation-take-header">
              <div>
                <h3>{selectedShot.shotKey} · {selectedShot.title}</h3>
                <span>剪辑目标 {formatDuration(selectedShot.timelineDurationMs)} · 已有 {takes.length} 个候选</span>
              </div>
              <div className="adaptation-take-generate">
                <label>生成时长
                  <select
                    className="select"
                    value={durationSeconds}
                    disabled={Boolean(activeTask) || working !== null}
                    onChange={(event) => onDurationChange(Number(event.target.value))}
                  >
                    {Array.from({ length: 11 }, (_, index) => index + 2).map((seconds) => (
                      <option key={seconds} value={seconds}>{seconds} 秒</option>
                    ))}
                  </select>
                </label>
                <label>分辨率
                  <select
                    className="select"
                    value={resolution}
                    disabled={Boolean(activeTask) || working !== null}
                    onChange={(event) => onResolutionChange(event.target.value as "480p" | "720p" | "1080p")}
                  >
                    <option value="480p">480p</option>
                    <option value="720p">720p</option>
                    <option value="1080p">1080p</option>
                  </select>
                </label>
                <button
                  className="button primary"
                  type="button"
                  disabled={!promptVersion || Boolean(activeTask) || working !== null || !workspace?.readiness.enabled}
                  onClick={onGenerate}
                >
                  {activeTask ? renderStatusLabel(activeTask.status) : working === "render-start" ? "提交中..." : "生成新候选"}
                </button>
              </div>
            </header>

            {!promptVersion ? (
              <div className="notice notice-warning">当前镜头还没有正式提示词，请返回“逐镜提示词”保存后再生成。</div>
            ) : null}
            {(workspace?.readiness.blockers ?? []).map((blocker) => (
              <div className="notice notice-warning" key={blocker}>{blocker}</div>
            ))}
            {activeTask ? (
              <section className="adaptation-render-progress">
                <span className="status-dot active" />
                <div><strong>{renderStatusLabel(activeTask.status)}</strong><small>任务 {activeTask.id} · 页面可安全刷新</small></div>
              </section>
            ) : null}
            {latestFailure ? (
              <section className="notice notice-danger adaptation-render-failure">
                <div>
                  <strong>{renderStatusLabel(latestFailure.status)}</strong>
                  <span>{latestFailure.lastErrorMessage ?? latestFailure.lastErrorCode ?? "生成失败"}</span>
                </div>
                <button
                  className="button secondary sm"
                  type="button"
                  disabled={working !== null || Boolean(activeTask) || !workspace?.readiness.enabled}
                  onClick={() => onRetry(latestFailure.id)}
                >
                  {working === `render-retry:${latestFailure.id}` ? "重试中..." : "按原输入重试"}
                </button>
              </section>
            ) : null}

            {selectedTakes.length ? (
              <section className={`adaptation-take-compare count-${selectedTakes.length}`}>
                <header><strong>候选对比</strong><span>{selectedTakes.length === 1 ? "再选一个候选可并排比较" : "同步查看两次生成结果"}</span></header>
                <div>{selectedTakes.map((take) => (
                  <TakePlayer
                    key={take.id}
                    take={take}
                    current={head?.currentTakeId === take.id}
                    confirming={working === `take-confirm:${take.id}`}
                    onConfirm={() => onConfirm(take.id)}
                  />
                ))}</div>
              </section>
            ) : null}

            <section className="adaptation-take-candidates">
              <header><strong>全部候选 Take</strong><span>选择最多两个进行比较；确认只切换当前采用指针</span></header>
              {takes.length ? (
                <div>{takes.map((take) => {
                  const task = tasks.find((item) => item.id === take.taskId) ?? null;
                  const comparing = compareTakeIds.includes(take.id);
                  return (
                    <article className={head?.currentTakeId === take.id ? "current" : ""} key={take.id}>
                      <video controls preload="metadata" src={takeContentUrl(take.id)} />
                      <header>
                        <div><strong>Take {take.takeNo}</strong><span>{head?.currentTakeId === take.id ? "当前采用" : "候选"}</span></div>
                        <label>
                          <input type="checkbox" checked={comparing} onChange={() => onToggleCompare(take.id)} />
                          对比
                        </label>
                      </header>
                      <dl>
                        <dt>生成输入</dt><dd>提示词 {promptIdentity(task, take)} · {task?.manifest.durationSeconds ?? "-"} 秒 · {task?.manifest.resolution ?? "-"}</dd>
                        <dt>参考图</dt><dd>{task?.manifest.references?.length ?? 0} 张</dd>
                        <dt>模型</dt><dd>{take.model}</dd>
                      </dl>
                      {task ? <details><summary>查看冻结提示词</summary><p>{task.manifest.promptText}</p></details> : null}
                      <button
                        className={head?.currentTakeId === take.id ? "button ghost sm" : "button secondary sm"}
                        type="button"
                        disabled={head?.currentTakeId === take.id || working !== null}
                        onClick={() => onConfirm(take.id)}
                      >
                        {head?.currentTakeId === take.id ? "已确认" : working === `take-confirm:${take.id}` ? "确认中..." : "确认为当前 Take"}
                      </button>
                    </article>
                  );
                })}</div>
              ) : (
                <div className="empty">还没有候选视频。每次生成会保留为独立 Take，不会覆盖之前结果。</div>
              )}
            </section>
          </>
        ) : <div className="empty">请选择一个正式镜头。</div>}
      </section>
    </div>
  );
}

function TakePlayer({
  take,
  current,
  confirming,
  onConfirm,
}: {
  take: ShotTake;
  current: boolean;
  confirming: boolean;
  onConfirm: () => void;
}) {
  return (
    <article>
      <video controls preload="metadata" src={takeContentUrl(take.id)} />
      <footer>
        <div><strong>Take {take.takeNo}</strong><span>{current ? "当前采用" : `${take.asset.durationMs ? formatDuration(take.asset.durationMs) : "时长待识别"}`}</span></div>
        <button className="button secondary sm" type="button" disabled={current || confirming} onClick={onConfirm}>{current ? "已确认" : confirming ? "确认中..." : "确认"}</button>
      </footer>
    </article>
  );
}

function takeContentUrl(takeId: string): string {
  return `/api/v1/video/takes/${encodeURIComponent(takeId)}/content`;
}

function takeStatusLabel(takeCount: number, confirmed: boolean, active: boolean): string {
  if (active) return "生成中";
  if (confirmed) return `${takeCount} 个候选 · 已确认`;
  if (takeCount) return `${takeCount} 个候选 · 待选片`;
  return "未生成";
}

function isFailed(status: string): boolean {
  return ["submission_unknown", "failed", "expired", "cancelled"].includes(status);
}

function renderStatusLabel(status: string): string {
  return {
    pending: "等待提交",
    submitting: "正在提交即梦",
    submission_unknown: "提交结果不确定",
    queued: "即梦排队中",
    running: "即梦生成中",
    archiving: "正在归档视频",
    succeeded: "生成成功",
    failed: "生成失败",
    expired: "供应商任务已过期",
    cancelled: "供应商任务已取消",
  }[status] ?? status;
}

function promptIdentity(task: RenderTask | null, take: ShotTake): string {
  if (!task || task.promptVersionId !== take.promptVersionId) return "-";
  return `#${task.manifest.promptContentHash.slice(0, 8)}`;
}

type TakeNavigation = Array<{
  number: number;
  shotCount: number;
  scenes: Array<{
    id: string;
    sceneKey: string;
    title: string;
    beats: Array<{
      id: string;
      beatKey: string;
      title: string;
      shots: FormalShot[];
    }>;
  }>;
}>;

function buildTakeNavigation(plan: FormalPlan, breakAfterShotIds: string[]): TakeNavigation {
  const boundaries = new Set(breakAfterShotIds);
  const episodes: TakeNavigation = [{ number: 1, shotCount: 0, scenes: [] }];
  for (const scene of plan.scenes) {
    for (const beat of scene.beats) {
      for (const shot of beat.shots) {
        const episode = episodes.at(-1)!;
        let sceneGroup = episode.scenes.at(-1);
        if (sceneGroup?.id !== scene.id) {
          sceneGroup = {
            id: scene.id,
            sceneKey: scene.sceneKey,
            title: scene.title,
            beats: [],
          };
          episode.scenes.push(sceneGroup);
        }
        let beatGroup = sceneGroup.beats.at(-1);
        if (beatGroup?.id !== beat.id) {
          beatGroup = {
            id: beat.id,
            beatKey: beat.beatKey,
            title: beat.title,
            shots: [],
          };
          sceneGroup.beats.push(beatGroup);
        }
        beatGroup.shots.push(shot);
        episode.shotCount += 1;
        if (boundaries.has(shot.id)) {
          episodes.push({ number: episode.number + 1, shotCount: 0, scenes: [] });
        }
      }
    }
  }
  if (episodes.at(-1)?.shotCount === 0 && episodes.length > 1) episodes.pop();
  return episodes;
}

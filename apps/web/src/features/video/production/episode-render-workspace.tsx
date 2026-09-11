"use client";
/* eslint-disable @next/next/no-img-element */

import { useEffect, useMemo, useState } from "react";

import { ApiResponseError } from "@/lib/api/response";
import { assetPreviewUrl } from "../adaptation/visual-canon-state";
import { startTaskPolling } from "../adaptation/task-polling";
import { commandResultIsUnknown, loadLocalDraft, saveLocalDraft } from "./episode-api";
import {
  episodeTakeContentUrl,
  getEpisodeRenderTask,
  listTakeCandidates,
  retryEpisodeRender,
  startEpisodeRender,
} from "./production-api";
import type {
  EpisodeRenderTask,
  ProductionBaseline,
  ProductionCapability,
  RetryEpisodeRenderRequest,
  StartEpisodeRenderRequest,
  TakeCandidateList,
} from "./types";

type RenderCommand =
  | { kind: "start"; baselineId: string; shotId: string; body: StartEpisodeRenderRequest }
  | { kind: "retry"; taskId: string; body: RetryEpisodeRenderRequest };

type Props = {
  episodeId: string;
  baseline: ProductionBaseline;
  capability: ProductionCapability;
  enabled: boolean;
  onOpenAdoptionReview: () => void;
};

const terminal = new Set(["succeeded", "failed", "expired", "cancelled"]);
const retryable = new Set(["failed", "expired", "cancelled"]);
const errorText = (failure: unknown) => failure instanceof Error ? failure.message : "镜头任务操作失败";
const requestId = () => crypto.randomUUID();

function loadRenderCommand(key: string): RenderCommand | null {
  const value = loadLocalDraft<RenderCommand>(key);
  if (!value || !["start", "retry"].includes(value.kind) || typeof value.body?.clientRequestId !== "string") return null;
  return value;
}

function loadTaskIds(key: string): string[] {
  const value = loadLocalDraft<unknown>(key);
  return Array.isArray(value) ? [...new Set(value.filter((item): item is string => typeof item === "string"))] : [];
}

export function EpisodeRenderWorkspace({ episodeId, baseline, capability, enabled, onOpenAdoptionReview }: Props) {
  const [selectedShotId, setSelectedShotId] = useState(baseline.shots[0]?.shotId ?? "");
  const [tasks, setTasks] = useState<Record<string, EpisodeRenderTask>>({});
  const [takePage, setTakePage] = useState<TakeCandidateList | null>(null);
  const [takeRefresh, setTakeRefresh] = useState(0);
  const [feeConfirmed, setFeeConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const commandStorage = `inkforge:episode-render-command:${episodeId}:${baseline.id}`;
  const taskStorage = `inkforge:episode-render-tasks:${episodeId}:${baseline.id}`;
  const [pendingCommand, setPendingCommand] = useState<RenderCommand | null>(() => loadRenderCommand(commandStorage));
  const [knownTaskIds] = useState(() => loadTaskIds(taskStorage));
  const [tasksHydrated, setTasksHydrated] = useState(knownTaskIds.length === 0);
  const [restoreAttempt, setRestoreAttempt] = useState(0);

  const selectedShot = baseline.shots.find((shot) => shot.shotId === selectedShotId) ?? baseline.shots[0] ?? null;
  const selectedShotVersionId = selectedShot?.shotVersionId;
  const shotTasks = useMemo(() => Object.values(tasks)
    .filter((task) => task.shotId === selectedShot?.shotId && task.productionBaselineId === baseline.id)
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt)), [baseline.id, selectedShot?.shotId, tasks]);
  const activeTask = shotTasks.find((task) => !terminal.has(task.status)) ?? null;
  const latestFailure = shotTasks.find((task) => retryable.has(task.status)) ?? null;
  const exactTakes = (takePage?.targetShotVersionId === selectedShot?.shotVersionId ? takePage.takes : [])
    .filter((take) => take.sourceBaselineId === baseline.id && take.sourceShotVersionId === selectedShot?.shotVersionId);
  const activeTaskKey = Object.values(tasks).filter((task) => !terminal.has(task.status)).map((task) => task.id).sort().join(":");
  const capabilityMismatch = selectedShot ? selectedShot.inputSnapshot.provider !== capability.provider
    || selectedShot.inputSnapshot.model !== capability.model
    || selectedShot.inputSnapshot.executionMode !== capability.executionMode
    || selectedShot.inputSnapshot.resolution !== capability.allowedResolution
    || selectedShot.inputSnapshot.outputFormat !== capability.allowedOutputFormat : false;
  const frozenKeyframes = selectedShot?.inputSnapshot.keyframes ?? [];

  useEffect(() => {
    let alive = true;
    if (!knownTaskIds.length) return () => { alive = false; };
    void Promise.allSettled(knownTaskIds.map((taskId) => getEpisodeRenderTask(episodeId, taskId))).then((results) => {
      if (!alive) return;
      const retryFailure = results.find((result) => result.status === "rejected" && !(result.reason instanceof ApiResponseError && result.reason.status === 404));
      if (retryFailure?.status === "rejected") {
        setError(`无法恢复已知镜头任务：${errorText(retryFailure.reason)}`);
        return;
      }
      const loaded = results.flatMap((result) => result.status === "fulfilled" ? [result.value] : []);
      setTasks(Object.fromEntries(loaded.filter((task) => task.productionBaselineId === baseline.id).map((task) => [task.id, task])));
      setTasksHydrated(true);
    });
    return () => { alive = false; };
  }, [baseline.id, episodeId, knownTaskIds, restoreAttempt]);

  useEffect(() => {
    if (!tasksHydrated) return;
    const ids = Object.values(tasks).filter((task) => task.productionBaselineId === baseline.id).map((task) => task.id);
    saveLocalDraft(taskStorage, ids.length ? ids : null);
  }, [baseline.id, taskStorage, tasks, tasksHydrated]);

  useEffect(() => {
    let alive = true;
    if (!selectedShotVersionId) return () => { alive = false; };
    void listTakeCandidates(episodeId, selectedShotVersionId).then((page) => {
      if (alive) setTakePage(page);
    }).catch((failure) => { if (alive) setError(errorText(failure)); });
    return () => { alive = false; };
  }, [episodeId, selectedShotVersionId, takeRefresh]);

  useEffect(() => {
    if (!activeTaskKey) return;
    const activeTaskIds = activeTaskKey.split(":");
    return startTaskPolling(async (signal) => {
      const refreshed = await Promise.all(activeTaskIds.map((taskId) => getEpisodeRenderTask(episodeId, taskId, signal)));
      if (signal.aborted) return false;
      setTasks((current) => ({ ...current, ...Object.fromEntries(refreshed.map((task) => [task.id, task])) }));
      if (refreshed.some((task) => task.status === "succeeded")) setTakeRefresh((value) => value + 1);
      return refreshed.some((task) => !terminal.has(task.status));
    }, (failure) => setError(`暂时无法刷新镜头任务，仍会按原任务继续核对：${errorText(failure)}`), 1800);
  }, [activeTaskKey, episodeId]);

  const rememberTask = (task: EpisodeRenderTask) => {
    if (task.episodeId !== episodeId || task.productionBaselineId !== baseline.id) throw new Error("镜头任务不属于当前制作基线");
    setTasks((current) => ({ ...current, [task.id]: task }));
    if (task.status === "succeeded") setTakeRefresh((value) => value + 1);
  };

  const execute = async (command: RenderCommand) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    setPendingCommand(command);
    saveLocalDraft(commandStorage, command);
    try {
      const task = command.kind === "start"
        ? await startEpisodeRender(episodeId, command.baselineId, command.shotId, command.body)
        : await retryEpisodeRender(episodeId, command.taskId, command.body);
      rememberTask(task);
      saveLocalDraft(commandStorage, null);
      setPendingCommand(null);
      setNotice(task.inputSnapshot.executionMode === "simulated" ? "模拟任务已受理，不会调用供应商或产生供应商费用。" : "真实任务已受理，将按冻结输入执行。");
    } catch (failure) {
      if (!commandResultIsUnknown(failure)) {
        saveLocalDraft(commandStorage, null);
        setPendingCommand(null);
      }
      setError(commandResultIsUnknown(failure) ? "提交结果尚未确认。原请求已保留，只能按相同 clientRequestId 重放核对。" : errorText(failure));
    } finally {
      setBusy(false);
    }
  };

  const start = () => {
    if (!selectedShot || activeTask || pendingCommand || capabilityMismatch) return;
    const live = selectedShot.inputSnapshot.executionMode === "live";
    if (live && !feeConfirmed) return;
    void execute({ kind: "start", baselineId: baseline.id, shotId: selectedShot.shotId, body: { clientRequestId: requestId(), feeConfirmed: live } });
  };

  const retry = (task: EpisodeRenderTask) => {
    const live = task.inputSnapshot.executionMode === "live";
    if (live && !feeConfirmed) return;
    void execute({ kind: "retry", taskId: task.id, body: { clientRequestId: requestId(), feeConfirmed: live } });
  };

  if (!selectedShot) return <section className="episode-empty"><h3>制作基线没有镜头</h3></section>;
  return <div className="episode-render-workspace">
    <header><div><span>制作基线 v{baseline.versionNo}</span><h3>逐镜生成与候选</h3><p>每次任务只读取这份基线的冻结输入。完成只形成 Take，不能自动进入粗剪或当前制作。</p></div><span className={`status ${selectedShot.inputSnapshot.executionMode === "simulated" ? "warning" : "danger"}`}>{selectedShot.inputSnapshot.executionMode === "simulated" ? "隔离模拟" : "真实执行"}</span></header>
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}{notice ? <p className="notice" role="status">{notice}</p> : null}
    {!tasksHydrated ? <section className="notice notice-warning"><strong>正在恢复本基线已知任务</strong><p>恢复完成前不会新建第二个任务。</p><button className="button ghost sm" type="button" onClick={() => setRestoreAttempt((value) => value + 1)}>重新读取任务</button></section> : null}
    {pendingCommand ? <section className="notice"><strong>任务提交结果待核对</strong><p>原请求和 clientRequestId 已保留，不会新建第二次生成。</p><button className="button" type="button" disabled={busy} onClick={() => void execute(pendingCommand)}>按原请求核对</button></section> : null}
    <div className="episode-render-layout"><aside className="episode-render-shot-list">{baseline.shots.map((shot) => {
      const currentTasks = Object.values(tasks).filter((task) => task.shotId === shot.shotId);
      const active = currentTasks.some((task) => !terminal.has(task.status));
      return <button type="button" className={shot.shotId === selectedShot.shotId ? "active" : ""} key={shot.shotVersionId} onClick={() => { setSelectedShotId(shot.shotId); setFeeConfirmed(false); setError(null); }}><span>{String(shot.ordinal).padStart(2, "0")}</span><div><strong>{shot.inputSnapshot.prompt}</strong><small>{shot.status === "adopted" ? "基线已有采用" : "待生产"} · {active ? "任务进行中" : `${currentTasks.length} 个已知任务`}</small></div></button>;
    })}</aside><main className="episode-render-main">
      <section className="episode-render-input"><header><div><span>镜头 {selectedShot.ordinal}</span><h4>{selectedShot.inputSnapshot.prompt}</h4></div><strong>{selectedShot.inputSnapshot.durationSeconds} 秒</strong></header><dl><div><dt>身份</dt><dd>{selectedShot.shotVersionId}</dd></div><div><dt>模型</dt><dd>{selectedShot.inputSnapshot.provider} · {selectedShot.inputSnapshot.model}</dd></div><div><dt>输出</dt><dd>{selectedShot.inputSnapshot.ratio} · {selectedShot.inputSnapshot.resolution} · {selectedShot.inputSnapshot.outputFormat} · {selectedShot.inputSnapshot.generateAudio ? "含原生声音" : "静音生成"}</dd></div><div><dt>冻结图片</dt><dd>{selectedShot.inputSnapshot.references.length} 个视觉参考 · {frozenKeyframes.length} 个关键帧</dd></div><div><dt>输入哈希</dt><dd>{selectedShot.inputHash}</dd></div></dl>
        <section className="episode-render-keyframes"><header><strong>冻结关键帧</strong><span>基线输入 {selectedShot.inputSnapshot.schemaVersion}</span></header>{frozenKeyframes.length ? <div>{frozenKeyframes.map((keyframe) => <article key={keyframe.keyframeVersionId}><img src={assetPreviewUrl(keyframe.assetId)} alt={`${keyframeRoleLabel(keyframe.role)}冻结关键帧`} /><div><strong>{keyframe.ordinal}. {keyframeRoleLabel(keyframe.role)}</strong><span>{keyframeDutyLabel(keyframe.duty)} · {keyframe.mimeType}</span><small>关键帧版本 {keyframe.keyframeVersionId}</small><small>素材 {keyframe.assetId}</small><small>SHA-256 {keyframe.sha256}</small><small>内容哈希 {keyframe.contentHash}</small></div></article>)}</div> : <p>本镜头没有冻结关键帧；生成仍会使用上方已冻结的视觉参考。</p>}</section>
        {capabilityMismatch ? <p className="notice notice-warning">这份历史基线的模型或执行能力与服务端当前允许值不同，可继续查看已有候选，但不能从浏览器拼装新参数发起任务。</p> : null}
        {selectedShot.inputSnapshot.executionMode === "live" ? <label className="episode-baseline-ack"><input type="checkbox" checked={feeConfirmed} disabled={busy || Boolean(activeTask)} onChange={(event) => setFeeConfirmed(event.target.checked)} />我确认按这份冻结清单真实调用供应商并可能产生费用</label> : <p className="notice">本镜头冻结为模拟执行。生成结果会明确标记为模拟占位视频。</p>}
        <button className="button primary" type="button" disabled={!enabled || !tasksHydrated || busy || capabilityMismatch || Boolean(activeTask) || Boolean(pendingCommand) || (selectedShot.inputSnapshot.executionMode === "live" && !feeConfirmed)} onClick={start}>{activeTask ? renderStatusLabel(activeTask.status, activeTask.inputSnapshot.executionMode) : busy ? "提交中…" : selectedShot.inputSnapshot.executionMode === "simulated" ? "生成模拟候选" : "生成新候选"}</button>
      </section>
      {activeTask ? <section className="episode-render-progress"><span className="status-dot active" /><div><strong>{renderStatusLabel(activeTask.status, activeTask.inputSnapshot.executionMode)}</strong><small>任务 {activeTask.id} · 已轮询 {activeTask.pollCount} 次 · 页面可安全刷新</small>{activeTask.lastErrorMessage ? <small>{activeTask.lastErrorMessage}</small> : null}</div></section> : null}
      {!activeTask && latestFailure ? <section className="notice notice-danger"><strong>{renderStatusLabel(latestFailure.status, latestFailure.inputSnapshot.executionMode)}</strong><p>{latestFailure.lastErrorMessage ?? latestFailure.lastErrorCode ?? "生成没有完成"}</p><button className="button ghost sm" type="button" disabled={!tasksHydrated || busy || Boolean(pendingCommand) || (latestFailure.inputSnapshot.executionMode === "live" && !feeConfirmed)} onClick={() => retry(latestFailure)}>按原冻结输入重试</button></section> : null}
      <section className="episode-render-candidates"><header><div><h4>本基线本镜头的 Take</h4><p>仅展示源基线和源镜头版本都精确匹配的已归档候选。</p></div><span>{exactTakes.length} 个</span></header>{exactTakes.length ? <div>{exactTakes.map((take) => <article key={take.id}><video controls preload="metadata" src={episodeTakeContentUrl(episodeId, take.id)} /><header><div><strong>Take {take.takeNo}</strong><span className={`status ${take.adopted ? "" : "warning"}`}>{take.adopted ? "已有采用记录" : "待采用"}</span></div><small>{(take.durationMs / 1000).toFixed(1)} 秒 · {take.width && take.height ? `${take.width}×${take.height}` : "实测尺寸缺失"} · {take.model}</small></header></article>)}</div> : <div className="episode-empty compact"><h4>还没有已归档候选</h4><p>任务成功后会在这里回读不可变 Take；模拟结果不会伪装成真实供应商媒体。</p></div>}<button className="button ghost" type="button" onClick={onOpenAdoptionReview}>核对 Take 并确认新的制作基线</button></section>
    </main></div>
  </div>;
}

function renderStatusLabel(status: EpisodeRenderTask["status"], mode: EpisodeRenderTask["inputSnapshot"]["executionMode"]): string {
  const simulated = mode === "simulated";
  return {
    pending: "等待提交",
    submitting: simulated ? "正在提交模拟任务" : "正在提交即梦",
    submission_unknown: "供应商提交结果不确定",
    queued: simulated ? "模拟任务排队中" : "即梦排队中",
    running: simulated ? "生成模拟视频中" : "即梦生成中",
    archiving: "正在归档媒体与尾帧",
    succeeded: simulated ? "模拟候选已归档" : "候选已归档",
    failed: "生成失败",
    expired: "供应商任务已过期",
    cancelled: "任务已取消",
  }[status];
}

function keyframeRoleLabel(role: "initial_state" | "transition_anchor" | "end_state"): string {
  return { initial_state: "首帧", transition_anchor: "转折帧", end_state: "尾帧" }[role];
}

function keyframeDutyLabel(duty: "identity" | "costume" | "scene" | "prop" | "storyboard" | "keyframe"): string {
  return { identity: "身份定妆", costume: "服装定妆", scene: "场景定妆", prop: "道具定妆", storyboard: "分镜图", keyframe: "关键帧" }[duty];
}

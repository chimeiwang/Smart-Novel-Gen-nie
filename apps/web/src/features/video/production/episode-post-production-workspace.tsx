"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiResponseError } from "@/lib/api/response";
import { startTaskPolling } from "../adaptation/task-polling";
import { EpisodeDelivery } from "./episode-delivery";
import { commandResultIsUnknown, loadLocalDraft, saveLocalDraft } from "./episode-api";
import { EpisodeRoughCut } from "./episode-rough-cut";
import { EpisodeSoundMix } from "./episode-sound-mix";
import type { EpisodeEditDraft, EpisodeMixDraft } from "./post-production-state";
import {
  createEpisodeEditVersion,
  createEpisodeMixVersion,
  getEpisodeEditVersion,
  getEpisodeExportTask,
  getEpisodeMixVersion,
  getEpisodeScriptVersion,
  getStoryboardVersion,
  getVideoProject,
  listEpisodeEditVersions,
  listEpisodeMixVersions,
  retryEpisodeExport,
  startEpisodeExport,
  uploadEpisodeAudioAsset,
} from "./production-api";
import type {
  CreateEpisodeEditRequest,
  CreateEpisodeMixRequest,
  EpisodeEditVersion,
  EpisodeEditVersionList,
  EpisodeExportTask,
  EpisodeMixVersion,
  EpisodeMixVersionList,
  ProductionBaseline,
  RetryEpisodeExportRequest,
  ScriptVersion,
  StartEpisodeExportRequest,
  StoryboardVersion,
  VideoAsset,
} from "./types";

type PostCommand =
  | { kind: "edit"; body: CreateEpisodeEditRequest }
  | { kind: "mix"; body: CreateEpisodeMixRequest }
  | { kind: "export-start"; body: StartEpisodeExportRequest }
  | { kind: "export-retry"; taskId: string; body: RetryEpisodeExportRequest };

type LoadedPost = {
  editPage: EpisodeEditVersionList;
  currentEdit: EpisodeEditVersion | null;
  mixPage: EpisodeMixVersionList;
  currentMix: EpisodeMixVersion | null;
  storyboard: StoryboardVersion;
  script: ScriptVersion;
  audioAssets: VideoAsset[];
};

type Props = {
  novelId: string;
  projectId: string;
  episodeId: string;
  baseline: ProductionBaseline;
  enabled: boolean;
  onDeliveryChanged: () => Promise<unknown>;
};

const requestId = () => crypto.randomUUID();
const errorText = (failure: unknown) => failure instanceof Error ? failure.message : "后期操作失败";

function loadPostCommand(key: string): PostCommand | null {
  const value = loadLocalDraft<PostCommand>(key);
  return value && ["edit", "mix", "export-start", "export-retry"].includes(value.kind) && typeof value.body?.clientRequestId === "string" ? value : null;
}

function loadTaskIds(key: string): string[] {
  const value = loadLocalDraft<unknown>(key);
  return Array.isArray(value) ? [...new Set(value.filter((item): item is string => typeof item === "string"))] : [];
}

export function EpisodePostProductionWorkspace({ novelId, projectId, episodeId, baseline, enabled, onDeliveryChanged }: Props) {
  const [loaded, setLoaded] = useState<LoadedPost | null>(null);
  const [tasks, setTasks] = useState<Record<string, EpisodeExportTask>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const commandStorage = `inkforge:episode-post-command:${episodeId}:${baseline.id}`;
  const taskStorage = `inkforge:episode-export-tasks:${episodeId}:${baseline.id}`;
  const [pendingCommand, setPendingCommand] = useState<PostCommand | null>(() => loadPostCommand(commandStorage));
  const [knownTaskIds] = useState(() => loadTaskIds(taskStorage));
  const [tasksHydrated, setTasksHydrated] = useState(knownTaskIds.length === 0);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const activeTaskKey = Object.values(tasks).filter((task) => task.status === "pending" || task.status === "rendering").map((task) => task.id).sort().join(":");

  const loadHeads = useCallback(async (): Promise<LoadedPost> => {
    const [editPage, mixPage, storyboard, script, project] = await Promise.all([
      listEpisodeEditVersions(episodeId, baseline.id),
      listEpisodeMixVersions(episodeId, baseline.id),
      getStoryboardVersion(episodeId, baseline.storyboardVersionId),
      getEpisodeScriptVersion(episodeId, baseline.scriptVersionId),
      getVideoProject(projectId),
    ]);
    const [currentEdit, currentMix] = await Promise.all([
      editPage.currentVersionId ? getEpisodeEditVersion(episodeId, baseline.id, editPage.currentVersionId) : Promise.resolve(null),
      mixPage.currentVersionId ? getEpisodeMixVersion(episodeId, baseline.id, mixPage.currentVersionId) : Promise.resolve(null),
    ]);
    return {
      editPage,
      currentEdit,
      mixPage,
      currentMix,
      storyboard,
      script,
      audioAssets: project.assets.filter((asset) => asset.modality === "audio" && asset.rightsStatus === "confirmed" && Boolean(asset.lockedAt) && Boolean(asset.durationMs)),
    };
  }, [baseline.id, baseline.scriptVersionId, baseline.storyboardVersionId, episodeId, projectId]);

  useEffect(() => {
    let alive = true;
    void loadHeads().then((value) => { if (alive) { setLoaded(value); setError(null); } }).catch((failure) => { if (alive) setError(errorText(failure)); });
    return () => { alive = false; };
  }, [loadHeads, restoreAttempt]);

  useEffect(() => {
    let alive = true;
    if (!knownTaskIds.length) return () => { alive = false; };
    void Promise.allSettled(knownTaskIds.map((taskId) => getEpisodeExportTask(episodeId, baseline.id, taskId))).then((results) => {
      if (!alive) return;
      const retryFailure = results.find((result) => result.status === "rejected" && !(result.reason instanceof ApiResponseError && result.reason.status === 404));
      if (retryFailure?.status === "rejected") {
        setError(`无法恢复已知导出任务：${errorText(retryFailure.reason)}`);
        return;
      }
      const restored = results.flatMap((result) => result.status === "fulfilled" && result.value.productionBaselineId === baseline.id ? [result.value] : []);
      setTasks(Object.fromEntries(restored.map((task) => [task.id, task])));
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
    if (!activeTaskKey) return;
    const ids = activeTaskKey.split(":");
    return startTaskPolling(async (signal) => {
      const refreshed = await Promise.all(ids.map((taskId) => getEpisodeExportTask(episodeId, baseline.id, taskId, signal)));
      if (signal.aborted) return false;
      setTasks((current) => ({ ...current, ...Object.fromEntries(refreshed.map((task) => [task.id, task])) }));
      if (refreshed.some((task) => task.status === "succeeded" && task.export)) await onDeliveryChanged();
      return refreshed.some((task) => task.status === "pending" || task.status === "rendering");
    }, (failure) => setError(`暂时无法刷新导出任务，仍会按 taskId 继续核对：${errorText(failure)}`), 1800);
  }, [activeTaskKey, baseline.id, episodeId, onDeliveryChanged]);

  const execute = async (command: PostCommand) => {
    if (busy) throw new Error("已有后期命令正在处理");
    setBusy(true);
    setError(null);
    setNotice(null);
    setPendingCommand(command);
    saveLocalDraft(commandStorage, command);
    try {
      if (command.kind === "edit") {
        const version = await createEpisodeEditVersion(episodeId, baseline.id, command.body);
        saveLocalDraft(`inkforge:episode-edit-draft:${episodeId}:${baseline.id}`, null);
        setLoaded((current) => current ? { ...current, currentEdit: version, editPage: { ...current.editPage, headRevision: version.headRevision, currentVersionId: version.id, versions: [version, ...current.editPage.versions.filter((item) => item.id !== version.id)] } } : current);
        setNotice(`已创建粗剪 v${version.versionNo}；现有声音与交付版本没有自动改变。`);
      } else if (command.kind === "mix") {
        const version = await createEpisodeMixVersion(episodeId, baseline.id, command.body);
        saveLocalDraft(`inkforge:episode-mix-draft:${episodeId}:${baseline.id}`, null);
        setLoaded((current) => current ? { ...current, currentMix: version, mixPage: { ...current.mixPage, headRevision: version.headRevision, currentVersionId: version.id, versions: [version, ...current.mixPage.versions.filter((item) => item.id !== version.id)] } } : current);
        setNotice(`已创建声音字幕 v${version.versionNo}。`);
      } else {
        const task = command.kind === "export-start"
          ? await startEpisodeExport(episodeId, baseline.id, command.body)
          : await retryEpisodeExport(episodeId, baseline.id, command.taskId, command.body);
        setTasks((current) => ({ ...current, [task.id]: task }));
        setNotice("导出任务已受理；任务只读取提交时冻结的版本组合与媒体清单。");
      }
      saveLocalDraft(commandStorage, null);
      setPendingCommand(null);
    } catch (failure) {
      if (!commandResultIsUnknown(failure)) {
        saveLocalDraft(commandStorage, null);
        setPendingCommand(null);
      }
      if (failure instanceof ApiResponseError && failure.status === 409) {
        const latest = await loadHeads();
        setLoaded(latest);
      }
      const message = commandResultIsUnknown(failure)
        ? "操作结果尚未确认。已保留完整路径、请求体和 clientRequestId，只能按原请求重放。"
        : errorText(failure);
      setError(message);
      throw new Error(message);
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async (draft: EpisodeEditDraft) => {
    await execute({ kind: "edit", body: { clientRequestId: requestId(), expectedHeadRevision: draft.expectedHeadRevision, basedOnVersionId: draft.basedOnVersionId, clips: draft.clips, omissions: draft.omissions } });
  };
  const saveMix = async (draft: EpisodeMixDraft) => {
    await execute({ kind: "mix", body: { clientRequestId: requestId(), expectedHeadRevision: draft.expectedHeadRevision, basedOnVersionId: draft.basedOnVersionId, editVersionId: draft.editVersionId, audioClips: draft.audioClips, subtitleCues: draft.subtitleCues } });
  };
  const uploadAudio = async (trackKind: Parameters<typeof EpisodeSoundMix>[0]["onUpload"] extends (kind: infer K, file: File) => Promise<void> ? K : never, file: File) => {
    if (busy) throw new Error("已有后期操作正在处理");
    setBusy(true);
    setError(null);
    try {
      const duty = trackKind === "dialogue" || trackKind === "narration" ? "voice" : trackKind;
      await uploadEpisodeAudioAsset(projectId, file, duty, `${trackKind} · ${file.name}`);
      const project = await getVideoProject(projectId);
      setLoaded((current) => current ? { ...current, audioAssets: project.assets.filter((asset) => asset.modality === "audio" && asset.rightsStatus === "confirmed" && Boolean(asset.lockedAt) && Boolean(asset.durationMs)) } : current);
    } finally {
      setBusy(false);
    }
  };
  const loadMoreEdits = () => {
    if (!loaded?.editPage.nextBeforeVersionNo || busy) return;
    setBusy(true);
    void listEpisodeEditVersions(episodeId, baseline.id, loaded.editPage.nextBeforeVersionNo).then((next) => setLoaded((current) => current ? { ...current, editPage: { ...next, versions: [...current.editPage.versions, ...next.versions.filter((item) => !current.editPage.versions.some((old) => old.id === item.id))] } } : current)).catch((failure) => setError(errorText(failure))).finally(() => setBusy(false));
  };
  const loadMoreMixes = () => {
    if (!loaded?.mixPage.nextBeforeVersionNo || busy) return;
    setBusy(true);
    void listEpisodeMixVersions(episodeId, baseline.id, loaded.mixPage.nextBeforeVersionNo).then((next) => setLoaded((current) => current ? { ...current, mixPage: { ...next, versions: [...current.mixPage.versions, ...next.versions.filter((item) => !current.mixPage.versions.some((old) => old.id === item.id))] } } : current)).catch((failure) => setError(errorText(failure))).finally(() => setBusy(false));
  };

  if (!loaded || !tasksHydrated) return <section className="episode-empty"><h3>{error ? "无法完整读取本基线后期状态" : "正在读取本基线后期状态…"}</h3>{error ? <><p className="notice notice-danger">{error}</p><button className="button ghost" type="button" onClick={() => setRestoreAttempt((value) => value + 1)}>重新读取后期状态</button></> : <p>将精确读取粗剪 head、声音 head、正式剧本、分镜和已知导出任务。</p>}</section>;
  const exportTasks = Object.values(tasks).sort((left, right) => right.createdAt.localeCompare(left.createdAt));
  return <div className="episode-post-workspace">
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}{notice ? <p className="notice" role="status">{notice}</p> : null}
    {pendingCommand ? <section className="notice"><strong>后期命令结果待核对</strong><p>不会换用新请求标识，也不会临时读取新 head。</p><button className="button" type="button" disabled={busy} onClick={() => void execute(pendingCommand).catch(() => undefined)}>按原请求核对</button></section> : null}
    <EpisodeRoughCut key={`${baseline.id}:${loaded.currentEdit?.id ?? "none"}:${loaded.editPage.headRevision}`} novelId={novelId} episodeId={episodeId} baseline={baseline} page={loaded.editPage} current={loaded.currentEdit} busy={busy || Boolean(pendingCommand)} enabled={enabled} onSave={saveEdit} onLoadVersion={(versionId) => getEpisodeEditVersion(episodeId, baseline.id, versionId)} onLoadMore={loadMoreEdits} />
    <EpisodeSoundMix key={`${baseline.id}:${loaded.currentEdit?.id ?? "none"}:${loaded.currentMix?.id ?? "none"}:${loaded.mixPage.headRevision}`} novelId={novelId} episodeId={episodeId} baseline={baseline} storyboard={loaded.storyboard} script={loaded.script} edit={loaded.currentEdit} page={loaded.mixPage} current={loaded.currentMix} audioAssets={loaded.audioAssets} busy={busy || Boolean(pendingCommand)} enabled={enabled} onSave={saveMix} onLoadVersion={(versionId) => getEpisodeMixVersion(episodeId, baseline.id, versionId)} onLoadMore={loadMoreMixes} onUpload={uploadAudio} />
    <EpisodeDelivery episodeId={episodeId} baseline={baseline} edit={loaded.currentEdit} mix={loaded.currentMix} tasks={exportTasks} busy={busy || Boolean(pendingCommand)} enabled={enabled} onStart={(body) => void execute({ kind: "export-start", body: { clientRequestId: requestId(), ...body } }).catch(() => undefined)} onRetry={(task) => void execute({ kind: "export-retry", taskId: task.id, body: { clientRequestId: requestId() } }).catch(() => undefined)} />
  </div>;
}

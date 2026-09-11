"use client";

import { useCallback, useEffect, useReducer, useState } from "react";

import { ApiResponseError } from "@/lib/api/response";
import { WorkspaceDialog } from "@/features/workspace/workspace-dialog";
import { loadVisualCanons, subscribeVisualCanonChange } from "../adaptation/video-project-context";
import { startTaskPolling } from "../adaptation/task-polling";
import type { VisualCanon } from "../adaptation/types";
import { cancelScriptRun, commandResultIsUnknown, getEpisode, loadLocalDraft, loadPendingRunCancellation, saveLocalDraft, type PendingRunCancellation } from "./episode-api";
import { EpisodeSessionContext } from "./episode-request-scope";
import { flushEpisodeSaves, registerEpisodeSave } from "./episode-save-navigation";
import { EpisodeStoryboard } from "./episode-storyboard";
import { EpisodeRenderWorkspace } from "./episode-render-workspace";
import { EpisodePostProductionWorkspace } from "./episode-post-production-workspace";
import { ImpactReviewPanel } from "./impact-review-panel";
import {
  executeProductionCommand,
  getStoryboardCandidate,
  getProductionBaseline,
  getProductionCapabilities,
  getStoryboardConfirmation,
  getStoryboardDraft,
  getStoryboardRun,
  getStoryboardVersion,
  listProductionBaselines,
  listStoryboardVersions,
  listStoryboardRuns,
  loadPendingProductionCommand,
  loadPendingStoryboardDraft,
  saveStoryboardDraft,
  type ProductionCommand,
} from "./production-api";
import { ProductionBaselineReview } from "./production-baseline-review";
import {
  productionKeyframeInputs,
  restoreProductionKeyframeSelection,
  type ProductionKeyframeSelection,
} from "./production-baseline-state";
import { baselineAdoptionInputs } from "./take-adoption-state";
import { ScriptDraftCoordinator, type DraftSnapshot } from "./script-draft-coordinator";
import { storyboardDraftFromResponse, type StoryboardWorkingDraft } from "./storyboard-document-state";
import { StoryboardPreview } from "./storyboard-preview";
import { StoryboardCandidateReview } from "./storyboard-candidate-review";
import { ProductionBaselineAdoptionStatus } from "./take-adoption-review";
import type {
  EpisodeDetail,
  ProductionBaseline,
  ProductionBaselineList,
  ProductionCapability,
  ProductionKeyframeRole,
  ScriptVersion,
  StoryboardConfirmation,
  StoryboardCandidate,
  StoryboardDraft,
  StoryboardVersion,
  StoryboardVersionList,
  StoryboardRunList,
  StoryboardRun,
  TakeAdoption,
  TakeCandidate,
  CreateTakeAdoptionRequest,
} from "./types";

type LoadedProduction = {
  draft: StoryboardDraft;
  versions: StoryboardVersionList;
  baselines: ProductionBaselineList;
  currentStoryboard: StoryboardVersion | null;
  currentBaseline: ProductionBaseline | null;
  capability: ProductionCapability;
  canons: VisualCanon[];
  runs: StoryboardRunList;
};

type Props = {
  detail: EpisodeDetail;
  enabled: boolean;
  targetAspectRatio: string;
  onEpisodeChanged: (detail: EpisodeDetail) => void;
};

const requestId = () => crypto.randomUUID();
const errorText = (failure: unknown) => failure instanceof Error ? failure.message : "操作失败，请重试";
const runActive = (status: string) => !["succeeded", "completed", "failed", "cancelled", "canceled"].includes(status);
const validRatio = (value: string): "16:9" | "4:3" | "1:1" | "3:4" | "9:16" | "21:9" | "adaptive" => (
  ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"].includes(value) ? value as ReturnType<typeof validRatio> : "9:16"
);

export function EpisodeProductionSurface({ detail, enabled, targetAspectRatio, onEpisodeChanged }: Props) {
  const [loaded, setLoaded] = useState<LoadedProduction | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const episodeId = detail.episode.id;
    void Promise.all([
      getStoryboardDraft(episodeId),
      listStoryboardVersions(episodeId),
      listProductionBaselines(episodeId),
      getProductionCapabilities(),
      loadVisualCanons(detail.episode.projectId),
      listStoryboardRuns(episodeId),
      detail.episode.currentStoryboardVersionId ? getStoryboardVersion(episodeId, detail.episode.currentStoryboardVersionId) : Promise.resolve(null),
      detail.episode.currentProductionBaselineId ? getProductionBaseline(episodeId, detail.episode.currentProductionBaselineId) : Promise.resolve(null),
    ]).then(([draft, versions, baselines, capability, canons, runs, currentStoryboard, currentBaseline]) => {
      if (alive) setLoaded({ draft, versions, baselines, capability, canons, runs, currentStoryboard, currentBaseline });
    }).catch((failure) => { if (alive) setError(errorText(failure)); });
    return () => { alive = false; };
  }, [detail.episode.id, detail.episode.projectId, detail.episode.currentStoryboardVersionId, detail.episode.currentProductionBaselineId]);

  if (error) return <section className="episode-empty"><h3>无法读取分镜与制作状态</h3><p className="notice notice-danger" role="alert">{error}</p></section>;
  if (!loaded) return <section className="episode-empty"><h3>正在读取分镜与制作状态…</h3><p>将精确回读工作稿、正式版本、制作基线和服务端能力。</p></section>;
  const loadedMatchesHeads = (loaded.currentStoryboard?.id ?? null) === detail.episode.currentStoryboardVersionId
    && (loaded.currentBaseline?.id ?? null) === detail.episode.currentProductionBaselineId;
  if (!loadedMatchesHeads) return <section className="episode-empty"><h3>正在核对最新制作 head…</h3><p>旧版本保持可读，工作稿会按远端 revision 检查本地恢复内容。</p></section>;
  return <LoadedEpisodeProduction key={`${detail.episode.id}:${detail.episode.currentStoryboardVersionId ?? "none"}:${detail.episode.currentProductionBaselineId ?? "none"}`} detail={detail} enabled={enabled} targetAspectRatio={validRatio(targetAspectRatio)} initial={loaded} onEpisodeChanged={onEpisodeChanged} />;
}

function LoadedEpisodeProduction({ detail, enabled, targetAspectRatio, initial, onEpisodeChanged }: Props & { targetAspectRatio: ReturnType<typeof validRatio>; initial: LoadedProduction }) {
  const [, notify] = useReducer((value: number) => value + 1, 0);
  const [lifecycle] = useState(() => new EpisodeSessionContext(true));
  const [serverDraft, setServerDraft] = useState(initial.draft);
  const [canons, setCanons] = useState(initial.canons);
  const [versionPage, setVersionPage] = useState(initial.versions);
  const [baselinePage, setBaselinePage] = useState(initial.baselines);
  const [runPage, setRunPage] = useState(initial.runs);
  const [candidates, setCandidates] = useState<StoryboardCandidate[]>([]);
  const [currentStoryboard, setCurrentStoryboard] = useState(initial.currentStoryboard);
  const [currentBaseline, setCurrentBaseline] = useState(initial.currentBaseline);
  const [viewingStoryboard, setViewingStoryboard] = useState<StoryboardVersion | null>(null);
  const [viewingBaseline, setViewingBaseline] = useState<ProductionBaseline | null>(initial.currentBaseline);
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<StoryboardConfirmation | null>(null);
  const [remoteDraft, setRemoteDraft] = useState<StoryboardDraft | null>(null);
  const [baselineReview, setBaselineReview] = useState<StoryboardVersion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [instruction, setInstruction] = useState("");
  const [selectedAiShotIds, setSelectedAiShotIds] = useState<string[]>([]);
  const [productionStage, setProductionStage] = useState<"storyboard" | "render" | "post">("storyboard");
  const [cancelling, setCancelling] = useState(false);
  const draftStorage = `inkforge:episode-storyboard-draft:${detail.episode.id}`;
  const commandStorage = `inkforge:episode-production-command:${detail.episode.id}`;
  const confirmationStorage = `inkforge:episode-storyboard-confirmation:${detail.episode.id}`;
  const cancellationStorage = `inkforge:episode-storyboard-run-cancellation:${detail.episode.id}`;
  const adoptionSelectionStorage = `inkforge:episode-production-adoptions:${detail.episode.id}`;
  const keyframeSelectionStorage = `inkforge:episode-production-keyframes:${detail.episode.id}`;
  const [selectedAdoptionIds, setSelectedAdoptionIds] = useState<Record<string, string>>(() => {
    const stored = loadLocalDraft<Record<string, unknown>>(adoptionSelectionStorage) ?? {};
    return Object.fromEntries(Object.entries(stored).filter((entry): entry is [string, string] => typeof entry[1] === "string"));
  });
  const [selectedKeyframes, setSelectedKeyframes] = useState<ProductionKeyframeSelection>(() => (
    restoreProductionKeyframeSelection(loadLocalDraft<unknown>(keyframeSelectionStorage))
  ));
  const [pendingCommand, setPendingCommand] = useState<ProductionCommand | null>(() => loadPendingProductionCommand(commandStorage));
  const [pendingCancellation, setPendingCancellation] = useState<PendingRunCancellation | null>(() => loadPendingRunCancellation(cancellationStorage));
  const [coordinator] = useState(() => {
    const attemptedSaves = new Set<string>();
    const restored = loadPendingStoryboardDraft(draftStorage);
    if (restored?.pending) attemptedSaves.add(restored.pending.clientRequestId);
    return new ScriptDraftCoordinator<StoryboardWorkingDraft>({
      initial: { document: storyboardDraftFromResponse(initial.draft), revision: initial.draft.revision },
      restored,
      resourceLabel: "分镜",
      requestId,
      onChange: notify,
      persist: (value) => saveLocalDraft(draftStorage, value),
      save: async (write) => {
        if (!enabled || !initial.capability.videoPreviewEnabled) throw new ApiResponseError(403, "VIDEO_DISABLED", "当前环境未开放视频写入", null, undefined);
        const recovering = attemptedSaves.has(write.clientRequestId);
        attemptedSaves.add(write.clientRequestId);
        const result = await saveStoryboardDraft(detail.episode.id, write, recovering);
        if (lifecycle.alive) setServerDraft(result.response);
        return result;
      },
    });
  });
  const working = coordinator.document;
  const scriptVersion = detail.scriptVersions.find((version) => version.id === working.scriptVersionId) ?? null;
  const writable = enabled && initial.capability.videoPreviewEnabled;
  const locked = !writable || coordinator.commandBusy || cancelling || Boolean(pendingCommand) || Boolean(pendingCancellation) || Boolean(confirmation) || Boolean(viewingStoryboard);
  const activeRun = runPage.runs.find((run) => runActive(run.status)) ?? null;
  const selectedProductionBaseline = viewingBaseline ?? currentBaseline;

  const refreshEpisode = useCallback(async () => {
    const next = await getEpisode(detail.episode.id);
    if (lifecycle.alive) onEpisodeChanged(next);
    return next;
  }, [detail.episode.id, lifecycle, onEpisodeChanged]);

  const upsertRun = useCallback((run: StoryboardRun) => {
    setRunPage((current) => ({ ...current, runs: [run, ...current.runs.filter((item) => item.runId !== run.runId)] }));
  }, []);

  const loadCandidate = useCallback(async (artifactId: string) => {
    const candidate = await getStoryboardCandidate(detail.episode.id, artifactId);
    if (lifecycle.alive) setCandidates((current) => [candidate, ...current.filter((item) => item.artifactId !== candidate.artifactId)]);
    return candidate;
  }, [detail.episode.id, lifecycle]);

  useEffect(() => {
    lifecycle.activate();
    coordinator.activate();
    const unregister = registerEpisodeSave({
      novelId: detail.episode.novelId,
      episodeId: `${detail.episode.id}:storyboard`,
      pending: () => coordinator.dirty || coordinator.busy || Boolean(loadPendingProductionCommand(commandStorage)) || Boolean(loadPendingRunCancellation(cancellationStorage)),
      flush: async () => {
        if (coordinator.commandBusy || loadPendingProductionCommand(commandStorage)) throw new Error("本集制作命令尚未核对");
        if (loadPendingRunCancellation(cancellationStorage)) throw new Error("分镜任务取消结果尚未核对");
        await coordinator.flush();
      },
    });
    const artifactId = loadLocalDraft<string>(confirmationStorage);
    if (artifactId) void getStoryboardConfirmation(detail.episode.id, artifactId).then((value) => { if (lifecycle.alive) setConfirmation(value); }).catch((failure) => { if (lifecycle.alive) setError(errorText(failure)); });
    return () => { lifecycle.dispose(); coordinator.dispose(); unregister(); };
  }, [cancellationStorage, commandStorage, confirmationStorage, coordinator, detail.episode.id, detail.episode.novelId, lifecycle]);

  useEffect(() => {
    let active = true;
    const refreshCanons = () => { void loadVisualCanons(detail.episode.projectId).then((values) => { if (active) setCanons(values); }).catch((failure) => { if (active) setError(errorText(failure)); }); };
    const unsubscribe = subscribeVisualCanonChange(detail.episode.projectId, refreshCanons);
    window.addEventListener("focus", refreshCanons);
    return () => { active = false; unsubscribe(); window.removeEventListener("focus", refreshCanons); };
  }, [detail.episode.projectId]);

  useEffect(() => {
    saveLocalDraft(adoptionSelectionStorage, Object.keys(selectedAdoptionIds).length ? selectedAdoptionIds : null);
  }, [adoptionSelectionStorage, selectedAdoptionIds]);

  useEffect(() => {
    saveLocalDraft(keyframeSelectionStorage, Object.keys(selectedKeyframes).length ? selectedKeyframes : null);
  }, [keyframeSelectionStorage, selectedKeyframes]);

  useEffect(() => {
    const artifactId = runPage.runs.find((run) => run.artifactId)?.artifactId;
    if (!artifactId || candidates.some((candidate) => candidate.artifactId === artifactId)) return;
    void getStoryboardCandidate(detail.episode.id, artifactId).then((candidate) => {
      if (lifecycle.alive) setCandidates((current) => [candidate, ...current.filter((item) => item.artifactId !== candidate.artifactId)]);
    }).catch((failure) => { if (lifecycle.alive) setError(errorText(failure)); });
  }, [candidates, detail.episode.id, lifecycle, runPage.runs]);

  useEffect(() => {
    if (!activeRun) return;
    return startTaskPolling(async (signal) => {
      const run = await getStoryboardRun(detail.episode.id, activeRun.runId, signal);
      if (signal.aborted || !lifecycle.alive) return false;
      upsertRun(run);
      if (!runActive(run.status) && run.artifactId) await loadCandidate(run.artifactId);
      return runActive(run.status);
    }, (failure) => { if (lifecycle.alive) setError(`暂时无法刷新分镜任务，仍会继续观察：${errorText(failure)}`); }, 1800);
  }, [activeRun, detail.episode.id, lifecycle, loadCandidate, upsertRun]);

  const perform = async (build: (snapshot: DraftSnapshot<StoryboardWorkingDraft>) => ProductionCommand, recovering = false) => coordinator.runExclusive(async (snapshot) => {
    setError(null);
    setNotice(null);
    const command = build(snapshot);
    saveLocalDraft(commandStorage, command);
    setPendingCommand(command);
    try {
      const response = await executeProductionCommand(detail.episode.id, command, recovering);
      let replacementDraft: DraftSnapshot<StoryboardWorkingDraft> | undefined;
      if (response.kind === "storyboard-run") {
        if (lifecycle.alive) {
          upsertRun(response.data);
          setNotice("分镜任务已受理。离开页面只会停止观察，不会取消任务或改变工作稿。");
        }
        if (response.data.artifactId) await loadCandidate(response.data.artifactId);
      } else if (response.kind === "storyboard-adopt") {
        const adoptedDraft = response.data;
        replacementDraft = { document: storyboardDraftFromResponse(adoptedDraft), revision: adoptedDraft.revision };
        if (lifecycle.alive) {
          setServerDraft(adoptedDraft);
          setSelectedAiShotIds([]);
          setNotice("候选已采用到分镜工作稿。请继续编辑并单独确认正式分镜。");
        }
        if (command.kind === "storyboard-adopt") await loadCandidate(command.artifactId);
      } else if (response.kind === "storyboard-prepare") {
        saveLocalDraft(confirmationStorage, response.data.artifactId);
        if (lifecycle.alive) setConfirmation(response.data);
      } else if (response.kind === "storyboard-approve") {
        const freshDraft = await getStoryboardDraft(detail.episode.id);
        replacementDraft = { document: storyboardDraftFromResponse(freshDraft), revision: freshDraft.revision };
        if (lifecycle.alive) {
          setServerDraft(freshDraft);
          setCurrentStoryboard(response.data);
          setVersionPage((current) => ({ ...current, versions: [response.data, ...current.versions.filter((item) => item.id !== response.data.id)] }));
          setConfirmation(null);
          setViewingStoryboard(response.data);
          setNotice(`已确认正式分镜 v${response.data.versionNo}。当前制作基线没有改变。`);
        }
        saveLocalDraft(confirmationStorage, null);
        await refreshEpisode();
      } else if (response.kind === "take-adoption") {
        if (lifecycle.alive) {
          setSelectedAdoptionIds((current) => ({ ...current, [response.data.targetShotVersionId]: response.data.id }));
          setNotice("素材采用决定已记录，并已加入待确认的制作版本组合。当前制作基线没有改变。");
        }
      } else {
        if (lifecycle.alive) {
          setCurrentBaseline(response.data);
          setViewingBaseline(response.data);
          setBaselinePage((current) => ({ ...current, baselines: [response.data, ...current.baselines.filter((item) => item.id !== response.data.id)] }));
          setBaselineReview(null);
          setSelectedAdoptionIds({});
          setSelectedKeyframes({});
          setNotice(`已确认制作基线 v${response.data.versionNo}；${response.data.shots.filter((shot) => shot.status === "pending").length} 镜待生产。`);
        }
        await refreshEpisode();
      }
      saveLocalDraft(commandStorage, null);
      if (lifecycle.alive) setPendingCommand(null);
      return { result: response, draft: replacementDraft };
    } catch (failure) {
      if (!commandResultIsUnknown(failure)) {
        saveLocalDraft(commandStorage, null);
        if (lifecycle.alive) setPendingCommand(null);
      }
      if (lifecycle.alive) setError(commandResultIsUnknown(failure) ? "操作结果尚未确认。已保留原请求，请核对后继续，不会创建第二次命令。" : errorText(failure));
      throw failure;
    }
  });

  const action = (operation: Promise<unknown>) => { void operation.catch((failure) => { if (lifecycle.alive) setError(errorText(failure)); }); };
  const changeProductionStage = (stage: "storyboard" | "render" | "post") => action(flushEpisodeSaves(detail.episode.novelId).then(() => setProductionStage(stage)));
  const prepareConfirmation = () => action(perform((snapshot) => ({ kind: "storyboard-prepare", body: { clientRequestId: requestId(), expectedDraftRevision: snapshot.revision, expectedEpisodeRevision: detail.episode.revision } })));
  const approveConfirmation = () => {
    if (!confirmation) return;
    action(perform(() => ({ kind: "storyboard-approve", artifactId: confirmation.artifactId, body: { clientRequestId: requestId(), expectedArtifactRevision: confirmation.artifactRevision, expectedDraftRevision: confirmation.draftRevision, expectedEpisodeRevision: confirmation.episodeRevision, confirmationHash: confirmation.confirmationHash } })));
  };
  const createBaseline = () => {
    if (!baselineReview) return;
    action(perform(() => ({ kind: "baseline-create", body: { clientRequestId: requestId(), expectedEpisodeRevision: detail.episode.revision, expectedProductionRevision: detail.episode.productionRevision, basedOnBaselineId: detail.episode.currentProductionBaselineId, scriptVersionId: baselineReview.scriptVersionId, storyboardVersionId: baselineReview.id, shotAdoptions: baselineAdoptionInputs(baselineReview, selectedAdoptionIds), keyframes: productionKeyframeInputs(baselineReview, selectedKeyframes) } })));
  };
  const createTakeAdoption = async (candidate: TakeCandidate, comparison: CreateTakeAdoptionRequest["comparison"]): Promise<TakeAdoption> => {
    const response = await perform(() => ({ kind: "take-adoption", body: {
      clientRequestId: requestId(),
      expectedProductionRevision: detail.episode.productionRevision,
      targetShotVersionId: comparison.targetShotVersionId,
      sourceTakeId: candidate.id,
      sourceBaselineId: candidate.sourceBaselineId,
      comparison,
    } }));
    if (response.kind !== "take-adoption") throw new Error("素材采用命令返回了错误的结果类型");
    return response.data;
  };
  const selectTakeAdoption = (shotVersionId: string, adoptionId: string | null) => setSelectedAdoptionIds((current) => {
    if (adoptionId) return { ...current, [shotVersionId]: adoptionId };
    const next = { ...current };
    delete next[shotVersionId];
    return next;
  });
  const selectKeyframe = (shotVersionId: string, role: ProductionKeyframeRole, assetId: string | null) => setSelectedKeyframes((current) => {
    const shot = { ...(current[shotVersionId] ?? {}) };
    if (assetId) shot[role] = assetId;
    else delete shot[role];
    if (Object.keys(shot).length) return { ...current, [shotVersionId]: shot };
    const next = { ...current };
    delete next[shotVersionId];
    return next;
  });
  const stableAiShotIds = selectedAiShotIds.filter((id) => (working.document.shots ?? []).some((shot) => shot.id === id));
  const startStoryboardRun = () => {
    if (!working.scriptVersionId || !instruction.trim() || activeRun) return;
    action(perform((snapshot) => ({ kind: "storyboard-run", body: {
      clientRequestId: requestId(),
      expectedDraftRevision: snapshot.revision,
      scriptVersionId: snapshot.document.scriptVersionId ?? "",
      operation: stableAiShotIds.length ? "episode_storyboard_revise" : "episode_storyboard_generate",
      selectedShotIds: stableAiShotIds,
      instruction: instruction.trim(),
    } })));
  };
  const adoptCandidate = (candidate: StoryboardCandidate) => action(perform((snapshot) => ({
    kind: "storyboard-adopt",
    artifactId: candidate.artifactId,
    body: { clientRequestId: requestId(), expectedArtifactRevision: candidate.revision, expectedDraftRevision: snapshot.revision },
  })));
  const cancelRun = async () => {
    const cancellation = pendingCancellation ?? (activeRun ? { runId: activeRun.runId, clientRequestId: requestId() } : null);
    if (!cancellation || cancelling) return;
    setCancelling(true);
    setError(null);
    setPendingCancellation(cancellation);
    saveLocalDraft(cancellationStorage, cancellation);
    try {
      await cancelScriptRun(cancellation);
      saveLocalDraft(cancellationStorage, null);
      setPendingCancellation(null);
      upsertRun(await getStoryboardRun(detail.episode.id, cancellation.runId));
      setNotice("已提交取消请求。任务将按权威状态收敛，已经完成的候选不会被删除。");
    } catch (failure) {
      if (!commandResultIsUnknown(failure)) { saveLocalDraft(cancellationStorage, null); setPendingCancellation(null); }
      setError(commandResultIsUnknown(failure) ? "取消结果尚未确认。原请求已经保留，不会创建第二次取消。" : errorText(failure));
    } finally { setCancelling(false); }
  };
  const compareRemote = () => action(getStoryboardDraft(detail.episode.id).then(setRemoteDraft));
  const selectScriptVersion = (versionId: string) => {
    if (!versionId || versionId === working.scriptVersionId) return;
    if ((working.document.shots?.length ?? 0) > 0 && !window.confirm("切换正式剧本依据会保留当前镜头和稳定身份；不再存在的场次绑定必须由你逐镜处理。继续吗？")) return;
    setError(null);
    coordinator.schedule({ ...working, scriptVersionId: versionId });
  };

  const showVersion = (versionId: string) => action(coordinator.flush().then(() => getStoryboardVersion(detail.episode.id, versionId)).then((version) => { setViewingStoryboard(version); setSelectedShotId(null); }));
  const showBaseline = (baselineId: string) => action(getProductionBaseline(detail.episode.id, baselineId).then(setViewingBaseline));
  const loadMoreVersions = () => {
    if (!versionPage.nextBeforeVersionNo || loadingMore) return;
    setLoadingMore(true);
    void listStoryboardVersions(detail.episode.id, versionPage.nextBeforeVersionNo).then((page) => setVersionPage((current) => ({ versions: [...current.versions, ...page.versions.filter((item) => !current.versions.some((old) => old.id === item.id))], nextBeforeVersionNo: page.nextBeforeVersionNo }))).catch((failure) => setError(errorText(failure))).finally(() => setLoadingMore(false));
  };
  const loadMoreBaselines = () => {
    if (!baselinePage.nextBeforeVersionNo || loadingMore) return;
    setLoadingMore(true);
    void listProductionBaselines(detail.episode.id, baselinePage.nextBeforeVersionNo).then((page) => setBaselinePage((current) => ({ baselines: [...current.baselines, ...page.baselines.filter((item) => !current.baselines.some((old) => old.id === item.id))], nextBeforeVersionNo: page.nextBeforeVersionNo }))).catch((failure) => setError(errorText(failure))).finally(() => setLoadingMore(false));
  };
  const loadMoreRuns = () => {
    if (!runPage.nextBeforeRunId || loadingMore) return;
    setLoadingMore(true);
    void listStoryboardRuns(detail.episode.id, runPage.nextBeforeRunId).then((page) => setRunPage((current) => ({ runs: [...current.runs, ...page.runs.filter((item) => !current.runs.some((old) => old.runId === item.runId))], nextBeforeRunId: page.nextBeforeRunId }))).catch((failure) => setError(errorText(failure))).finally(() => setLoadingMore(false));
  };

  return <div className="episode-production-workspace">
    <section className="episode-production-capability"><div><strong>制作能力</strong><span>{initial.capability.provider} · {initial.capability.model}</span></div><span className={`status ${initial.capability.executionMode === "simulated" ? "warning" : "danger"}`}>{initial.capability.executionMode === "simulated" ? "隔离模拟" : "真实执行"}</span><small>{initial.capability.allowedDurationSeconds.join(" / ")} 秒 · {initial.capability.allowedResolution} · {initial.capability.allowedOutputFormat} · 最多 {initial.capability.maxImageReferences} 张参考</small></section>
    <section className="episode-baseline-combination" aria-label="当前版本组合"><span>当前正式剧本<strong>{detail.currentScriptVersion ? `v${detail.currentScriptVersion.versionNo}` : "无"}</strong></span><span>当前正式分镜<strong>{currentStoryboard ? `v${currentStoryboard.versionNo}` : "无"}</strong><small>{currentStoryboard ? `依据剧本 ${scriptVersionLabel(detail.scriptVersions, currentStoryboard.scriptVersionId)}` : ""}</small></span><span>当前制作<strong>{currentBaseline ? `v${currentBaseline.versionNo}` : "无"}</strong><small>{currentBaseline ? `分镜 ${storyboardVersionLabel(versionPage, currentBaseline.storyboardVersionId)}` : ""}</small></span><span>当前交付<strong>{detail.episode.latestDeliveryVersionId ? "已有" : "无"}</strong></span></section>
    <nav className="episode-production-stage-nav" aria-label="本集制作阶段"><button className={productionStage === "storyboard" ? "active" : ""} type="button" onClick={() => changeProductionStage("storyboard")}>分镜与版本</button><button className={productionStage === "render" ? "active" : ""} type="button" disabled={!selectedProductionBaseline} onClick={() => changeProductionStage("render")}>逐镜生产</button><button className={productionStage === "post" ? "active" : ""} type="button" disabled={!selectedProductionBaseline} onClick={() => changeProductionStage("post")}>粗剪、声音与交付</button>{productionStage !== "storyboard" && baselinePage.baselines.length ? <label>工作基线<select className="select" value={selectedProductionBaseline?.id ?? ""} onChange={(event) => action(flushEpisodeSaves(detail.episode.novelId).then(() => getProductionBaseline(detail.episode.id, event.target.value)).then(setViewingBaseline))}>{baselinePage.baselines.map((baseline) => <option value={baseline.id} key={baseline.id}>制作 v{baseline.versionNo}{baseline.id === detail.episode.currentProductionBaselineId ? " · 当前" : ""}</option>)}</select></label> : null}</nav>
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}{notice ? <p className="notice" role="status">{notice}</p> : null}
    {pendingCommand ? <div className="notice"><p>有一条制作命令结果尚未确认，原请求已保留。</p><button className="button" type="button" disabled={coordinator.commandBusy} onClick={() => action(perform(() => pendingCommand, true))}>按原请求核对结果</button></div> : null}
    {pendingCancellation ? <div className="notice"><p>分镜任务取消结果尚未确认，原请求已保留。</p><button className="button" type="button" disabled={cancelling} onClick={() => void cancelRun()}>按原请求核对取消</button></div> : null}
    {productionStage === "storyboard" ? <><div className="episode-production-toolbar"><label>分镜依据<select className="select" disabled={locked} value={working.scriptVersionId ?? ""} onChange={(event) => selectScriptVersion(event.target.value)}><option value="">选择本集正式剧本</option>{detail.scriptVersions.map((version) => <option key={version.id} value={version.id}>正式剧本 v{version.versionNo}{version.id === detail.episode.currentScriptVersionId ? " · 当前" : ""}</option>)}</select></label><div className="episode-inline-actions"><button className={`button ${viewingStoryboard ? "ghost" : "primary"}`} type="button" onClick={() => setViewingStoryboard(null)}>分镜工作稿</button>{currentStoryboard ? <button className={`button ${viewingStoryboard?.id === currentStoryboard.id ? "primary" : "ghost"}`} type="button" onClick={() => action(flushEpisodeSaves(detail.episode.novelId).then(() => setViewingStoryboard(currentStoryboard)))}>当前正式 v{currentStoryboard.versionNo}</button> : null}</div></div>
    <div className="episode-production-main-grid"><main>
      <div className="episode-save-bar" role="status"><strong>{viewingStoryboard ? `正在查看正式分镜 v${viewingStoryboard.versionNo}（只读）` : { saved: "分镜工作稿已保存", waiting: "分镜工作稿待保存…", saving: "正在保存分镜工作稿…", failed: "分镜保存结果待核对", conflict: "分镜工作稿存在版本冲突" }[coordinator.state]}</strong>{!viewingStoryboard && coordinator.state === "failed" ? <button className="button" type="button" onClick={() => action(coordinator.retry())}>核对并重试保存</button> : null}{!viewingStoryboard && coordinator.state === "conflict" ? <button className="button" type="button" onClick={compareRemote}>比较远端工作稿</button> : null}</div>
      {remoteDraft ? <section className="episode-storyboard-conflict notice"><h4>远端分镜工作稿 r{remoteDraft.revision}</h4><StoryboardPreview document={remoteDraft.document} scriptVersion={detail.scriptVersions.find((version) => version.id === remoteDraft.scriptVersionId) ?? null} /><p>本地镜头与输入仍保留。只有你的明确选择会改变下一次保存依据。</p><div className="episode-inline-actions"><button className="button" type="button" onClick={() => { coordinator.resolveConflict({ document: storyboardDraftFromResponse(remoteDraft), revision: remoteDraft.revision }, true); setServerDraft(remoteDraft); setRemoteDraft(null); }}>保留本地稿，基于远端 revision 继续</button><button className="button ghost" type="button" onClick={() => { if (window.confirm("丢弃本地未保存分镜，采用远端工作稿？")) { coordinator.resolveConflict({ document: storyboardDraftFromResponse(remoteDraft), revision: remoteDraft.revision }, false); setServerDraft(remoteDraft); setRemoteDraft(null); } }}>采用远端稿</button></div></section> : null}
      {viewingStoryboard ? <><StoryboardPreview document={viewingStoryboard.document} scriptVersion={detail.scriptVersions.find((version) => version.id === viewingStoryboard.scriptVersionId) ?? null} /><div className="episode-inline-actions"><button className="button primary" type="button" disabled={!writable || Boolean(pendingCommand)} onClick={() => setBaselineReview(viewingStoryboard)}>以这组版本确认制作基线</button><button className="button ghost" type="button" onClick={() => setViewingStoryboard(null)}>返回工作稿</button></div></> : <>
        <EpisodeStoryboard document={working.document} scriptVersion={scriptVersion} canons={canons} capability={initial.capability} targetAspectRatio={targetAspectRatio} selectedShotId={selectedShotId} disabled={locked} onSelectedShotId={setSelectedShotId} onChange={(document) => { setError(null); coordinator.schedule({ ...working, document }); }} />
        <section className="episode-storyboard-ai"><header><div><h3>AI 起草与局部返工</h3><p>任务只产生候选，不会自动改写工作稿或确认正式分镜。</p></div>{activeRun ? <span className="status warning">{activeRun.status}</span> : null}</header><label>本次要求<textarea className="textarea" rows={3} maxLength={8000} disabled={locked || Boolean(activeRun)} value={instruction} placeholder="例如：按雨夜交信场设计 6 个镜头，突出林岚迟疑后收回信" onChange={(event) => setInstruction(event.target.value)} /></label>{(working.document.shots ?? []).some((shot) => shot.id) ? <fieldset><legend>局部返工范围（不选则起草完整候选）</legend>{(working.document.shots ?? []).flatMap((shot, index) => shot.id ? [<label key={shot.id}><input type="checkbox" disabled={locked || Boolean(activeRun)} checked={stableAiShotIds.includes(shot.id)} onChange={(event) => setSelectedAiShotIds((current) => event.target.checked ? [...current, shot.id!] : current.filter((id) => id !== shot.id))} />镜头 {index + 1} · {shot.title}</label>] : [])}</fieldset> : null}<p className="muted">{stableAiShotIds.length ? `只允许候选修改选中的 ${stableAiShotIds.length} 个稳定镜头。` : "完整起草仍保留当前工作稿，采用前必须人工审阅。"}</p>{!canons.some((canon) => canon.currentVersionId) ? <p className="notice notice-warning">AI 分镜需要至少一个已确认的视觉定妆版本。</p> : null}<div className="episode-inline-actions"><button className="button" type="button" disabled={locked || Boolean(activeRun) || !working.scriptVersionId || !instruction.trim() || !canons.some((canon) => canon.currentVersionId)} onClick={startStoryboardRun}>{activeRun ? "AI 正在处理…" : stableAiShotIds.length ? "返工选中镜头" : "起草完整分镜候选"}</button>{activeRun ? <button className="button ghost" type="button" disabled={cancelling || Boolean(pendingCancellation)} onClick={() => void cancelRun()}>{cancelling ? "正在取消…" : "取消任务"}</button> : null}</div>{activeRun ? <p className="muted">离开页面只停止观察；只有明确点击取消才会请求任务收敛。</p> : null}</section>
        <StoryboardCandidateReview candidates={candidates} scriptVersions={detail.scriptVersions} draftRevision={coordinator.revision} scriptVersionId={working.scriptVersionId} baseStoryboardVersionId={working.baseStoryboardVersionId} busy={coordinator.busy || coordinator.dirty || Boolean(pendingCommand)} enabled={writable && !activeRun && !pendingCancellation} onAdopt={adoptCandidate} />
        <section className="episode-storyboard-confirm-bar"><div><strong>人工确认分镜</strong><p>先保存当前工作稿，再冻结正式分镜。确认新版不会切换现有制作基线。</p></div><button className="button primary" type="button" disabled={locked || !(working.document.shots?.length) || !working.scriptVersionId} onClick={prepareConfirmation}>准备确认正式分镜</button></section>
      </>}
    </main><aside className="episode-production-context">
      <section className="episode-production-side-card"><header><strong>正式分镜版本</strong><span>{versionPage.versions.length} 项已加载</span></header><div className="episode-production-version-list">{versionPage.versions.map((version) => <button type="button" className={version.id === detail.episode.currentStoryboardVersionId ? "current" : ""} key={version.id} onClick={() => showVersion(version.id)}><span>v{version.versionNo}</span><div><strong>{version.shotCount} 镜</strong><small>剧本 {scriptVersionLabel(detail.scriptVersions, version.scriptVersionId)}</small></div></button>)}</div>{versionPage.nextBeforeVersionNo ? <button className="button ghost sm" type="button" disabled={loadingMore} onClick={loadMoreVersions}>{loadingMore ? "读取中…" : "加载更早版本"}</button> : null}</section>
      <section className="episode-production-side-card"><header><strong>制作基线</strong><span>{currentBaseline ? `当前 v${currentBaseline.versionNo}` : "尚无"}</span></header><div className="episode-production-version-list">{baselinePage.baselines.map((baseline) => <button type="button" className={baseline.id === detail.episode.currentProductionBaselineId ? "current" : ""} key={baseline.id} onClick={() => showBaseline(baseline.id)}><span>v{baseline.versionNo}</span><div><strong>{baseline.shotCount} 镜</strong><small>剧本 {scriptVersionLabel(detail.scriptVersions, baseline.scriptVersionId)} · 分镜 {storyboardVersionLabel(versionPage, baseline.storyboardVersionId)}</small></div></button>)}</div>{baselinePage.nextBeforeVersionNo ? <button className="button ghost sm" type="button" disabled={loadingMore} onClick={loadMoreBaselines}>{loadingMore ? "读取中…" : "加载更早基线"}</button> : null}</section>
      <section className="episode-production-side-card"><header><strong>分镜任务</strong><span>{runPage.runs.length} 项已加载</span></header><div className="episode-production-run-list">{runPage.runs.map((run) => <article key={run.runId}><div><strong>{run.status}</strong><small>{new Date(run.createdAt).toLocaleString("zh-CN")}</small></div>{run.errorMessage ? <p className="notice notice-danger">{run.errorMessage}</p> : null}{run.artifactId ? <button className="button ghost sm" type="button" onClick={() => action(loadCandidate(run.artifactId!))}>查看候选</button> : null}</article>)}</div>{runPage.nextBeforeRunId ? <button className="button ghost sm" type="button" disabled={loadingMore} onClick={loadMoreRuns}>{loadingMore ? "读取中…" : "加载更早任务"}</button> : null}</section>
      <ProductionBaselineAdoptionStatus baseline={viewingBaseline} />
      <ImpactReviewPanel episodeId={detail.episode.id} projectId={detail.episode.projectId} novelId={detail.episode.novelId} enabled={writable} />
      <section className="episode-production-side-card"><header><strong>工作稿依据</strong><span>r{serverDraft.revision}</span></header><p>{working.baseStoryboardVersionId ? `基于正式分镜 ${working.baseStoryboardVersionId}` : "尚未基于正式分镜"}</p><p>{scriptVersion ? `绑定正式剧本 v${scriptVersion.versionNo}` : "尚未选择正式剧本"}</p></section>
    </aside></div></> : productionStage === "render" && selectedProductionBaseline ? <EpisodeRenderWorkspace key={selectedProductionBaseline.id} episodeId={detail.episode.id} baseline={selectedProductionBaseline} capability={initial.capability} enabled={writable} onOpenAdoptionReview={() => action(getStoryboardVersion(detail.episode.id, selectedProductionBaseline.storyboardVersionId).then(setBaselineReview))} /> : productionStage === "post" && selectedProductionBaseline ? <EpisodePostProductionWorkspace key={selectedProductionBaseline.id} novelId={detail.episode.novelId} projectId={detail.episode.projectId} episodeId={detail.episode.id} baseline={selectedProductionBaseline} enabled={writable} onDeliveryChanged={refreshEpisode} /> : <section className="episode-empty"><h3>先确认制作基线</h3><p>逐镜生成和后期必须绑定不可变的剧本、分镜与生成输入。</p><button className="button" type="button" onClick={() => changeProductionStage("storyboard")}>返回分镜与版本</button></section>}
    {confirmation ? <WorkspaceDialog open title="确认正式分镜" variant="review" closeDisabled={coordinator.commandBusy} onClose={() => { saveLocalDraft(confirmationStorage, null); setConfirmation(null); }}><div className="episode-confirmation-inner"><p>工作稿 r{confirmation.draftRevision} · 剧本 {scriptVersionLabel(detail.scriptVersions, confirmation.scriptVersionId)} · {confirmation.document.shots?.length ?? 0} 镜。批准后创建不可变版本，现有制作不变。</p><div className="episode-confirmation-content"><StoryboardPreview document={confirmation.document} scriptVersion={detail.scriptVersions.find((version) => version.id === confirmation.scriptVersionId) ?? null} /></div><div className="episode-inline-actions"><button className="button primary" type="button" disabled={coordinator.commandBusy || Boolean(pendingCommand)} onClick={approveConfirmation}>批准正式分镜</button><button className="button ghost" type="button" disabled={coordinator.commandBusy || Boolean(pendingCommand)} onClick={() => { saveLocalDraft(confirmationStorage, null); setConfirmation(null); }}>返回继续修改</button></div></div></WorkspaceDialog> : null}
    {baselineReview ? <WorkspaceDialog open title="确认制作版本组合" variant="review" closeDisabled={coordinator.commandBusy} onClose={() => setBaselineReview(null)}><ProductionBaselineReview key={baselineReview.id} episodeId={detail.episode.id} storyboard={baselineReview} scriptVersion={detail.scriptVersions.find((version) => version.id === baselineReview.scriptVersionId) ?? null} currentBaseline={currentBaseline} capability={initial.capability} canons={canons} busy={coordinator.commandBusy || Boolean(pendingCommand)} enabled={writable} selectedAdoptionIds={selectedAdoptionIds} selectedKeyframes={selectedKeyframes} onCreateAdoption={createTakeAdoption} onSelectAdoption={selectTakeAdoption} onSelectKeyframe={selectKeyframe} onConfirm={createBaseline} /></WorkspaceDialog> : null}
  </div>;
}

function scriptVersionLabel(versions: ScriptVersion[], id: string): string {
  const version = versions.find((item) => item.id === id);
  return version ? `v${version.versionNo}` : id;
}

function storyboardVersionLabel(page: StoryboardVersionList, id: string): string {
  const version = page.versions.find((item) => item.id === id);
  return version ? `v${version.versionNo}` : id;
}

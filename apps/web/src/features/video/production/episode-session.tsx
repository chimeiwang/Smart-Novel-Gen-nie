"use client";

import { useCallback, useEffect, useReducer, useState } from "react";
import { browserApi } from "@/lib/api/browser";
import { ApiResponseError, requireApiData } from "@/lib/api/response";
import { startTaskPolling } from "../adaptation/task-polling";
import { EpisodeSourcePanel } from "./episode-source-panel";
import { EpisodeScriptEditor } from "./episode-script-editor";
import { ScriptCandidateReview } from "./script-candidate-review";
import { EpisodeDependencyPanel } from "./episode-dependency-panel";
import { EpisodeVersionContext } from "./episode-version-context";
import { EpisodeProductionSurface } from "./episode-production-surface";
import { EpisodeSessionContext } from "./episode-request-scope";
import { WorkspaceDialog } from "@/features/workspace/workspace-dialog";
import { ScriptPreview } from "./script-preview";
import { flushEpisodeSaves, registerEpisodeSave } from "./episode-save-navigation";
import { ScriptDraftCoordinator, type DraftSnapshot } from "./script-draft-coordinator";
import { cancelScriptRun, commandResultIsUnknown, executeEpisodeCommand, getEpisode, loadLocalDraft, loadPendingEpisodeCommand, loadPendingRunCancellation, loadPendingScriptDraft, saveLocalDraft, saveScriptDraft, type EpisodeCommand, type PendingRunCancellation } from "./episode-api";
import type { Character, Episode, EpisodeDetail, ScriptConfirmation, ScriptDocument, ScriptVersion } from "./types";
import type { EpisodeWorksurface } from "@/features/workspace/workspace-view";

const requestId = () => crypto.randomUUID();
const errorText = (failure: unknown) => failure instanceof Error ? failure.message : "操作失败，请重试";
const runActive = (status?: string) => Boolean(status && !["succeeded", "completed", "failed", "cancelled", "canceled"].includes(status));

export function EpisodeSession({ initial, episodes, characters, enabled, targetAspectRatio, surface, onSurfaceChange, onEpisodeChanged }: { initial: EpisodeDetail; episodes: Episode[]; characters: Character[]; enabled: boolean; targetAspectRatio: string; surface: EpisodeWorksurface; onSurfaceChange: (surface: EpisodeWorksurface) => void; onEpisodeChanged: (episode: Episode) => void }) {
  const [detail, setDetail] = useState(initial);
  const [session] = useState(() => new EpisodeSessionContext(initial));
  useEffect(() => { session.update(detail); }, [detail, session]);
  const [, notify] = useReducer((value: number) => value + 1, 0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [titleDraft, setTitle] = useState<string | null>(null);
  const title = titleDraft ?? detail.episode.title;
  const [instruction, setInstruction] = useState("");
  const [selectedScenes, setSelectedScenes] = useState<string[]>([]);
  const [viewingVersion, setViewingVersion] = useState<ScriptVersion | null>(null);
  const [confirmation, setConfirmation] = useState<ScriptConfirmation | null>(null);
  const [remoteDraft, setRemoteDraft] = useState<EpisodeDetail["scriptDraft"] | null>(null);
  const commandStorage = `inkforge:episode-command:${initial.episode.id}`;
  const cancellationStorage = `inkforge:episode-run-cancellation:${initial.episode.id}`;
  const confirmationStorage = `inkforge:episode-confirmation:${initial.episode.id}`;
  const draftStorage = `inkforge:episode-draft:${initial.episode.id}`;
  const [pendingCommand, setPendingCommand] = useState<EpisodeCommand | null>(() => loadPendingEpisodeCommand(commandStorage));
  const [pendingCancellation, setPendingCancellation] = useState<PendingRunCancellation | null>(() => loadPendingRunCancellation(cancellationStorage));
  const [cancelling, setCancelling] = useState(false);
  const [coordinator] = useState(() => {
    const attempted = new Set<string>();
    const restored = loadPendingScriptDraft(draftStorage);
    if (restored?.pending) attempted.add(restored.pending.clientRequestId);
    return new ScriptDraftCoordinator<ScriptDocument>({ initial: { document: initial.scriptDraft.document, revision: initial.scriptDraft.revision }, restored, requestId, onChange: notify, persist: (draft) => saveLocalDraft(draftStorage, draft), save: async (write) => {
      if (!enabled) throw new ApiResponseError(403, "VIDEO_DISABLED", "当前环境未开放视频写入", null, undefined);
      const recovering = attempted.has(write.clientRequestId);
      attempted.add(write.clientRequestId);
      const metadataKey = `${draftStorage}:${write.clientRequestId}`;
      const baseline = loadLocalDraft<Pick<EpisodeDetail["scriptDraft"], "sourceSetVersionId" | "baseScriptVersionId">>(metadataKey) ?? { sourceSetVersionId: session.detail.scriptDraft.sourceSetVersionId, baseScriptVersionId: session.detail.scriptDraft.baseScriptVersionId };
      saveLocalDraft(metadataKey, baseline);
      const result = await saveScriptDraft(initial.episode.id, baseline, write, recovering);
      saveLocalDraft(metadataKey, null);
      if (session.alive) setDetail((current) => result.draft.revision >= current.scriptDraft.revision ? { ...current, scriptDraft: result.draft } : current);
      return result;
    } });
  });
  const document = coordinator.document;
  const busy = coordinator.commandBusy;
  const locked = !enabled || busy || cancelling || Boolean(pendingCommand) || Boolean(pendingCancellation) || Boolean(viewingVersion) || Boolean(confirmation);
  const latestRun = detail.latestScriptRun;
  const currentSource = detail.sourceSets.find((set) => set.id === detail.episode.currentSourceSetVersionId) ?? null;
  const displaySource = viewingVersion ? detail.sourceSets.find((set) => set.id === viewingVersion.sourceSetVersionId) ?? null : currentSource;
  const episodeRevision = () => Math.max(session.detail.episode.revision, episodes.find((episode) => episode.id === initial.episode.id)?.revision ?? 0);
  const currentDisplay = { ...detail, scriptDraft: { ...detail.scriptDraft, revision: coordinator.revision } };

  const refresh = useCallback(async () => {
    const result = await getEpisode(initial.episode.id);
    if (!session.alive) return result;
    setDetail(result);
    onEpisodeChanged(result.episode);
    return result;
  }, [initial.episode.id, onEpisodeChanged, session]);

  useEffect(() => {
    session.activate();
    coordinator.activate();
    const unregister = registerEpisodeSave({ novelId: initial.episode.novelId, episodeId: initial.episode.id, pending: () => coordinator.dirty || coordinator.busy || Boolean(loadPendingEpisodeCommand(commandStorage)), flush: async () => {
      if (coordinator.commandBusy || loadPendingEpisodeCommand(commandStorage)) throw new Error("本集命令尚未确认完成，请先核对操作结果");
      await coordinator.flush();
    } });
    const preparedId = loadLocalDraft<string>(confirmationStorage);
    if (preparedId) void browserApi.GET("/api/v1/video/episodes/{episode_id}/script/confirmations/{artifact_id}", { params: { path: { episode_id: initial.episode.id, artifact_id: preparedId } } }).then(requireApiData).then((result) => { if (session.alive) setConfirmation(result); }).catch((failure) => { if (session.alive) setError(errorText(failure)); });
    return () => { session.dispose(); coordinator.dispose(); unregister(); };
  }, [initial.episode.novelId, initial.episode.id, commandStorage, confirmationStorage, coordinator, session]);

  useEffect(() => {
    if (!runActive(latestRun?.status)) return;
    return startTaskPolling(async (signal) => {
      const result = await getEpisode(initial.episode.id, signal);
      if (signal.aborted || !session.alive) return false;
      setDetail(result);
      onEpisodeChanged(result.episode);
      return runActive(result.latestScriptRun?.status);
    }, (failure) => { if (session.alive) setError(`暂时无法刷新 AI 任务，仍在继续观察：${errorText(failure)}`); }, 1800);
  }, [initial.episode.id, latestRun?.runId, latestRun?.status, onEpisodeChanged, session]);

  useEffect(() => registerEpisodeSave({ novelId: initial.episode.novelId, episodeId: initial.episode.id, pending: () => title.trim() !== detail.episode.title, flush: async () => { if (title.trim() !== detail.episode.title) throw new Error("分集标题尚未保存，请先保存标题"); } }), [initial.episode.novelId, initial.episode.id, title, detail.episode.title]);

  useEffect(() => registerEpisodeSave({ novelId: initial.episode.novelId, episodeId: initial.episode.id, pending: () => Boolean(pendingCommand), flush: async () => { if (pendingCommand) throw new Error("本集命令尚未核对，请先恢复原操作"); } }), [initial.episode.novelId, initial.episode.id, pendingCommand]);

  const perform = async (build: (snapshot: DraftSnapshot<ScriptDocument>) => EpisodeCommand, recovering = false) => {
    setError(null);
    setNotice(null);
    return coordinator.runExclusive(async (snapshot) => {
      const command = build(snapshot);
      saveLocalDraft(commandStorage, command);
      setPendingCommand(command);
      try {
        const response = await executeEpisodeCommand(initial.episode.id, command, recovering);
        if (response.kind === "prepare") { saveLocalDraft(confirmationStorage, response.data.artifactId); if (session.alive) setConfirmation(response.data); }
        if (response.kind === "approve") { saveLocalDraft(confirmationStorage, null); if (session.alive) { setConfirmation(null); setNotice(`已确认正式剧本 v${response.data.versionNo}。已有制作和成片保留原版本。`); } }
        const next = await refresh();
        if (response.kind === "rename" && session.alive) setTitle(null);
        saveLocalDraft(commandStorage, null);
        if (session.alive) setPendingCommand(null);
        return { result: response, draft: { document: next.scriptDraft.document, revision: next.scriptDraft.revision } };
      } catch (failure) {
        if (!commandResultIsUnknown(failure)) { saveLocalDraft(commandStorage, null); if (session.alive) setPendingCommand(null); }
        if (session.alive) setError(commandResultIsUnknown(failure) ? "操作结果尚未确认。请核对并重试原命令，不会创建第二次请求。" : errorText(failure));
        throw failure;
      }
    });
  };
  const action = (operation: Promise<unknown>) => { void operation.catch((failure) => { if (session.alive) setError(errorText(failure)); }); };
  const edit = (next: ScriptDocument) => { setError(null); setSelectedScenes((ids) => ids.filter((id) => (next.scenes ?? []).some((scene) => scene.id === id))); coordinator.schedule(next); };
  const refreshCurrent = () => action(refresh().then((remote) => { if (!coordinator.busy && !coordinator.dirty) coordinator.resolveConflict({ document: remote.scriptDraft.document, revision: remote.scriptDraft.revision }, false); else if (remote.scriptDraft.revision !== coordinator.revision) setNotice("远端工作稿已有变化。本地输入保持不变，保存时会核对版本。"); }));
  const prepareConfirmation = () => action(perform((snapshot) => ({ kind: "prepare", body: { clientRequestId: requestId(), expectedDraftRevision: snapshot.revision, expectedEpisodeRevision: episodeRevision() } })));
  const cancelRun = async () => {
    const cancellation = pendingCancellation ?? (latestRun && runActive(latestRun.status) ? { runId: latestRun.runId, clientRequestId: requestId() } : null);
    if (!cancellation || cancelling) return;
    setCancelling(true);
    setError(null);
    setNotice(null);
    setPendingCancellation(cancellation);
    saveLocalDraft(cancellationStorage, cancellation);
    try {
      await cancelScriptRun(cancellation);
      saveLocalDraft(cancellationStorage, null);
      setPendingCancellation(null);
      await refresh();
      setNotice("已提交取消请求，任务将按权威状态收敛；不会删除已经完成的候选。");
    } catch (failure) {
      if (!commandResultIsUnknown(failure)) {
        saveLocalDraft(cancellationStorage, null);
        setPendingCancellation(null);
      }
      setError(commandResultIsUnknown(failure) ? "取消结果尚未确认。已保留原请求，可继续核对，不会创建第二次取消。" : errorText(failure));
    } finally {
      setCancelling(false);
    }
  };

  return <div className="episode-session">
    <header className="episode-session-header"><div><span className="muted">独立分集</span><h2>{detail.episode.title}</h2></div><div className="episode-inline-actions"><button className="button ghost" type="button" disabled={busy || Boolean(pendingCommand)} onClick={refreshCurrent}>刷新本集状态</button><button className={`button ${surface === "script" ? "primary" : "ghost"}`} type="button" onClick={() => onSurfaceChange("script")}>剧本</button><button className={`button ${surface === "production" ? "primary" : "ghost"}`} type="button" onClick={() => onSurfaceChange("production")}>分镜与制作</button></div></header>
    <EpisodeVersionContext detail={currentDisplay} viewingVersion={viewingVersion} onView={(version) => action(flushEpisodeSaves(detail.episode.novelId).then(() => setViewingVersion(version)))} />
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}{notice ? <p className="notice" role="status">{notice}</p> : null}
    {pendingCommand ? <div className="notice">有一条操作尚未核对，已保留原请求。<button className="button" type="button" disabled={busy} onClick={() => action(perform(() => pendingCommand, true))}>核对并重试</button></div> : null}
    {pendingCancellation ? <div className="notice">取消结果尚未核对，已保留原请求。<button className="button" type="button" disabled={cancelling} onClick={() => void cancelRun()}>核对并重试取消</button></div> : null}
    {surface === "production" ? (detail.currentScriptVersion ? <EpisodeProductionSurface detail={detail} enabled={enabled} targetAspectRatio={targetAspectRatio} onEpisodeChanged={(next) => { setDetail(next); onEpisodeChanged(next.episode); }} /> : <section className="episode-empty"><h3>先确认本集剧本</h3><p>完成取材与剧本，确认作者认可的正式版本后，再按场次制作分镜。</p><button className="button" type="button" onClick={() => onSurfaceChange("script")}>返回本集剧本</button></section>) : <>
      <div className="episode-toolbar"><label>分集标题<input className="input" value={title} maxLength={240} disabled={locked} onChange={(event) => setTitle(event.target.value)} /></label><button className="button ghost" type="button" disabled={locked || !title.trim() || title.trim() === detail.episode.title} onClick={() => action(perform(() => ({ kind: "rename", body: { clientRequestId: requestId(), expectedRevision: episodeRevision(), title: title.trim() } })))}>保存标题</button></div>
      <div className="episode-working-grid"><main className="episode-script-main"><div className="episode-save-bar" role="status"><strong>{viewingVersion ? `正在查看正式剧本 v${viewingVersion.versionNo}（只读）` : { saved: "工作稿已保存", waiting: "工作稿待保存…", saving: "正在保存工作稿…", failed: "保存结果待核对", conflict: "工作稿存在版本冲突" }[coordinator.state]}</strong>{!viewingVersion && coordinator.state === "failed" ? <button className="button" type="button" onClick={() => action(coordinator.retry())}>核对并重试保存</button> : null}{!viewingVersion && coordinator.state === "conflict" ? <button className="button" type="button" onClick={() => action(getEpisode(detail.episode.id).then((remote) => setRemoteDraft(remote.scriptDraft)))}>比较远端工作稿</button> : null}</div>
      {remoteDraft ? <section className="notice"><h4>远端工作稿 r{remoteDraft.revision}</h4><div className="episode-conflict-text"><ScriptPreview document={remoteDraft.document} characters={characters} /></div><p>本地输入仍保留。选择后才会改变保存依据。</p><button className="button" type="button" onClick={() => { coordinator.resolveConflict({ document: remoteDraft.document, revision: remoteDraft.revision }, true); setDetail((current) => ({ ...current, scriptDraft: remoteDraft })); setRemoteDraft(null); }}>保留本地稿，基于远端版本继续保存</button><button className="button ghost" type="button" onClick={() => { if (window.confirm("丢弃本地未保存修改并采用远端工作稿？")) { coordinator.resolveConflict({ document: remoteDraft.document, revision: remoteDraft.revision }, false); setDetail((current) => ({ ...current, scriptDraft: remoteDraft })); setRemoteDraft(null); } }}>采用远端稿</button></section> : null}
      <EpisodeScriptEditor document={viewingVersion?.document ?? document} characters={characters} disabled={locked} selectedSceneIds={selectedScenes} onSelectedSceneIds={setSelectedScenes} onChange={edit} />
      {!viewingVersion ? <section className="episode-ai-actions"><h3>用 AI 起草或返工</h3><label>本次要求<textarea className="textarea" rows={3} value={instruction} maxLength={8000} disabled={locked || runActive(latestRun?.status)} placeholder="例如：只改选中的送信场，让林岚因不信任顾舟收回信，其他场次保持不变" onChange={(event) => setInstruction(event.target.value)} /></label><p className="muted">{selectedScenes.length ? `只修订勾选的 ${selectedScenes.length} 场。其他场次保持原稿。` : "起草完整候选；已有工作稿不会自动被替换。"}</p><div className="episode-inline-actions"><button className="button" type="button" disabled={locked || runActive(latestRun?.status) || !instruction.trim() || !detail.scriptDraft.sourceSetVersionId} onClick={() => action(perform((snapshot) => ({ kind: "run", body: { clientRequestId: requestId(), expectedDraftRevision: snapshot.revision, operation: selectedScenes.length ? "episode_script_revise" : "episode_script_generate", selectedSceneIds: selectedScenes, instruction: instruction.trim() } })))}>{runActive(latestRun?.status) ? "AI 正在处理…" : selectedScenes.length ? "修订选中场次" : "起草本集剧本"}</button>{runActive(latestRun?.status) ? <button className="button ghost" type="button" disabled={cancelling || Boolean(pendingCancellation)} onClick={() => void cancelRun()}>{cancelling ? "正在取消…" : "取消任务"}</button> : null}<button className="button primary" type="button" disabled={locked || !(document.scenes?.length)} onClick={prepareConfirmation}>确认正式剧本</button></div>{latestRun ? <p className="muted">最近任务：{latestRun.status}{latestRun.errorMessage ? ` · ${latestRun.errorMessage}` : ""}。离开页面只停止观察；只有点击“取消任务”才会请求取消。</p> : null}</section> : null}
      <ScriptCandidateReview candidates={detail.candidateArtifacts} draftRevision={coordinator.revision} busy={busy || coordinator.dirty} enabled={enabled && !pendingCommand && !viewingVersion && !confirmation} onAdopt={(candidate) => action(perform((snapshot) => ({ kind: "adopt", artifactId: candidate.artifactId, body: { clientRequestId: requestId(), expectedArtifactRevision: candidate.revision, expectedDraftRevision: snapshot.revision } })))} />
      </main><aside className="episode-context-panel"><EpisodeSourcePanel key={`${detail.episode.id}:${displaySource?.id ?? "empty"}`} novelId={detail.episode.novelId} episodeId={detail.episode.id} sourceSet={displaySource} disabled={locked} onSave={async (sources) => { await perform(() => ({ kind: "sources", body: { clientRequestId: requestId(), expectedRevision: episodeRevision(), basedOnVersionId: session.detail.episode.currentSourceSetVersionId, sources } })); }} />
      {!viewingVersion && currentSource && currentSource.id !== detail.scriptDraft.sourceSetVersionId ? <section className="notice"><p>当前工作稿尚未使用来源 v{currentSource.versionNo}。采用新版来源不会重写剧本文字；旧原文锚点需要重新核对。</p><button className="button" type="button" disabled={locked} onClick={() => { if (!window.confirm("将这份取材用于工作稿，并清除不再对应新快照的旧原文锚点？剧本文字和历史版本会保留。")) return; action(perform((snapshot) => ({ kind: "bind-sources", body: { clientRequestId: requestId(), expectedRevision: snapshot.revision, sourceSetVersionId: currentSource.id, baseScriptVersionId: session.detail.scriptDraft.baseScriptVersionId, document: { ...snapshot.document, scenes: (snapshot.document.scenes ?? []).map((scene) => ({ ...scene, lines: (scene.lines ?? []).map((line) => ({ ...line, sourceRefs: [] })) })) } } }))); }}>将这份来源用于本稿</button></section> : null}
      <EpisodeDependencyPanel episodeId={detail.episode.id} episodes={episodes} document={viewingVersion?.document ?? document} disabled={locked} onChange={edit} /></aside></div>
    </>}
    {confirmation ? <WorkspaceDialog open title="确认正式剧本" variant="review" closeDisabled={busy || Boolean(pendingCommand)} onClose={() => { saveLocalDraft(confirmationStorage, null); setConfirmation(null); }}><div className="episode-confirmation-inner"><h3>确认这份剧本成为正式版本</h3><p>工作稿 r{confirmation.draftRevision} · {confirmation.document.scenes?.length ?? 0} 场。确认不会切换制作基线，也不会覆盖旧成片。</p><div className="episode-confirmation-content"><ScriptPreview document={confirmation.document} characters={characters} /></div><div className="episode-inline-actions"><button className="button primary" type="button" disabled={busy || Boolean(pendingCommand)} onClick={() => action(perform(() => ({ kind: "approve", artifactId: confirmation.artifactId, body: { clientRequestId: requestId(), expectedArtifactRevision: confirmation.artifactRevision, expectedDraftRevision: confirmation.draftRevision, expectedEpisodeRevision: confirmation.episodeRevision, confirmationHash: confirmation.confirmationHash } })))}>批准正式版本</button><button className="button ghost" type="button" disabled={busy || Boolean(pendingCommand)} onClick={() => { saveLocalDraft(confirmationStorage, null); setConfirmation(null); }}>返回继续修改</button></div></div></WorkspaceDialog> : null}
  </div>;
}

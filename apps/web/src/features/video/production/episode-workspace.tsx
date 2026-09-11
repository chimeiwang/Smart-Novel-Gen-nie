"use client";

import type { components } from "@inkforge/api-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import { createSeriesProject, loadVideoProjectContext, type VideoProjectContext } from "../adaptation/video-project-context";
import type { EpisodeRouteContext } from "@/features/workspace/workspace-view";
import { EpisodeList } from "./episode-list";
import { EpisodeSession } from "./episode-session";
import { EpisodeRequestScope } from "./episode-request-scope";
import { flushEpisodeSaves, registerEpisodeSave } from "./episode-save-navigation";
import { commandResultIsUnknown, executeProjectCommand, getEpisode, getEpisodes, loadLocalDraft, loadPendingProjectCommand, saveLocalDraft, type ProjectCommand } from "./episode-api";
import type { Episode, EpisodeDetail, EpisodeListResponse } from "./types";
import "./episode-production.css";

export type EpisodeWorkspaceProps = { novelId: string; novelName: string; episodeContext: EpisodeRouteContext; onEpisodeNavigate: (context: EpisodeRouteContext) => Promise<void> };

export function EpisodeWorkspace({ novelId, novelName, episodeContext, onEpisodeNavigate }: EpisodeWorkspaceProps) {
  const [context, setContext] = useState<VideoProjectContext | null>(null);
  const [list, setList] = useState<EpisodeListResponse | null>(null);
  const [detail, setDetail] = useState<EpisodeDetail | null>(null);
  const [characters, setCharacters] = useState<components["schemas"]["CharacterResponse"][]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<ProjectCommand | null>(null);
  const projectCommandActive = useRef(false);
  const pendingProjectCommand = useRef<ProjectCommand | null>(null);
  const projectCreationKey = `inkforge:video-project-creation:${novelId}`;
  const [projectCreationUnknown, setProjectCreationUnknown] = useState(() => loadLocalDraft<boolean>(projectCreationKey) === true);
  const requestScope = useRef(new EpisodeRequestScope());
  const projects = context?.projects.filter((project) => project.mode === "series") ?? [];
  const project = episodeContext.projectId ? projects.find((item) => item.id === episodeContext.projectId) : projects[0];
  const projectId = project?.id ?? null;
  const currentId = episodeContext.episodeId;
  const enabled = Boolean(context?.previewEnabled);
  const storageKey = `inkforge:episode-project-command:${projectId ?? "none"}`;

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([loadVideoProjectContext(novelId), browserApi.GET("/api/v1/novels/{novel_id}/characters", { params: { path: { novel_id: novelId } }, signal: controller.signal }).then(requireApiData)]).then(([next, nextCharacters]) => { if (controller.signal.aborted) return; setContext(next); setCharacters(nextCharacters); }).catch((failure) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "读取剧集项目失败"); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [novelId]);

  useEffect(() => {
    if (!projectId) return;
    const controller = new AbortController();
    const scope = requestScope.current;
    const isCurrent = scope.next();
    void Promise.all([getEpisodes(projectId, controller.signal), currentId ? getEpisode(currentId, controller.signal) : Promise.resolve(null)]).then(([next, episode]) => {
      if (!isCurrent() || controller.signal.aborted) return;
      if (episode && episode.episode.projectId !== projectId) throw new Error("该集不属于当前项目，请从分集列表选择");
      setList(next);
      setDetail(episode);
      pendingProjectCommand.current = loadPendingProjectCommand(storageKey);
      setPending(pendingProjectCommand.current);
      setError(null);
    }).catch((failure) => { if (isCurrent() && !controller.signal.aborted) { setDetail(null); setError(failure instanceof Error ? failure.message : "读取分集失败"); } });
    return () => { controller.abort(); scope.dispose(); };
  }, [projectId, currentId, storageKey]);

  useEffect(() => registerEpisodeSave({ novelId, episodeId: "project", pending: () => projectCommandActive.current || Boolean(pendingProjectCommand.current), flush: async () => { if (projectCommandActive.current || pendingProjectCommand.current) throw new Error("分集操作结果尚未确认，请先核对"); } }), [novelId]);

  const episodeChanged = useCallback((episode: Episode) => {
    setList((current) => current ? { ...current, episodes: current.episodes.map((item) => item.id === episode.id ? episode : item) } : current);
  }, []);

  const navigate = async (next: EpisodeRouteContext) => {
    setError(null);
    try { await onEpisodeNavigate(next); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "当前稿尚未保存，未切换分集"); }
  };

  const projectCommand = async (command: ProjectCommand, recovering = false) => {
    if (!projectId || busy) return;
    await flushEpisodeSaves(novelId, "project");
    projectCommandActive.current = true;
    setBusy(true);
    setError(null);
    setPending(command);
    pendingProjectCommand.current = command;
    saveLocalDraft(storageKey, command);
    try {
      const result = await executeProjectCommand(projectId, command, recovering);
      const next = await getEpisodes(projectId);
      setList(next);
      setPending(null);
      pendingProjectCommand.current = null;
      saveLocalDraft(storageKey, null);
      if (result.kind === "create") {
        // 创建已经回读后才切换；结束项目命令的离开屏障，其他草稿仍由导航统一 flush。
        setBusy(false);
        projectCommandActive.current = false;
        await onEpisodeNavigate({ projectId, episodeId: result.data.id, surface: "script" });
      }
    } catch (failure) {
      if (!commandResultIsUnknown(failure)) { pendingProjectCommand.current = null; setPending(null); saveLocalDraft(storageKey, null); }
      setError(commandResultIsUnknown(failure) ? "分集操作结果待核对，请使用原请求继续核对，不要重复新建。" : failure instanceof Error ? failure.message : "分集操作失败");
      throw failure;
    } finally { projectCommandActive.current = false; setBusy(false); }
  };

  const createProject = async () => {
    projectCommandActive.current = true;
    setBusy(true);
    setError(null);
    try {
      const latest = await loadVideoProjectContext(novelId);
      setContext(latest);
      const existing = latest.projects.find((item) => item.mode === "series");
      if (existing) { setProjectCreationUnknown(false); saveLocalDraft(projectCreationKey, null); return; }
      if (projectCreationUnknown) { setError("尚未查到项目，请稍后继续核对。没有自动重复创建。"); return; }
      try {
        // 旧项目创建接口尚无幂等键，刷新后也只能先核对，不自动重复创建。
        saveLocalDraft(projectCreationKey, true);
        const created = await createSeriesProject(novelId, `${novelName} · 剧集制作`);
        saveLocalDraft(projectCreationKey, null);
        setContext({ ...latest, projects: [created, ...latest.projects] });
      } catch (failure) { if (commandResultIsUnknown(failure)) setProjectCreationUnknown(true); else saveLocalDraft(projectCreationKey, null); throw failure; }
    } catch (failure) { setError(failure instanceof Error ? failure.message : "创建视频项目失败"); }
    finally { projectCommandActive.current = false; setBusy(false); }
  };

  return <div className="episode-production"><header className="episode-project-header"><div><h1>剧集制作</h1><p className="muted">从小说取材，为每集写下独立剧本，再进入分镜。</p></div>{projects.length ? <label>系列项目<select className="select" value={projectId ?? ""} disabled={busy || Boolean(pending)} onChange={(event) => void navigate({ projectId: event.target.value, episodeId: null, surface: "script" })}>{!projectId ? <option value="">所选项目不可用</option> : null}{projects.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label> : null}</header>
    {!enabled && context ? <p className="notice">当前环境未开放视频写入，可查看已保存的剧集。</p> : null}
    {error ? <p className="notice notice-danger" role="alert">{error}</p> : null}
    {loading ? <p className="muted">正在读取剧集项目…</p> : !projectId ? <section className="episode-empty"><h2>{episodeContext.projectId ? "无法找到所选项目" : "先建立这部小说的系列项目"}</h2><p>每集可以选择不同章节、独立改编，角色定妆在系列内复用。</p>{!episodeContext.projectId ? <button className="button primary" type="button" disabled={!enabled || busy} onClick={() => void createProject()}>{projectCreationUnknown ? "核对项目创建结果" : "创建系列项目"}</button> : null}</section> : <>
      {pending ? <p className="notice">分集命令等待核对。<button className="button" type="button" disabled={busy} onClick={() => { void projectCommand(pending, true).catch(() => undefined); }}>核对并重试原命令</button></p> : null}
      <div className="episode-workspace-layout"><EpisodeList data={list?.projectId === projectId ? list : null} currentId={currentId} busy={busy || Boolean(pending)} enabled={enabled} onSelect={(episode) => void navigate({ projectId, episodeId: episode.id, surface: "script" })} onCreate={(title) => projectCommand({ kind: "create", body: { clientRequestId: crypto.randomUUID(), title, creativeIntent: "" } })} onMove={(episodeId, offset) => { if (!list) return; const ids = list.episodes.map((episode) => episode.id); const index = ids.indexOf(episodeId); if (index < 0 || !ids[index + offset]) return; [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]]; void projectCommand({ kind: "reorder", body: { clientRequestId: crypto.randomUUID(), expectedProjectRevision: list.projectRevision, episodeIds: ids } }).catch(() => undefined); }} />
      {detail?.episode.id === currentId && detail.episode.projectId === projectId ? <EpisodeSession key={detail.episode.id} initial={detail} episodes={list?.episodes ?? []} characters={characters} enabled={enabled} targetAspectRatio={project?.targetAspectRatio ?? "9:16"} surface={episodeContext.surface} onSurfaceChange={(surface) => void navigate({ projectId, episodeId: detail.episode.id, surface })} onEpisodeChanged={episodeChanged} /> : <section className="episode-empty"><h2>{currentId ? "正在读取所选分集" : list?.episodes.length ? "选择一集继续创作" : "制作第 1 集"}</h2><p>{currentId ? "读取完成后恢复本集来源、工作稿和正式版本。" : "先给这一集起个名字。然后从 2–3 个章节中取材，写出本集的冲突与结尾。"}</p></section>}</div>
    </>}
  </div>;
}

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiResponseError } from "@/lib/api/response";
import type { VisualCanon } from "./types";
import type { VisualSetting } from "./visual-canon-state";
import { SettingVisualEditor } from "./setting-visual-editor";
import { confirmVisualEditorLeave, useVisualEditorLeaveGuard } from "./visual-editor-leave-guard";
import {
  createSeriesProject,
  loadVideoProjectContext,
  loadVisualCanons,
  selectSeriesProject,
  subscribeVisualCanonChange,
  type VideoProjectContext,
} from "./video-project-context";

export function LoreVisualPanel({ novelId, novelName, setting }: { novelId: string; novelName: string; setting: VisualSetting }) {
  const [context, setContext] = useState<VideoProjectContext | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [canons, setCanons] = useState<VisualCanon[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [creationUncertain, setCreationUncertain] = useState(false);
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const readVersion = useRef(0);
  useVisualEditorLeaveGuard(novelId, false, creating);

  const reloadProjects = useCallback(async () => {
    const next = await loadVideoProjectContext(novelId);
    setContext(next);
    setProjectId((current) => selectSeriesProject(next.projects, current)?.id ?? null);
    if (selectSeriesProject(next.projects)) setCreationUncertain(false);
    return next;
  }, [novelId]);

  useEffect(() => {
    let cancelled = false;
    void loadVideoProjectContext(novelId).then((next) => {
      if (cancelled) return;
      setContext(next);
      setProjectId(selectSeriesProject(next.projects)?.id ?? null);
    }).catch((failure) => {
      if (!cancelled) setError(failure instanceof Error ? failure.message : "读取视频项目失败。");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; readVersion.current += 1; };
  }, [novelId]);

  const reloadCanons = useCallback(async () => {
    if (!projectId) return;
    const version = ++readVersion.current;
    setLibraryLoading(true);
    try {
      const result = await loadVisualCanons(projectId);
      if (version === readVersion.current) setCanons(result);
    } finally {
      if (version === readVersion.current) setLibraryLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    const refresh = () => {
      void reloadCanons().catch((failure) => setError(failure instanceof Error ? failure.message : "读取定妆版本失败。"));
    };
    const timer = window.setTimeout(refresh, 0);
    const unsubscribe = subscribeVisualCanonChange(projectId, refresh);
    window.addEventListener("focus", refresh);
    return () => { window.clearTimeout(timer); unsubscribe(); window.removeEventListener("focus", refresh); readVersion.current += 1; };
  }, [projectId, reloadCanons]);

  const createProject = async () => {
    if (creating || !context?.previewEnabled) return;
    setCreating(true);
    setError(null);
    let creationAttempted = false;
    try {
      // 项目创建没有幂等键。先回读，结果不确定时只做核对，不自动重发 POST。
      const latest = await reloadProjects();
      const existing = selectSeriesProject(latest.projects);
      if (existing) return;
      if (creationUncertain) {
        setError("暂未查到已创建的项目，请稍后再次核对。没有自动重复创建。");
        return;
      }
      creationAttempted = true;
      const created = await createSeriesProject(novelId, `${novelName} · 章节影视化`);
      setContext({ ...latest, projects: [created, ...latest.projects] });
      setProjectId(created.id);
    } catch (failure) {
      const uncertain = creationAttempted && (!(failure instanceof ApiResponseError) || failure.status >= 500);
      setCreationUncertain(uncertain);
      setError(uncertain ? "项目创建结果尚未确认，请核对已有项目后继续。" : failure instanceof Error ? failure.message : "读取视频项目失败，请重试。");
      if (uncertain) {
        try {
          const checked = await reloadProjects();
          if (selectSeriesProject(checked.projects)) setError(null);
        } catch { /* 保留结果未知状态，继续提供回读入口。 */ }
      }
    } finally {
      setCreating(false);
    }
  };

  const refresh = async () => {
    setError(null);
    try { await reloadProjects(); await reloadCanons(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "刷新视觉定妆失败。"); }
  };

  const projects = context?.projects.filter((project) => project.mode === "series") ?? [];
  return (
    <div className="setting-visual-context">
      <header className="setting-visual-project"><label>视频项目<select className="select" value={projectId ?? ""} disabled={loading || creating || !projects.length} onChange={(event) => {
        if (!confirmVisualEditorLeave(novelId, "visual")) return;
        readVersion.current += 1;
        setError(null);
        setCanons([]);
        setProjectId(event.target.value);
      }}><option value="" disabled>{loading ? "读取中…" : "尚未创建系列视频项目"}</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.title} · {project.targetAspectRatio}</option>)}</select></label><button className="button ghost sm" type="button" disabled={creating} onClick={() => void refresh()}>{libraryLoading ? "正在读取版本…" : "刷新状态"}</button></header>
      <p className="muted">同一个设定在不同视频项目中可使用不同定妆。这里的确认不会修改小说文字设定。</p>
      {error ? <div className="notice notice-danger" role="alert">{error}</div> : null}
      {!loading && !projectId ? <div className="setting-visual-empty"><strong>先建立视频项目，再保存定妆</strong><p>将创建 9:16、中文的系列项目。无需先分析章节或生成分镜。</p>{!context?.previewEnabled ? <p>当前环境未开放视频写入。</p> : <button className="button primary" type="button" disabled={creating} onClick={() => void createProject()}>{creating ? "正在核对项目…" : creationUncertain ? "核对创建结果" : "创建系列视频项目"}</button>}</div> : null}
      {projectId ? <SettingVisualEditor key={`${projectId}:${setting.kind}:${setting.id}`} novelId={novelId} projectId={projectId} setting={setting} canons={canons} enabled={Boolean(context?.previewEnabled)} onCanonChanged={(canon) => setCanons((current) => [...current.filter((item) => item.id !== canon.id), canon])} onReload={reloadCanons} /> : null}
    </div>
  );
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { requireApiData } from "@/lib/api/response";
import { VideoNavigation } from "./video-navigation";
import { VideoReadinessInspector } from "./video-readiness-inspector";
import { VideoStageCanvas } from "./video-stage-canvas";
import {
  readInitialVideoLocation,
  videoErrorMessage,
} from "./video-workspace-helpers";
import {
  nextVideoRefreshDelay,
  videoProjectRefreshSignature,
} from "./video-refresh-policy";
import {
  buildPreviewReadiness,
  buildVideoWorkspaceSearch,
  readVideoPlanAssets,
  type VideoStage,
} from "./video-workspace-state";
import type {
  AssetDuty,
  AssetModality,
  PromptPreview,
  VideoProject,
  VideoProjectDetail,
  VideoProjectList,
  VideoWorkspaceProps,
} from "./video-workspace-types";

export function VideoWorkspace({
  novelId,
  novelName,
  currentChapter,
}: VideoWorkspaceProps) {
  const initialLocation = readInitialVideoLocation();
  const [projects, setProjects] = useState<VideoProject[]>([]);
  const [capabilities, setCapabilities] = useState<Pick<
    VideoProjectList,
    "previewEnabled" | "seedanceConfigured" | "seedanceEnabled"
  >>({ previewEnabled: false, seedanceConfigured: false, seedanceEnabled: false });
  const [activeProjectId, setActiveProjectId] = useState<string | null>(initialLocation.projectId);
  const [detail, setDetail] = useState<VideoProjectDetail | null>(null);
  const [activeSceneId, setActiveSceneId] = useState<string | null>(initialLocation.sceneId);
  const [stage, setStage] = useState<VideoStage>(initialLocation.stage);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // 来源必须由作者主动选择，不再默认把整章全文送给模型。
  const [sceneTitle, setSceneTitle] = useState(
    currentChapter ? `${currentChapter.title} · 试制事件` : "试制事件",
  );
  const [sourceText, setSourceText] = useState("");
  const [selectionStartUtf16, setSelectionStartUtf16] = useState<number | null>(null);
  const [selectionEndUtf16, setSelectionEndUtf16] = useState<number | null>(null);
  const [selectionChapterVersion, setSelectionChapterVersion] = useState<string | null>(null);
  const [sceneClientRequestId, setSceneClientRequestId] = useState<string | null>(null);
  const [durationSeconds, setDurationSeconds] = useState(15);

  // 素材选择只属于本次开发预览，不伪装成正式 Canon 绑定。
  const [previewSelections, setPreviewSelections] = useState<Record<string, string>>({});
  const [promptPreview, setPromptPreview] = useState<PromptPreview | null>(null);
  const [assetName, setAssetName] = useState("");
  const [assetModality, setAssetModality] = useState<AssetModality>("image");
  const [assetDuty, setAssetDuty] = useState<AssetDuty>("identity");
  const [assetFile, setAssetFile] = useState<File | null>(null);
  const currentChapterVersion = currentChapter
    ? `${currentChapter.id}:${currentChapter.updatedAt}`
    : null;
  const selectionIsCurrent = currentChapterVersion !== null
    && selectionChapterVersion === currentChapterVersion;
  const selectedSourceText = selectionIsCurrent ? sourceText : "";
  const selectedStartUtf16 = selectionIsCurrent ? selectionStartUtf16 : null;
  const selectedEndUtf16 = selectionIsCurrent ? selectionEndUtf16 : null;

  const activeScene = useMemo(
    () => detail?.scenes.find((scene) => scene.id === activeSceneId) ?? detail?.scenes[0] ?? null,
    [activeSceneId, detail],
  );
  const formalAssets = useMemo(
    () => readVideoPlanAssets(activeScene?.plan),
    [activeScene?.plan],
  );
  const canonSlots = useMemo(
    () => formalAssets.filter((asset) => asset.bindingScope === "canon_slot"),
    [formalAssets],
  );
  const sceneReferences = useMemo(
    () => formalAssets.filter((asset) => asset.bindingScope === "scene_direct"),
    [formalAssets],
  );
  const readiness = useMemo(
    () => buildPreviewReadiness(formalAssets, previewSelections),
    [formalAssets, previewSelections],
  );
  const hasGeneratingScene = detail?.scenes.some(
    (scene) => scene.status === "generating",
  ) ?? false;
  const generationSignature = detail ? videoProjectRefreshSignature(detail) : "";

  // 项目详情是场景与素材的单一数据源，刷新后会尽量保留用户原先选择的场景。
  const loadProject = useCallback(async (projectId: string, preferredSceneId?: string | null) => {
    const result = requireApiData(await browserApi.GET(
      "/api/v1/video/projects/{project_id}",
      { params: { path: { project_id: projectId } } },
    ));
    setDetail(result);
    setActiveProjectId(projectId);
    setActiveSceneId((current) => {
      const requested = preferredSceneId ?? current;
      return requested && result.scenes.some((scene) => scene.id === requested)
        ? requested
        : result.scenes[0]?.id ?? null;
    });
    return result;
  }, []);

  const loadProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = requireApiData(await browserApi.GET(
        "/api/v1/video/novels/{novel_id}/projects",
        { params: { path: { novel_id: novelId } } },
      ));
      setProjects(result.projects);
      // 空项目时没有 detail；列表响应仍是能力门禁的权威来源。
      setCapabilities({
        previewEnabled: result.previewEnabled,
        seedanceConfigured: result.seedanceConfigured,
        seedanceEnabled: result.seedanceEnabled,
      });
      const selected = initialLocation.projectId && result.projects.some(
        (project) => project.id === initialLocation.projectId,
      ) ? initialLocation.projectId : result.projects[0]?.id;
      if (selected) await loadProject(selected, initialLocation.sceneId);
      else setDetail(null);
    } catch (loadError) {
      setError(videoErrorMessage(loadError, "加载长篇视频预览失败"));
    } finally {
      setLoading(false);
    }
  }, [initialLocation.projectId, initialLocation.sceneId, loadProject, novelId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadProjects(), 0);
    return () => window.clearTimeout(timer);
  }, [loadProjects]);

  useEffect(() => {
    // 当前切片没有视频 SSE；使用可取消、无重叠的退避刷新，页面隐藏时完全暂停。
    if (!hasGeneratingScene || !activeProjectId) return;
    let cancelled = false;
    let timer: number | null = null;
    let unchangedPolls = 0;
    let observedSignature = generationSignature;

    const clearTimer = () => {
      if (timer === null) return;
      window.clearTimeout(timer);
      timer = null;
    };
    const schedule = (delayMs: number) => {
      clearTimer();
      if (cancelled || document.visibilityState === "hidden") return;
      timer = window.setTimeout(() => void poll(), delayMs);
    };
    const poll = async () => {
      timer = null;
      if (cancelled || document.visibilityState === "hidden") return;
      let nextDelay: number | null = null;
      try {
        const result = await loadProject(activeProjectId, activeSceneId);
        const nextSignature = videoProjectRefreshSignature(result);
        unchangedPolls = nextSignature === observedSignature ? unchangedPolls + 1 : 0;
        observedSignature = nextSignature;
        if (result.scenes.some((scene) => scene.status === "generating")) {
          nextDelay = nextVideoRefreshDelay(unchangedPolls);
        }
      } catch (refreshError) {
        setError(videoErrorMessage(refreshError, "刷新视频生成状态失败"));
        nextDelay = nextVideoRefreshDelay(3);
      }
      if (nextDelay !== null) schedule(nextDelay);
    };
    const handleVisibilityChange = () => {
      clearTimer();
      if (document.visibilityState === "visible") schedule(0);
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    schedule(nextVideoRefreshDelay(0));
    return () => {
      cancelled = true;
      clearTimer();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [
    activeProjectId,
    activeSceneId,
    generationSignature,
    hasGeneratingScene,
    loadProject,
  ]);

  useEffect(() => {
    // 把当前项目、场景和阶段固化到地址，支持刷新后回到同一工作上下文。
    const search = buildVideoWorkspaceSearch({
      currentSearch: window.location.search,
      projectId: activeProjectId,
      sceneId: activeScene?.id ?? null,
      stage,
    });
    const next = `${window.location.pathname}?${search}`;
    window.history.replaceState(window.history.state, "", next);
  }, [activeProjectId, activeScene?.id, stage]);

  const createProject = async () => {
    setWorking("project");
    setError(null);
    try {
      const project = requireApiData(await browserApi.POST(
        "/api/v1/video/novels/{novel_id}/projects",
        {
          params: { path: { novel_id: novelId } },
          body: {
            title: `${novelName} · 长篇视频试制`,
            mode: "highlight",
            targetAspectRatio: "16:9",
            targetLanguage: "zh-CN",
          },
        },
      ));
      setProjects((current) => [project, ...current]);
      await loadProject(project.id);
      setStage("source");
    } catch (createError) {
      setError(videoErrorMessage(createError, "创建长篇视频预览项目失败"));
    } finally {
      setWorking(null);
    }
  };

  const createScene = async () => {
    if (
      !activeProjectId
      || !currentChapter
      || selectedStartUtf16 === null
      || selectedEndUtf16 === null
    ) return;
    const clientRequestId = sceneClientRequestId ?? createClientRequestId();
    if (sceneClientRequestId === null) setSceneClientRequestId(clientRequestId);
    setWorking("scene");
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/video/projects/{project_id}/scenes",
        {
          params: { path: { project_id: activeProjectId } },
          body: {
            clientRequestId,
            chapterId: currentChapter.id,
            title: sceneTitle,
            expectedChapterUpdatedAt: currentChapter.updatedAt,
            selectionStartUtf16: selectedStartUtf16,
            selectionEndUtf16: selectedEndUtf16,
            selectedText: selectedSourceText,
            durationSeconds,
          },
        },
      ));
      await loadProject(activeProjectId, result.scene.id);
      setActiveSceneId(result.scene.id);
      setPreviewSelections({});
      setPromptPreview(null);
      setSceneClientRequestId(null);
      setStage("foundation");
    } catch (createError) {
      setError(videoErrorMessage(createError, "生成场景地基失败"));
    } finally {
      setWorking(null);
    }
  };

  const approveScene = async (
    sceneId: string,
    expectedArtifactRevision: number,
    clientRequestId: string,
  ) => {
    if (!activeProjectId) return;
    setWorking(`approve:${sceneId}`);
    setError(null);
    try {
      requireApiData(await browserApi.POST(
        "/api/v1/video/scenes/{scene_id}/approve",
        {
          params: { path: { scene_id: sceneId } },
          body: { clientRequestId, expectedArtifactRevision },
        },
      ));
      await loadProject(activeProjectId, sceneId);
      setStage("settings");
    } catch (approveError) {
      setError(videoErrorMessage(approveError, "批准场景方案失败"));
    } finally {
      setWorking(null);
    }
  };

  const reviseScene = async (
    sceneId: string,
    expectedArtifactRevision: number,
    userMessage: string,
    clientRequestId: string,
  ) => {
    if (!activeProjectId) return;
    setWorking(`revise:${sceneId}`);
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/video/scenes/{scene_id}/revise",
        {
          params: { path: { scene_id: sceneId } },
          body: {
            clientRequestId,
            expectedArtifactRevision,
            userMessage,
          },
        },
      ));
      // 旧候选的素材选择与提示词预览不得流入新一轮导演方案。
      setPreviewSelections({});
      setPromptPreview(null);
      await loadProject(activeProjectId, result.scene.id);
      setActiveSceneId(result.scene.id);
      setStage("foundation");
    } catch (reviseError) {
      setError(videoErrorMessage(reviseError, "返工并重新生成场景失败"));
    } finally {
      setWorking(null);
    }
  };

  const retryScene = async (sceneId: string) => {
    if (!activeProjectId) return;
    setWorking(`retry:${sceneId}`);
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/video/scenes/{scene_id}/retry",
        { params: { path: { scene_id: sceneId } } },
      ));
      await loadProject(activeProjectId, result.scene.id);
      setActiveSceneId(result.scene.id);
      setPromptPreview(null);
      setStage("foundation");
    } catch (retryError) {
      setError(videoErrorMessage(retryError, "重新生成当前场景失败"));
    } finally {
      setWorking(null);
    }
  };

  const uploadAsset = async () => {
    if (!activeProjectId || !assetFile || !assetName.trim()) return;
    setWorking("asset-upload");
    setError(null);
    try {
      requireApiData(await browserApi.POST(
        "/api/v1/video/projects/{project_id}/assets",
        {
          params: { path: { project_id: activeProjectId } },
          body: {
            file: assetFile as unknown as string,
            name: assetName,
            modality: assetModality,
            duty: assetDuty,
            sourceKind: "user_upload",
          },
          bodySerializer: () => {
            const body = new FormData();
            body.append("file", assetFile);
            body.append("name", assetName);
            body.append("modality", assetModality);
            body.append("duty", assetDuty);
            body.append("sourceKind", "user_upload");
            return body;
          },
        },
      ));
      setAssetFile(null);
      setAssetName("");
      await loadProject(activeProjectId, activeScene?.id);
    } catch (uploadError) {
      setError(videoErrorMessage(uploadError, "上传素材失败"));
    } finally {
      setWorking(null);
    }
  };

  const confirmAsset = async (assetId: string) => {
    if (!activeProjectId) return;
    setWorking(`asset:${assetId}`);
    setError(null);
    try {
      requireApiData(await browserApi.PATCH(
        "/api/v1/video/assets/{asset_id}/rights",
        {
          params: { path: { asset_id: assetId } },
          body: { rightsStatus: "confirmed" },
        },
      ));
      await loadProject(activeProjectId, activeScene?.id);
    } catch (confirmError) {
      setError(videoErrorMessage(confirmError, "确认素材权利失败"));
    } finally {
      setWorking(null);
    }
  };

  const compilePromptPreview = async () => {
    if (!activeScene) return;
    setWorking("prompt-preview");
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/video/scenes/{scene_id}/prompt-preview",
        {
          params: { path: { scene_id: activeScene.id } },
          body: {
            previewBindings: Object.entries(previewSelections).map(([slotId, assetId]) => ({
              slotId,
              assetId,
            })),
          },
        },
      ));
      setPromptPreview(result);
      setStage("package");
    } catch (previewError) {
      setError(videoErrorMessage(previewError, "编译提示词预览失败"));
    } finally {
      setWorking(null);
    }
  };

  const selectProject = async (projectId: string) => {
    setPromptPreview(null);
    setPreviewSelections({});
    await loadProject(projectId);
    setStage("source");
  };

  const selectScene = (sceneId: string) => {
    setActiveSceneId(sceneId);
    setPromptPreview(null);
    setPreviewSelections({});
    setStage("foundation");
  };

  if (loading) return <div className="panel empty">正在加载长篇视频预览...</div>;

  return (
    <div className="video-workspace">
      <VideoNavigation
        projects={projects}
        activeProjectId={activeProjectId}
        scenes={detail?.scenes ?? []}
        activeSceneId={activeScene?.id ?? null}
        stage={stage}
        working={working}
        onCreateProject={() => void createProject()}
        onSelectProject={(projectId) => void selectProject(projectId)}
        onSelectScene={selectScene}
        onSelectStage={setStage}
      />

      <main className="panel video-stage-panel">
        <div className="panel-header">
          <div>
            <h2 className="title-md">{detail?.project.title ?? "长篇视频试制"}</h2>
            <div className="meta">
              <span className="badge">开发预览</span>
              <span className="badge">仅长篇</span>
              <span className="badge">Seedance 2.5 格式</span>
            </div>
          </div>
          <span className={`badge ${(detail?.previewEnabled ?? capabilities.previewEnabled) ? "badge-success" : "badge-warning"}`}>
            {(detail?.previewEnabled ?? capabilities.previewEnabled) ? "预览写入已开启" : "预览写入已关闭"}
          </span>
        </div>
        <div className="panel-body video-stage-body">
          {error ? <div className="notice notice-danger" role="alert">{error}</div> : null}
          {!detail ? (
            <div className="video-stage-empty">
              <h3>建立一个长篇视频试制项目</h3>
              <p>当前切片只验证单个 4～15 秒场景、设定槽位和提示词格式，不会提交真实视频。</p>
              <button className="button primary" type="button" onClick={() => void createProject()}>
                创建开发预览项目
              </button>
            </div>
          ) : (
            <VideoStageCanvas
              stage={stage}
              currentChapter={currentChapter}
              scene={activeScene}
              sceneTitle={sceneTitle}
              sourceText={selectedSourceText}
              selectionStartUtf16={selectedStartUtf16}
              selectionEndUtf16={selectedEndUtf16}
              durationSeconds={durationSeconds}
              working={working}
              assets={detail.assets}
              canonSlots={canonSlots}
              sceneReferences={sceneReferences}
              previewSelections={previewSelections}
              promptPreview={promptPreview}
              assetForm={{ assetName, assetModality, assetDuty, assetFile }}
              onSceneTitleChange={(value) => {
                setSceneTitle(value);
                setSceneClientRequestId(null);
              }}
              onSourceSelectionChange={(start, end, value) => {
                setSelectionStartUtf16(start);
                setSelectionEndUtf16(end);
                setSourceText(value);
                setSelectionChapterVersion(currentChapterVersion);
                setSceneClientRequestId(null);
              }}
              onDurationChange={(value) => {
                setDurationSeconds(value);
                setSceneClientRequestId(null);
              }}
              onCreateScene={() => void createScene()}
              onRetryScene={(sceneId) => void retryScene(sceneId)}
              onApproveScene={(sceneId, revision, clientRequestId) => {
                void approveScene(sceneId, revision, clientRequestId);
              }}
              onReviseScene={(sceneId, revision, userMessage, clientRequestId) => {
                void reviseScene(sceneId, revision, userMessage, clientRequestId);
              }}
              onSelectAsset={(slotId, assetId) => {
                setPromptPreview(null);
                setPreviewSelections((current) => ({ ...current, [slotId]: assetId }));
              }}
              onAssetNameChange={setAssetName}
              onAssetModalityChange={setAssetModality}
              onAssetDutyChange={setAssetDuty}
              onAssetFileChange={setAssetFile}
              onUploadAsset={() => void uploadAsset()}
              onConfirmAsset={(assetId) => void confirmAsset(assetId)}
              onCompilePreview={() => void compilePromptPreview()}
              onChangeStage={setStage}
            />
          )}
        </div>
      </main>

      <VideoReadinessInspector
        previewEnabled={detail?.previewEnabled ?? capabilities.previewEnabled}
        seedanceConfigured={detail?.seedanceConfigured ?? capabilities.seedanceConfigured}
        scene={activeScene}
        formalAssets={formalAssets}
        resolvedCount={readiness.resolvedSlotIds.length}
        missingCount={readiness.missingSlotIds.length}
        promptPreview={promptPreview}
        onNextStage={setStage}
      />
    </div>
  );
}

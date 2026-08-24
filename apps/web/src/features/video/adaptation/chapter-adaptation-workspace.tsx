"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { requireApiData } from "@/lib/api/response";
import {
  addShotAfter,
  bindShotSource,
  candidateSourceCoverage,
  cloneCandidate,
  deleteCandidateShot,
  durationMetrics,
  flattenCandidateShots,
  flattenFormalShots,
  localCoverageFindings,
  mergeShotWithNext,
  mergeSceneWithNext,
  restoreCandidateShot,
  updateCandidateShot,
  type DiscardedShot,
} from "./adaptation-state";
import { EpisodeEditor } from "./episode-editor";
import { FinishWorkspace } from "./finish-workspace";
import { KeyframeWorkspace } from "./keyframe-workspace";
import { PromptEditor } from "./prompt-editor";
import { RoughCutWorkspace } from "./rough-cut-workspace";
import { ShotInspector } from "./shot-inspector";
import { ShotPlanAudit } from "./shot-plan-audit";
import { ShotTimeline, type TimelineScene } from "./shot-timeline";
import { SourcePanel } from "./source-panel";
import { TakeWorkspace } from "./take-workspace";
import { VisualCanonPanel } from "./visual-canon-panel";
import type {
  AdaptationCandidate,
  ChapterAdaptation,
  ChapterAdaptationWorkspaceProps,
  CandidateShot,
  AudioTrackKind,
  EpisodeAudioClip,
  EpisodeEditClip,
  EpisodeSubtitleCue,
  FormalShot,
  KeyframeRole,
  PostProductionWorkspace,
  RenderWorkspace,
  SourceSelection,
  VisualCanon,
  VideoProject,
} from "./types";

type Stage = "review" | "episodes" | "visuals" | "prompts" | "keyframes" | "takes" | "edit" | "finish";
const ACTIVE_TASKS = new Set(["pending", "submitted", "processing"]);
const ACTIVE_RENDER_TASKS = new Set(["pending", "submitting", "queued", "running", "archiving"]);

export function ChapterAdaptationWorkspace({
  novelId,
  novelName,
  currentChapter,
  selectionBridge,
}: ChapterAdaptationWorkspaceProps) {
  const [projects, setProjects] = useState<VideoProject[]>([]);
  const [visualCanons, setVisualCanons] = useState<VisualCanon[]>([]);
  const [previewEnabled, setPreviewEnabled] = useState(false);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [adaptation, setAdaptation] = useState<ChapterAdaptation | null>(null);
  const [draftPlan, setDraftPlan] = useState<AdaptationCandidate | null>(null);
  const [discardedShots, setDiscardedShots] = useState<DiscardedShot[]>([]);
  const [selectedShotKey, setSelectedShotKey] = useState<string | null>(null);
  const [sourceSelection, setSourceSelection] = useState<SourceSelection | null>(null);
  const [episodeBreakIds, setEpisodeBreakIds] = useState<string[]>([]);
  const [stage, setStage] = useState<Stage>("review");
  const [pacingPreset, setPacingPreset] = useState<"short_drama" | "cinematic" | "dialogue_driven">("short_drama");
  const [targetEpisodeSeconds, setTargetEpisodeSeconds] = useState<60 | 90 | 120>(90);
  const [promptText, setPromptText] = useState("");
  const [renderWorkspace, setRenderWorkspace] = useState<RenderWorkspace | null>(null);
  const [postProductionWorkspace, setPostProductionWorkspace] = useState<PostProductionWorkspace | null>(null);
  const [renderDurationSeconds, setRenderDurationSeconds] = useState(5);
  const [renderResolution, setRenderResolution] = useState<"480p" | "720p" | "1080p">("720p");
  const [compareTakeIds, setCompareTakeIds] = useState<string[]>([]);
  const [revisionBrief, setRevisionBrief] = useState("");
  const [draftEdited, setDraftEdited] = useState(false);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const currentChapterId = currentChapter?.id;
  const currentChapterContent = currentChapter?.content;

  const replaceAdaptation = useCallback((next: ChapterAdaptation) => {
    setAdaptation(next);
    setDraftPlan(next.candidatePlan ? cloneCandidate(next.candidatePlan) : null);
    setDraftEdited(false);
    setEpisodeBreakIds(next.episodePlan?.breakAfterShotIds ?? []);
  }, []);

  const loadAdaptations = useCallback(async (projectId: string) => {
    const [adaptationsResponse, canonsResponse] = await Promise.all([
      browserApi.GET(
        "/api/v1/video/projects/{project_id}/chapter-adaptations",
        { params: { path: { project_id: projectId } } },
      ),
      browserApi.GET(
        "/api/v1/video/projects/{project_id}/visual-canons",
        { params: { path: { project_id: projectId } } },
      ),
    ]);
    const result = requireApiData(adaptationsResponse);
    setVisualCanons(requireApiData(canonsResponse).canons);
    const chapterAdaptations = currentChapterId
      ? result.adaptations.filter((item) => item.chapterId === currentChapterId)
      : [];
    const selected = chapterAdaptations.find((item) => item.sourceText === currentChapterContent)
      ?? chapterAdaptations[0]
      ?? null;
    setActiveProjectId(projectId);
    setPostProductionWorkspace(null);
    if (selected) {
      replaceAdaptation(selected);
      setStage(initialStage(selected));
    }
    else {
      setAdaptation(null);
      setDraftPlan(null);
      setEpisodeBreakIds([]);
      setStage("review");
    }
  }, [currentChapterContent, currentChapterId, replaceAdaptation]);

  const loadWorkspace = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = requireApiData(await browserApi.GET(
        "/api/v1/video/novels/{novel_id}/projects",
        { params: { path: { novel_id: novelId } } },
      ));
      setProjects(result.projects);
      setPreviewEnabled(result.previewEnabled);
      const project = result.projects.find((item) => item.mode === "series") ?? result.projects[0];
      if (project) await loadAdaptations(project.id);
      else {
        setActiveProjectId(null);
        setAdaptation(null);
        setVisualCanons([]);
      }
    } catch (loadError) {
      setError(errorMessage(loadError, "加载章节影视化工作台失败"));
    } finally {
      setLoading(false);
    }
  }, [loadAdaptations, novelId]);

  const loadRenderWorkspace = useCallback(async (adaptationId: string) => {
    const response = await browserApi.GET(
      "/api/v1/video/chapter-adaptations/{adaptation_id}/renders",
      { params: { path: { adaptation_id: adaptationId } } },
    );
    const result = requireApiData(response);
    setRenderWorkspace(result);
    return result;
  }, []);

  const loadPostProductionWorkspace = useCallback(async (adaptationId: string) => {
    const response = await browserApi.GET(
      "/api/v1/video/chapter-adaptations/{adaptation_id}/post-production",
      { params: { path: { adaptation_id: adaptationId } } },
    );
    const result = requireApiData(response);
    setPostProductionWorkspace(result);
    return result;
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadWorkspace(), 0);
    return () => window.clearTimeout(timer);
  }, [loadWorkspace]);

  const taskActive = Boolean(adaptation?.latestTask && ACTIVE_TASKS.has(adaptation.latestTask.status));
  const sourceChanged = Boolean(
    adaptation
    && currentChapter
    && adaptation.chapterId === currentChapter.id
    && adaptation.sourceText !== currentChapter.content,
  );
  useEffect(() => {
    if (!taskActive || !adaptation) return;
    const timer = window.setTimeout(() => {
      void browserApi.GET(
        "/api/v1/video/chapter-adaptations/{adaptation_id}",
        { params: { path: { adaptation_id: adaptation.id } } },
      ).then((response) => replaceAdaptation(requireApiData(response))).catch((pollError) => {
        setError(errorMessage(pollError, "刷新章节影视化任务失败"));
      });
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [adaptation, replaceAdaptation, taskActive]);

  useEffect(() => {
    if (stage !== "takes" || !adaptation?.currentPlan) return;
    const timer = window.setTimeout(() => {
      void loadRenderWorkspace(adaptation.id).catch((loadError) => {
        setError(errorMessage(loadError, "加载候选 Take 失败"));
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [adaptation?.currentPlan, adaptation?.id, loadRenderWorkspace, stage]);

  useEffect(() => {
    if (!adaptation?.currentPlan || !adaptation.episodePlan || !["keyframes", "edit", "finish"].includes(stage)) return;
    const timer = window.setTimeout(() => {
      void loadPostProductionWorkspace(adaptation.id).catch((loadError) => {
        setError(errorMessage(loadError, "加载后期制作工作区失败"));
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [adaptation?.currentPlan, adaptation?.episodePlan, adaptation?.id, loadPostProductionWorkspace, stage]);

  const exportTaskActive = Boolean(
    postProductionWorkspace?.episodes.some((episode) => (
      episode.exportTasks.some((task) => task.status === "pending" || task.status === "rendering")
    )),
  );
  useEffect(() => {
    if (stage !== "finish" || !adaptation || !exportTaskActive) return;
    const timer = window.setTimeout(() => {
      void loadPostProductionWorkspace(adaptation.id).catch((pollError) => {
        setError(errorMessage(pollError, "刷新整集导出任务失败"));
      });
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [adaptation, exportTaskActive, loadPostProductionWorkspace, stage]);

  const renderTaskActive = Boolean(
    renderWorkspace?.tasks.some((task) => ACTIVE_RENDER_TASKS.has(task.status)),
  );
  useEffect(() => {
    if (stage !== "takes" || !adaptation || !renderTaskActive) return;
    const timer = window.setTimeout(() => {
      void loadRenderWorkspace(adaptation.id).catch((pollError) => {
        setError(errorMessage(pollError, "刷新逐镜视频任务失败"));
      });
    }, 1800);
    return () => window.clearTimeout(timer);
  }, [adaptation, loadRenderWorkspace, renderTaskActive, stage]);

  const candidatePlan = draftPlan ?? adaptation?.candidatePlan ?? null;
  const formalPlan = adaptation?.currentPlan ?? null;
  const episodePlanReady = Boolean(adaptation?.episodePlan);
  const editable = Boolean(adaptation?.candidatePlan && candidatePlan);
  // 审镜只操作待审候选；分集、视觉设定和提示词必须始终固定到当前正式版本。
  const activePlan = stage === "review"
    ? candidatePlan ?? formalPlan
    : formalPlan ?? candidatePlan;
  const activePlanKind = stage === "review" && candidatePlan
    ? "candidate"
    : formalPlan
      ? "formal"
      : candidatePlan
        ? "candidate"
        : null;
  const timelineScenes = useMemo<TimelineScene[]>(() => (
    activePlan?.scenes ?? []
  ).map((scene) => ({
    sceneKey: scene.sceneKey,
    title: scene.title,
    locationLabel: scene.locationLabel,
    timeLabel: scene.timeLabel,
    objective: scene.objective,
    beats: scene.beats.map((beat) => ({
      beatKey: beat.beatKey,
      title: beat.title,
      dramaticTurn: beat.dramaticTurn,
      coverageGoals: beat.coverageGoals,
      shots: beat.shots,
    })),
  })), [activePlan]);
  const timelineShots = useMemo(() => timelineScenes.flatMap((scene) => scene.beats.flatMap((beat) => beat.shots)), [timelineScenes]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (!timelineShots.some((shot) => shot.shotKey === selectedShotKey)) {
        setSelectedShotKey(timelineShots[0]?.shotKey ?? null);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selectedShotKey, timelineShots]);

  const selectedLocation = findTimelineLocation(timelineScenes, selectedShotKey);
  const selectedFormalShot = formalPlan
    ? flattenFormalShots(formalPlan).find((shot) => shot.shotKey === selectedShotKey) ?? null
    : null;
  const selectedPromptCandidate = adaptation?.promptCandidates.find((item) => item.shotId === selectedFormalShot?.id) ?? null;
  const selectedPromptVersion = adaptation?.promptVersions.find((item) => item.shotId === selectedFormalShot?.id) ?? null;
  const currentVisualReferences = adaptation?.visualReferenceSets.find(
    (item) => item.shotId === selectedFormalShot?.id,
  )?.references ?? [];
  const liveCoverageFindings = useMemo(
    () => candidatePlan ? localCoverageFindings(candidatePlan) : [],
    [candidatePlan],
  );

  const applyDraftPlan = (next: AdaptationCandidate | null) => {
    if (!next) return;
    setDraftPlan(next);
    setDraftEdited(true);
  };

  useEffect(() => {
    const timer = window.setTimeout(() => setPromptText(
      selectedPromptCandidate?.compiledPrompt
      ?? selectedPromptVersion?.currentText
      ?? "",
    ), 0);
    return () => window.clearTimeout(timer);
  }, [selectedPromptCandidate?.compiledPrompt, selectedPromptVersion?.currentText, selectedFormalShot?.id]);

  useEffect(() => {
    if (!selectedFormalShot) return;
    // 生成时长是显式供应商参数；切镜时只给出最接近剪辑目标的 2–12 秒默认值。
    const nearestSupportedDuration = Math.max(
      2,
      Math.min(12, Math.round(selectedFormalShot.timelineDurationMs / 1000)),
    );
    const timer = window.setTimeout(() => {
      setRenderDurationSeconds(nearestSupportedDuration);
      setCompareTakeIds([]);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [selectedFormalShot]);

  const ensureProject = async (): Promise<string> => {
    if (activeProjectId) return activeProjectId;
    const existing = projects.find((item) => item.mode === "series") ?? projects[0];
    if (existing) return existing.id;
    const project = requireApiData(await browserApi.POST(
      "/api/v1/video/novels/{novel_id}/projects",
      {
        params: { path: { novel_id: novelId } },
        body: {
          title: `${novelName} · 章节影视化`,
          mode: "series",
          targetAspectRatio: "9:16",
          targetLanguage: "zh-CN",
        },
      },
    ));
    setProjects((current) => [project, ...current]);
    setActiveProjectId(project.id);
    setVisualCanons([]);
    return project.id;
  };

  const startPlan = async () => {
    if (!currentChapter) return setError("当前小说还没有可改编章节");
    setWorking("start-plan");
    setError(null);
    try {
      const projectId = await ensureProject();
      let current = adaptation;
      if (!current || current.chapterId !== currentChapter.id || current.sourceText !== currentChapter.content) {
        current = requireApiData(await browserApi.POST(
          "/api/v1/video/projects/{project_id}/chapter-adaptations",
          {
            params: { path: { project_id: projectId } },
            body: {
              clientRequestId: createClientRequestId(),
              chapterId: currentChapter.id,
              expectedChapterUpdatedAt: currentChapter.updatedAt,
            },
          },
        ));
      }
      const basePlan = current.id === adaptation?.id ? formalPlan : null;
      const accepted = requireApiData(await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan-runs",
        {
          params: { path: { adaptation_id: current.id } },
          body: {
            clientRequestId: createClientRequestId(),
            pacingPreset,
            targetEpisodeSeconds,
            baseShotPlanVersionId: basePlan?.planVersionId ?? null,
            revisionBrief: basePlan && revisionBrief.trim() ? revisionBrief.trim() : null,
          },
        },
      ));
      replaceAdaptation(accepted.adaptation);
      setStage("review");
    } catch (startError) {
      setError(errorMessage(startError, "启动电影化拆镜失败"));
    } finally {
      setWorking(null);
    }
  };

  const confirmPlan = async () => {
    if (!adaptation?.reviewArtifact || !draftPlan) return;
    setWorking("confirm");
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/shot-plan/confirm",
        {
          params: { path: { adaptation_id: adaptation.id } },
          body: {
            clientRequestId: createClientRequestId(),
            expectedArtifactRevision: adaptation.reviewArtifact.revision,
            expectedAdaptationRevision: adaptation.headRevision,
            plan: draftPlan,
          },
        },
      ));
      replaceAdaptation(result);
      setStage("episodes");
    } catch (confirmError) {
      setError(errorMessage(confirmError, "确认电影化镜头方案失败"));
    } finally {
      setWorking(null);
    }
  };

  const discardCandidate = async () => {
    if (!adaptation?.reviewArtifact) return;
    setWorking("discard");
    setError(null);
    try {
      const result = requireApiData(await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/candidate/discard",
        {
          params: { path: { adaptation_id: adaptation.id } },
          body: {
            clientRequestId: createClientRequestId(),
            expectedArtifactRevision: adaptation.reviewArtifact.revision,
            expectedAdaptationRevision: adaptation.headRevision,
          },
        },
      ));
      replaceAdaptation(result);
    } catch (discardError) {
      setError(errorMessage(discardError, "放弃待审镜头方案失败"));
    } finally {
      setWorking(null);
    }
  };

  const saveEpisodes = async () => {
    if (!adaptation || !formalPlan) return;
    setWorking("episodes");
    setError(null);
    try {
      const result = requireApiData(await browserApi.PUT(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/episode-plan",
        {
          params: { path: { adaptation_id: adaptation.id } },
          body: {
            clientRequestId: createClientRequestId(),
            expectedAdaptationRevision: adaptation.headRevision,
            shotPlanVersionId: formalPlan.planVersionId,
            breakAfterShotIds: episodeBreakIds,
          },
        },
      ));
      replaceAdaptation(result);
      setStage("visuals");
    } catch (saveError) {
      setError(errorMessage(saveError, "保存分集版本失败"));
    } finally {
      setWorking(null);
    }
  };

  const generatePrompts = async (shotIds: string[]) => {
    if (!adaptation || !formalPlan) return;
    setWorking(shotIds.length ? "prompt" : "prompt-all");
    setError(null);
    try {
      const accepted = requireApiData(await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/prompt-runs",
        {
          params: { path: { adaptation_id: adaptation.id } },
          body: {
            clientRequestId: createClientRequestId(),
            expectedAdaptationRevision: adaptation.headRevision,
            shotPlanVersionId: formalPlan.planVersionId,
            shotIds,
          },
        },
      ));
      replaceAdaptation(accepted.adaptation);
    } catch (promptError) {
      setError(errorMessage(promptError, "生成逐镜即梦提示词失败"));
    } finally {
      setWorking(null);
    }
  };

  const savePrompt = async () => {
    if (!adaptation || !selectedFormalShot || !promptText.trim()) return;
    setWorking("save-prompt");
    setError(null);
    try {
      const result = requireApiData(await browserApi.PUT(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/prompt",
        {
          params: { path: { adaptation_id: adaptation.id, shot_id: selectedFormalShot.id } },
          body: {
            expectedPromptRevision: selectedPromptVersion?.headRevision ?? 1,
            candidateTaskId: selectedPromptCandidate?.taskId ?? null,
            currentPrompt: promptText.trim(),
          },
        },
      ));
      replaceAdaptation(result);
    } catch (saveError) {
      setError(errorMessage(saveError, "保存正式提示词版本失败"));
    } finally {
      setWorking(null);
    }
  };

  const startRender = async () => {
    if (!adaptation || !selectedFormalShot || !selectedPromptVersion) return;
    setWorking("render-start");
    setError(null);
    try {
      await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/render-tasks",
        {
          params: {
            path: {
              adaptation_id: adaptation.id,
              shot_id: selectedFormalShot.id,
            },
          },
          body: {
            clientRequestId: createClientRequestId(),
            expectedPromptRevision: selectedPromptVersion.headRevision,
            durationSeconds: renderDurationSeconds,
            resolution: renderResolution,
            generateAudio: true,
            watermark: false,
          },
        },
      ).then(requireApiData);
      await loadRenderWorkspace(adaptation.id);
    } catch (renderError) {
      setError(errorMessage(renderError, "提交逐镜视频生成失败"));
    } finally {
      setWorking(null);
    }
  };

  const retryRender = async (taskId: string) => {
    if (!adaptation) return;
    setWorking(`render-retry:${taskId}`);
    setError(null);
    try {
      await browserApi.POST(
        "/api/v1/video/render-tasks/{task_id}/retry",
        {
          params: { path: { task_id: taskId } },
          body: { clientRequestId: createClientRequestId() },
        },
      ).then(requireApiData);
      await loadRenderWorkspace(adaptation.id);
    } catch (retryError) {
      setError(errorMessage(retryError, "重试逐镜视频生成失败"));
    } finally {
      setWorking(null);
    }
  };

  const confirmTake = async (takeId: string) => {
    if (!adaptation || !selectedFormalShot || !renderWorkspace) return;
    const head = renderWorkspace.takeHeads.find((item) => item.shotId === selectedFormalShot.id);
    if (!head) return;
    setWorking(`take-confirm:${takeId}`);
    setError(null);
    try {
      await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/takes/{take_id}/confirm",
        {
          params: {
            path: {
              adaptation_id: adaptation.id,
              shot_id: selectedFormalShot.id,
              take_id: takeId,
            },
          },
          body: {
            clientRequestId: createClientRequestId(),
            expectedTakeRevision: head.revision,
          },
        },
      ).then(requireApiData);
      await loadRenderWorkspace(adaptation.id);
    } catch (confirmError) {
      setError(errorMessage(confirmError, "确认当前 Take 失败"));
      await loadRenderWorkspace(adaptation.id).catch(() => undefined);
    } finally {
      setWorking(null);
    }
  };

  const uploadControlledAsset = async (
    file: File,
    modality: "image" | "audio",
    duty: "keyframe" | "voice" | "ambience" | "sfx" | "music",
    name: string,
  ) => {
    if (!activeProjectId) throw new Error("当前没有视频项目");
    const asset = requireApiData(await browserApi.POST(
      "/api/v1/video/projects/{project_id}/assets",
      {
        params: { path: { project_id: activeProjectId } },
        body: {
          file: file as unknown as string,
          name,
          modality,
          duty,
          sourceKind: "user_upload",
        },
        bodySerializer: () => {
          const body = new FormData();
          body.append("file", file);
          body.append("name", name);
          body.append("modality", modality);
          body.append("duty", duty);
          body.append("sourceKind", "user_upload");
          return body;
        },
      },
    ));
    requireApiData(await browserApi.PATCH(
      "/api/v1/video/assets/{asset_id}/rights",
      {
        params: { path: { asset_id: asset.id } },
        body: { rightsStatus: "confirmed" },
      },
    ));
    return asset;
  };

  const saveKeyframeVersion = async (
    role: KeyframeRole,
    assetId: string | null,
    sourceTakeId: string | null = null,
    sourceTimeMs: number | null = null,
  ) => {
    if (!adaptation || !selectedFormalShot || !postProductionWorkspace) return;
    const head = postProductionWorkspace.shots
      .find((shot) => shot.shotId === selectedFormalShot.id)
      ?.heads.find((item) => item.role === role);
    if (!head) return;
    requireApiData(await browserApi.POST(
      "/api/v1/video/chapter-adaptations/{adaptation_id}/shots/{shot_id}/keyframe-versions",
      {
        params: { path: { adaptation_id: adaptation.id, shot_id: selectedFormalShot.id } },
        body: {
          clientRequestId: createClientRequestId(),
          expectedRevision: head.revision,
          role,
          assetId,
          sourceTakeId,
          sourceTimeMs,
        },
      },
    ));
    await loadPostProductionWorkspace(adaptation.id);
  };

  const bindKeyframe = async (role: KeyframeRole, assetId: string | null) => {
    setWorking(`keyframe:${role}`);
    setError(null);
    try {
      await saveKeyframeVersion(role, assetId);
    } catch (saveError) {
      setError(errorMessage(saveError, "确认关键帧失败"));
    } finally {
      setWorking(null);
    }
  };

  const uploadKeyframe = async (role: KeyframeRole, file: File) => {
    if (!selectedFormalShot) return;
    setWorking(`keyframe-upload:${role}`);
    setError(null);
    try {
      const asset = await uploadControlledAsset(
        file,
        "image",
        "keyframe",
        `${selectedFormalShot.shotKey} · ${file.name}`,
      );
      await saveKeyframeVersion(role, asset.id);
    } catch (uploadError) {
      setError(errorMessage(uploadError, "上传并确认关键帧失败"));
    } finally {
      setWorking(null);
    }
  };

  const extractKeyframe = async (
    role: KeyframeRole,
    takeId: string,
    timestampMs: number,
  ) => {
    if (!selectedFormalShot) return;
    setWorking(`keyframe-extract:${role}`);
    setError(null);
    try {
      const asset = requireApiData(await browserApi.POST(
        "/api/v1/video/takes/{take_id}/frames",
        {
          params: { path: { take_id: takeId } },
          body: {
            clientRequestId: createClientRequestId(),
            timestampMs,
            name: `${selectedFormalShot.shotKey} · ${role} · ${(timestampMs / 1000).toFixed(1)}s`,
          },
        },
      ));
      await saveKeyframeVersion(role, asset.id, takeId, timestampMs);
    } catch (extractError) {
      setError(errorMessage(extractError, "从 Take 抽取关键帧失败"));
    } finally {
      setWorking(null);
    }
  };

  const loadEditVersion = async (versionId: string) => requireApiData(await browserApi.GET(
    "/api/v1/video/edit-versions/{version_id}",
    { params: { path: { version_id: versionId } } },
  ));

  const saveEditVersion = async (
    episodeNo: number,
    clips: EpisodeEditClip[],
    basedOnVersionId: string | null,
  ) => {
    if (!adaptation || !postProductionWorkspace) return;
    const episode = postProductionWorkspace.episodes.find((item) => item.episodeNo === episodeNo);
    if (!episode) return;
    setWorking("edit-save");
    setError(null);
    try {
      requireApiData(await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/edit-versions",
        {
          params: { path: { adaptation_id: adaptation.id, episode_no: episodeNo } },
          body: {
            clientRequestId: createClientRequestId(),
            expectedRevision: episode.editHead.revision,
            basedOnVersionId,
            clips,
          },
        },
      ));
      await loadPostProductionWorkspace(adaptation.id);
    } catch (saveError) {
      setError(errorMessage(saveError, "保存粗剪版本失败"));
    } finally {
      setWorking(null);
    }
  };

  const loadMixVersion = async (versionId: string) => requireApiData(await browserApi.GET(
    "/api/v1/video/mix-versions/{version_id}",
    { params: { path: { version_id: versionId } } },
  ));

  const saveMixVersion = async (
    episodeNo: number,
    editVersionId: string,
    audioClips: EpisodeAudioClip[],
    subtitleCues: EpisodeSubtitleCue[],
    basedOnVersionId: string | null,
  ) => {
    if (!adaptation || !postProductionWorkspace) return;
    const episode = postProductionWorkspace.episodes.find((item) => item.episodeNo === episodeNo);
    if (!episode) return;
    setWorking("mix-save");
    setError(null);
    try {
      requireApiData(await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/mix-versions",
        {
          params: { path: { adaptation_id: adaptation.id, episode_no: episodeNo } },
          body: {
            clientRequestId: createClientRequestId(),
            expectedRevision: episode.mixHead.revision,
            basedOnVersionId,
            editVersionId,
            audioClips,
            subtitleCues,
          },
        },
      ));
      await loadPostProductionWorkspace(adaptation.id);
    } catch (saveError) {
      setError(errorMessage(saveError, "保存声音字幕版本失败"));
    } finally {
      setWorking(null);
    }
  };

  const uploadAudio = async (trackKind: AudioTrackKind, file: File) => {
    if (!adaptation) return;
    setWorking(`audio-upload:${trackKind}`);
    setError(null);
    try {
      const duty = trackKind === "dialogue" || trackKind === "narration" ? "voice" : trackKind;
      await uploadControlledAsset(file, "audio", duty, `${trackKind} · ${file.name}`);
      await loadPostProductionWorkspace(adaptation.id);
    } catch (uploadError) {
      setError(errorMessage(uploadError, "上传音频素材失败"));
    } finally {
      setWorking(null);
    }
  };

  const startEpisodeExport = async (
    episodeNo: number,
    editVersionId: string,
    mixVersionId: string,
    resolution: "720p" | "1080p",
    framesPerSecond: 24 | 25 | 30,
    burnSubtitles: boolean,
  ) => {
    if (!adaptation) return;
    setWorking("export-start");
    setError(null);
    try {
      requireApiData(await browserApi.POST(
        "/api/v1/video/chapter-adaptations/{adaptation_id}/episodes/{episode_no}/export-tasks",
        {
          params: { path: { adaptation_id: adaptation.id, episode_no: episodeNo } },
          body: {
            clientRequestId: createClientRequestId(),
            editVersionId,
            mixVersionId,
            resolution,
            framesPerSecond,
            burnSubtitles,
          },
        },
      ));
      await loadPostProductionWorkspace(adaptation.id);
    } catch (exportError) {
      setError(errorMessage(exportError, "提交整集导出失败"));
    } finally {
      setWorking(null);
    }
  };

  const retryEpisodeExport = async (taskId: string) => {
    if (!adaptation) return;
    setWorking(`export-retry:${taskId}`);
    setError(null);
    try {
      requireApiData(await browserApi.POST(
        "/api/v1/video/export-tasks/{task_id}/retry",
        {
          params: { path: { task_id: taskId } },
          body: { clientRequestId: createClientRequestId() },
        },
      ));
      await loadPostProductionWorkspace(adaptation.id);
    } catch (retryError) {
      setError(errorMessage(retryError, "重试整集导出失败"));
    } finally {
      setWorking(null);
    }
  };

  const rewriteSelection = async () => {
    if (!sourceSelection || !selectionBridge || !currentChapter || adaptation?.sourceText !== currentChapter.content) return;
    await selectionBridge.captureSelection({
      resourceType: "chapter_content",
      resourceId: currentChapter.id,
      sourceLabel: `章节：${currentChapter.title}`,
      baseUpdatedAt: currentChapter.updatedAt,
      content: currentChapter.content,
      utf16Start: sourceSelection.utf16Start,
      utf16End: sourceSelection.utf16End,
    });
    setSourceSelection(null);
  };

  if (loading) return <div className="panel empty">正在加载章节影视化工作台...</div>;
  const candidateShots = candidatePlan ? flattenCandidateShots(candidatePlan) : [];
  const formalShots = formalPlan ? flattenFormalShots(formalPlan) : [];
  const metrics = durationMetrics(timelineShots);
  const metricsLabel = activePlanKind === "candidate"
    ? "待审候选"
    : formalPlan
      ? `正式 v${formalPlan.versionNo}`
      : "尚无方案";

  return (
    <section className="panel chapter-adaptation-workspace">
      <header className="chapter-adaptation-header">
        <div>
          <h2>{adaptation?.chapterTitle ?? currentChapter?.title ?? "章节影视化"}</h2>
          <span>{statusLabel(adaptation, taskActive, stage)}</span>
        </div>
        <div className="chapter-adaptation-controls">
          <label>节奏
            <select className="select" value={pacingPreset} disabled={taskActive} onChange={(event) => setPacingPreset(event.target.value as typeof pacingPreset)}>
              <option value="short_drama">短剧叙事</option><option value="cinematic">电影叙事</option><option value="dialogue_driven">对白驱动</option>
            </select>
          </label>
          <label>单集目标
            <select className="select" value={targetEpisodeSeconds} disabled={taskActive} onChange={(event) => setTargetEpisodeSeconds(Number(event.target.value) as 60 | 90 | 120)}>
              <option value={60}>60 秒</option><option value={90}>90 秒</option><option value={120}>120 秒</option>
            </select>
          </label>
          {stage === "review" ? (
            <>
              <button className="button secondary" type="button" disabled={!previewEnabled || !currentChapter || taskActive || editable || working !== null} onClick={() => void startPlan()}>{taskActive ? "分析中..." : editable ? "候选待处理" : formalPlan ? `基于 v${formalPlan.versionNo} 生成修订候选` : adaptation ? "重新分析章节" : "开始分析章节"}</button>
              {editable ? <button className="button ghost" type="button" disabled={working !== null} onClick={() => void discardCandidate()}>{working === "discard" ? "放弃中..." : "放弃候选"}</button> : null}
              {editable ? <button className="button primary" type="button" disabled={working !== null} onClick={() => void confirmPlan()}>{working === "confirm" ? "确认中..." : `确认 ${candidateShots.length} 个镜头`}</button> : null}
            </>
          ) : stage === "episodes" ? (
            <button className="button primary" type="button" disabled={!formalPlan || working !== null} onClick={() => void saveEpisodes()}>{working === "episodes" ? "保存中..." : "保存分集并进入视觉设定"}</button>
          ) : stage === "visuals" ? (
            <button className="button primary" type="button" disabled={!formalPlan} onClick={() => setStage("prompts")}>进入逐镜提示词</button>
          ) : stage === "prompts" ? (
            <>
              <button className="button secondary" type="button" disabled={!formalPlan || taskActive || working !== null} onClick={() => void generatePrompts([])}>{taskActive ? "提示词生成中..." : "批量生成未完成提示词"}</button>
              <button className="button primary" type="button" disabled={!formalPlan || !episodePlanReady} onClick={() => setStage("keyframes")}>进入关键帧</button>
            </>
          ) : stage === "keyframes" ? (
            <>
              <button className="button secondary" type="button" disabled={!adaptation || working !== null} onClick={() => adaptation && void loadPostProductionWorkspace(adaptation.id)}>刷新视觉锚点</button>
              <button className="button primary" type="button" disabled={!formalPlan} onClick={() => setStage("takes")}>进入生成与选片</button>
            </>
          ) : stage === "takes" ? (
            <>
              <button className="button secondary" type="button" disabled={!formalPlan || renderTaskActive} onClick={() => adaptation && void loadRenderWorkspace(adaptation.id)}>{renderTaskActive ? "候选生成中..." : "刷新候选"}</button>
              <button className="button primary" type="button" disabled={!formalPlan || !episodePlanReady} onClick={() => setStage("edit")}>进入分集粗剪</button>
            </>
          ) : stage === "edit" ? (
            <button className="button primary" type="button" disabled={!formalPlan} onClick={() => setStage("finish")}>进入声音与输出</button>
          ) : (
            <button className="button secondary" type="button" disabled={!adaptation} onClick={() => adaptation && void loadPostProductionWorkspace(adaptation.id)}>{exportTaskActive ? "导出中..." : "刷新后期状态"}</button>
          )}
        </div>
      </header>
      <nav className="chapter-adaptation-steps">
        <StageButton value="review" current={stage} label="拆镜与审镜" onSelect={setStage} />
        <StageButton value="episodes" current={stage} label="在镜头间分集" disabled={!formalPlan} onSelect={setStage} />
        <StageButton value="visuals" current={stage} label="角色与场景稳定" disabled={!formalPlan} onSelect={setStage} />
        <StageButton value="prompts" current={stage} label="逐镜提示词" disabled={!formalPlan} onSelect={setStage} />
        <StageButton value="keyframes" current={stage} label="关键帧" disabled={!formalPlan || !episodePlanReady} onSelect={setStage} />
        <StageButton value="takes" current={stage} label="生成与选片" disabled={!formalPlan} onSelect={setStage} />
        <StageButton value="edit" current={stage} label="分集粗剪" disabled={!formalPlan || !episodePlanReady} onSelect={setStage} />
        <StageButton value="finish" current={stage} label="声音与输出" disabled={!formalPlan || !episodePlanReady} onSelect={setStage} />
      </nav>
      {error ? <div className="notice notice-danger" role="alert">{error}</div> : null}
      {adaptation?.latestTask?.status === "failed" ? (
        <div className="notice notice-danger" role="alert">
          {adaptation.latestTask.lastErrorMessage ?? "章节影视化任务失败，请重新提交。"}
        </div>
      ) : null}
      {!previewEnabled ? <div className="notice notice-warning">当前环境未开启视频开发预览写入。</div> : null}
      {sourceChanged ? <div className="notice notice-warning">当前章节正文已经修改，这里保留的是旧快照；重新电影化拆镜会创建新的章节改编。</div> : null}
      {stage !== "review" && candidatePlan && formalPlan ? (
        <section className="adaptation-version-context notice notice-warning">
          <div>
            <strong>当前正在处理正式 v{formalPlan.versionNo}（{formalShots.length} 镜）</strong>
            <span>另有待审候选（{candidateShots.length} 镜）；只有确认后才会成为新的正式版本，不会静默覆盖当前工作。</span>
          </div>
          <button className="button secondary sm" type="button" onClick={() => setStage("review")}>返回审镜</button>
        </section>
      ) : null}
      {(candidatePlan || formalPlan) ? (
        <div className="chapter-adaptation-metrics">
          <strong>{metricsLabel}</strong>
          <span>{timelineScenes.length} 场</span><span>{timelineScenes.reduce((sum, scene) => sum + scene.beats.length, 0)} 节拍</span><span>{timelineShots.length} 镜</span>
          <span>约 {Number((metrics.totalMs / 1000).toFixed(1))} 秒</span><span>平均 {Number((metrics.averageMs / 1000).toFixed(1))} 秒/镜</span>
          {activePlanKind === "candidate" && candidatePlan ? <span>原文覆盖 {candidateSourceCoverage(candidatePlan, Array.from(adaptation?.sourceText ?? "").length)}%</span> : null}
        </div>
      ) : null}
      {stage === "review" && formalPlan && !candidatePlan ? (
        <section className="adaptation-revision-brief">
          <div><strong>从正式 v{formalPlan.versionNo} 继续</strong><span>AI 会重新分析叙事目标，保留有效镜头并生成完整待审修订；当前版本不会被改写。</span></div>
          <textarea
            className="textarea"
            value={revisionBrief}
            maxLength={1200}
            disabled={taskActive || working !== null}
            placeholder="可选：写下这次最想解决的问题，例如空间关系不清、镜头职责重复、画外对白声层错误……"
            onChange={(event) => setRevisionBrief(event.target.value)}
          />
        </section>
      ) : null}
      {stage === "review" && candidatePlan ? (
        <ShotPlanAudit
          reviewSummary={candidatePlan.reviewSummary ?? null}
          initialFindings={candidatePlan.reviewFindings ?? []}
          liveFindings={liveCoverageFindings}
          edited={draftEdited}
          onSelectShot={setSelectedShotKey}
        />
      ) : null}
      {stage === "review" ? (
        (candidatePlan || formalPlan) ? (
          <div className="chapter-adaptation-review-grid">
            <SourcePanel
              sourceText={adaptation?.sourceText ?? currentChapter?.content ?? ""}
              shots={timelineShots}
              selectedShotKey={selectedShotKey}
              editable={editable}
              selection={sourceSelection}
              onSelectShot={setSelectedShotKey}
              onSelection={setSourceSelection}
              onRewrite={() => void rewriteSelection()}
              onBind={() => {
                if (!draftPlan || !selectedShotKey || !sourceSelection) return;
                applyDraftPlan(bindShotSource(draftPlan, selectedShotKey, sourceSelection));
                setSourceSelection(null);
              }}
              onAddFromSelection={() => {
                if (!draftPlan || !selectedShotKey || !sourceSelection) return;
                const next = addShotAfter(draftPlan, selectedShotKey, sourceSelection, "action");
                applyDraftPlan(next);
                setSourceSelection(null);
              }}
              onClearSelection={() => setSourceSelection(null)}
            />
            <ShotTimeline
              scenes={timelineScenes}
              selectedShotKey={selectedShotKey}
              editable={editable}
              onSelect={setSelectedShotKey}
              onMergeScene={(sceneKey) => {
                if (!draftPlan) return;
                const next = mergeSceneWithNext(draftPlan, sceneKey);
                if (next) applyDraftPlan(next);
                else setError("当前场景之后没有可合并场景");
              }}
            />
            <ShotInspector
              shot={selectedLocation?.shot ?? null}
              sceneTitle={selectedLocation?.scene.title ?? ""}
              beatTitle={selectedLocation?.beat.title ?? ""}
              coverageGoals={selectedLocation?.beat.coverageGoals ?? []}
              editable={editable}
              discardedCount={discardedShots.length}
              onChange={(patch) => draftPlan && selectedShotKey && applyDraftPlan(updateCandidateShot(draftPlan, selectedShotKey, patch))}
              onToggleGoal={(goalKey) => {
                if (!draftPlan || !selectedShotKey || !selectedLocation) return;
                const current = selectedLocation.shot.coveredGoalKeys ?? [];
                const coveredGoalKeys = current.includes(goalKey)
                  ? current.filter((item) => item !== goalKey)
                  : [...current, goalKey];
                applyDraftPlan(updateCandidateShot(draftPlan, selectedShotKey, { coveredGoalKeys }));
              }}
              onMerge={() => {
                if (!draftPlan || !selectedShotKey) return;
                const next = mergeShotWithNext(draftPlan, selectedShotKey);
                if (next) applyDraftPlan(next); else setError("只能合并同一节拍中的相邻镜头；时长不能超过 15 秒，且两镜对白位置不能冲突");
              }}
              onDelete={() => {
                if (!draftPlan || !selectedShotKey) return;
                const result = deleteCandidateShot(draftPlan, selectedShotKey);
                if (!result) return setError("每个戏剧节拍至少保留一个镜头");
                setDiscardedShots((current) => [...current, result.discarded]);
                applyDraftPlan(result.plan);
              }}
              onRestore={() => {
                const discarded = discardedShots.at(-1);
                if (!draftPlan || !discarded) return;
                const next = restoreCandidateShot(draftPlan, discarded);
                if (next) {
                  applyDraftPlan(next);
                  setDiscardedShots((current) => current.slice(0, -1));
                }
              }}
              onAdd={(purpose: CandidateShot["narrativePurpose"]) => {
                if (!draftPlan || !selectedShotKey) return;
                const needsSource = purpose === "action";
                if (needsSource && !sourceSelection) return setError("新增动作镜头前，请先在左侧选择对应原文");
                const next = addShotAfter(draftPlan, selectedShotKey, needsSource ? sourceSelection : null, purpose);
                applyDraftPlan(next);
                setSourceSelection(null);
              }}
            />
          </div>
        ) : (
          <div className="chapter-adaptation-empty">
            <strong>{taskActive ? "AI 正在识别场景、戏剧节拍和观众目标" : "把当前章节转成可审核的镜头时间线"}</strong>
            <p>AI 先判断观众在每个节拍中必须获得什么，再用镜头完成目标；不会按对白、句号或固定景别模板机械拆分。</p>
            {!taskActive ? <button className="button primary" type="button" disabled={!previewEnabled || !currentChapter} onClick={() => void startPlan()}>开始分析章节</button> : <span>任务已进入耐久队列，可以安全刷新页面。</span>}
          </div>
        )
      ) : null}
      {stage === "episodes" && formalPlan ? <EpisodeEditor plan={formalPlan} breakAfterShotIds={episodeBreakIds} targetEpisodeSeconds={targetEpisodeSeconds} onToggle={(shotId) => setEpisodeBreakIds((current) => toggleEpisodeBoundary(formalPlan, current, shotId))} /> : null}
      {stage === "visuals" && formalPlan && activeProjectId && adaptation ? <VisualCanonPanel
        novelId={novelId}
        projectId={activeProjectId}
        adaptationId={adaptation.id}
        plan={formalPlan}
        selectedShot={selectedFormalShot}
        canons={visualCanons}
        referenceSets={adaptation.visualReferenceSets}
        onSelectShot={setSelectedShotKey}
        onCanonChanged={(canon) => setVisualCanons((current) => {
          const exists = current.some((item) => item.id === canon.id);
          return exists
            ? current.map((item) => item.id === canon.id ? canon : item)
            : [...current, canon];
        })}
        onReferenceSetChanged={(referenceSet) => setAdaptation((current) => current ? {
          ...current,
          visualReferenceSets: current.visualReferenceSets.some((item) => item.shotId === referenceSet.shotId)
            ? current.visualReferenceSets.map((item) => item.shotId === referenceSet.shotId ? referenceSet : item)
            : [...current.visualReferenceSets, referenceSet],
        } : current)}
      /> : null}
      {stage === "prompts" && formalPlan ? <PromptEditor
        plan={formalPlan}
        selectedShot={selectedFormalShot}
        candidate={selectedPromptCandidate}
        candidates={adaptation?.promptCandidates ?? []}
        versions={adaptation?.promptVersions ?? []}
        breakAfterShotIds={adaptation?.episodePlan?.breakAfterShotIds ?? []}
        promptText={promptText}
        aspectRatio={projects.find((item) => item.id === activeProjectId)?.targetAspectRatio ?? "9:16"}
        visualReferences={selectedPromptCandidate?.visualReferences
          ?? selectedPromptVersion?.visualReferences
          ?? currentVisualReferences
          ?? []}
        currentVisualReferences={currentVisualReferences}
        taskActive={taskActive}
        working={working}
        onSelect={setSelectedShotKey}
        onPromptChange={setPromptText}
        onGenerate={() => selectedFormalShot && void generatePrompts([selectedFormalShot.id])}
        onSave={() => void savePrompt()}
      /> : null}
      {stage === "keyframes" && formalPlan ? <KeyframeWorkspace
        plan={formalPlan}
        selectedShot={selectedFormalShot}
        workspace={postProductionWorkspace}
        working={working}
        onSelectShot={setSelectedShotKey}
        onBind={(role, assetId) => void bindKeyframe(role, assetId)}
        onExtract={(role, takeId, timestampMs) => void extractKeyframe(role, takeId, timestampMs)}
        onUpload={(role, file) => void uploadKeyframe(role, file)}
      /> : null}
      {stage === "takes" && formalPlan ? <TakeWorkspace
        plan={formalPlan}
        selectedShot={selectedFormalShot}
        promptVersion={selectedPromptVersion}
        workspace={renderWorkspace}
        breakAfterShotIds={adaptation?.episodePlan?.breakAfterShotIds ?? []}
        durationSeconds={renderDurationSeconds}
        resolution={renderResolution}
        compareTakeIds={compareTakeIds}
        working={working}
        onSelectShot={setSelectedShotKey}
        onDurationChange={setRenderDurationSeconds}
        onResolutionChange={setRenderResolution}
        onGenerate={() => void startRender()}
        onRetry={(taskId) => void retryRender(taskId)}
        onConfirm={(takeId) => void confirmTake(takeId)}
        onToggleCompare={(takeId) => setCompareTakeIds((current) => {
          if (current.includes(takeId)) return current.filter((item) => item !== takeId);
          return current.length < 2 ? [...current, takeId] : [current[1], takeId];
        })}
      /> : null}
      {stage === "edit" && formalPlan ? <RoughCutWorkspace
        workspace={postProductionWorkspace}
        working={working}
        onLoadVersion={loadEditVersion}
        onSave={(episodeNo, clips, basedOnVersionId) => void saveEditVersion(episodeNo, clips, basedOnVersionId)}
      /> : null}
      {stage === "finish" && formalPlan ? <FinishWorkspace
        workspace={postProductionWorkspace}
        working={working}
        onLoadMixVersion={loadMixVersion}
        onSaveMix={(episodeNo, editVersionId, audioClips, subtitleCues, basedOnVersionId) => void saveMixVersion(episodeNo, editVersionId, audioClips, subtitleCues, basedOnVersionId)}
        onUploadAudio={(trackKind, file) => void uploadAudio(trackKind, file)}
        onStartExport={(episodeNo, editVersionId, mixVersionId, resolution, framesPerSecond, burnSubtitles) => void startEpisodeExport(episodeNo, editVersionId, mixVersionId, resolution, framesPerSecond, burnSubtitles)}
        onRetryExport={(taskId) => void retryEpisodeExport(taskId)}
      /> : null}
    </section>
  );
}

function StageButton({ value, current, label, disabled = false, onSelect }: { value: Stage; current: Stage; label: string; disabled?: boolean; onSelect: (value: Stage) => void }) {
  return <button className={current === value ? "active" : ""} type="button" disabled={disabled} onClick={() => onSelect(value)}>{label}</button>;
}

function statusLabel(adaptation: ChapterAdaptation | null, taskActive: boolean, stage: Stage): string {
  if (taskActive && adaptation?.latestTask?.kind === "shot_prompt") return "正在生成逐镜即梦提示词";
  if (taskActive) return adaptation?.latestTask?.checkpointStage === "dramatic_structure" ? "已完成戏剧分析，正在设计镜头" : "正在分析章节";
  if (stage === "keyframes") return "逐镜关键帧与连续性复核";
  if (stage === "takes") return "逐镜生成与候选选片";
  if (stage === "edit") return "分集非破坏性粗剪";
  if (stage === "finish") return "声音、字幕与可追溯整集输出";
  if (stage !== "review" && adaptation?.currentPlan) return `正在处理正式镜头方案 v${adaptation.currentPlan.versionNo}`;
  if (adaptation?.state === "awaiting_review") return "电影化镜头候选等待确认";
  if (adaptation?.state === "approved") return `正式镜头方案 v${adaptation.currentPlan?.versionNo ?? 1}`;
  if (adaptation?.state === "failed") return adaptation.latestTask?.lastErrorMessage ?? "任务失败，可重新提交";
  return "尚未开始";
}

function initialStage(adaptation: ChapterAdaptation): Stage {
  if (adaptation.candidatePlan || !adaptation.currentPlan) return "review";
  if (adaptation.promptVersions.length || adaptation.promptCandidates.length) return "prompts";
  if (adaptation.episodePlan) return "visuals";
  return "episodes";
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function findTimelineLocation(scenes: TimelineScene[], shotKey: string | null) {
  for (const scene of scenes) {
    for (const beat of scene.beats) {
      const shot = beat.shots.find((item) => item.shotKey === shotKey);
      if (shot) return { scene, beat, shot };
    }
  }
  return null;
}

function toggleEpisodeBoundary(plan: NonNullable<ChapterAdaptation["currentPlan"]>, current: string[], shotId: string) {
  const next = new Set(current);
  if (next.has(shotId)) next.delete(shotId);
  else next.add(shotId);
  const positions = new Map(flattenFormalShots(plan).map((shot, index) => [shot.id, index]));
  return [...next].sort((left, right) => (positions.get(left) ?? 0) - (positions.get(right) ?? 0));
}

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
import { PromptEditor } from "./prompt-editor";
import { ShotInspector } from "./shot-inspector";
import { ShotPlanAudit } from "./shot-plan-audit";
import { ShotTimeline, type TimelineScene } from "./shot-timeline";
import { SourcePanel } from "./source-panel";
import { VisualCanonPanel } from "./visual-canon-panel";
import type {
  AdaptationCandidate,
  ChapterAdaptation,
  ChapterAdaptationWorkspaceProps,
  CandidateShot,
  FormalShot,
  SourceSelection,
  VisualCanon,
  VideoProject,
} from "./types";

type Stage = "review" | "episodes" | "visuals" | "prompts";
const ACTIVE_TASKS = new Set(["pending", "submitted", "processing"]);

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

  const candidatePlan = draftPlan ?? adaptation?.candidatePlan ?? null;
  const formalPlan = adaptation?.currentPlan ?? null;
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
          ) : (
              <button className="button secondary" type="button" disabled={!formalPlan || taskActive || working !== null} onClick={() => void generatePrompts([])}>{taskActive ? "提示词生成中..." : "批量生成未完成提示词"}</button>
          )}
        </div>
      </header>
      <nav className="chapter-adaptation-steps">
        <StageButton value="review" current={stage} label="拆镜与审镜" onSelect={setStage} />
        <StageButton value="episodes" current={stage} label="在镜头间分集" disabled={!formalPlan} onSelect={setStage} />
        <StageButton value="visuals" current={stage} label="角色与场景稳定" disabled={!formalPlan} onSelect={setStage} />
        <StageButton value="prompts" current={stage} label="逐镜提示词" disabled={!formalPlan} onSelect={setStage} />
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
    </section>
  );
}

function StageButton({ value, current, label, disabled = false, onSelect }: { value: Stage; current: Stage; label: string; disabled?: boolean; onSelect: (value: Stage) => void }) {
  return <button className={current === value ? "active" : ""} type="button" disabled={disabled} onClick={() => onSelect(value)}>{label}</button>;
}

function statusLabel(adaptation: ChapterAdaptation | null, taskActive: boolean, stage: Stage): string {
  if (taskActive && adaptation?.latestTask?.kind === "shot_prompt") return "正在生成逐镜即梦提示词";
  if (taskActive) return adaptation?.latestTask?.checkpointStage === "dramatic_structure" ? "已完成戏剧分析，正在设计镜头" : "正在分析章节";
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

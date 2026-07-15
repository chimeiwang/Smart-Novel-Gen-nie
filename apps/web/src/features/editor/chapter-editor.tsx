"use client";

import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import type { QualityCheckDto } from "@/shared/contracts/quality-check";
import { countTextLength } from "@/shared/lib/word-count";
import {
  ChapterSaveCoordinator,
  createBestEffortChapterDraftStorage,
  type ChapterSaveState,
} from "./chapter-save-coordinator";
import { registerActiveChapterSave } from "./chapter-save-navigation";
import {
  canResetQualityCheck,
  findRunningQualityCheck,
  findQualityCheckToResume,
  pollQualityCheck,
} from "./quality-check-poller";

type ChapterEditorProps = {
  userId: string;
  novelId: string;
  chapter: {
    id: string;
    title: string;
    content: string;
    status: string;
    completedAt: string | null;
    updatedAt: string;
  };
  chapterProgress: string | null;
  qualityChecks?: QualityCheckDto[];
  styleName?: string | null;
};

export function ChapterEditor({
  userId,
  novelId,
  chapter,
  chapterProgress,
  qualityChecks = [],
  styleName,
}: ChapterEditorProps) {
  const router = useRouter();
  const [title, setTitle] = useState(chapter.title);
  const [content, setContent] = useState(chapter.content);
  const [saveState, setSaveState] = useState<ChapterSaveState>("saved");
  const [chapterStatus, setChapterStatus] = useState(chapter.status);
  const [pendingStatus, startStatusTransition] = useTransition();
  const [showQualityDialog, setShowQualityDialog] = useState(false);
  const [runningCheckId, setRunningCheckId] = useState<string | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [draftDiscardError, setDraftDiscardError] = useState<string | null>(null);
  const [localChecks, setLocalChecks] = useState<Record<string, QualityCheckDto>>({});
  const saveCoordinatorRef = useRef<ChapterSaveCoordinator | null>(null);
  const qualityPollingGenerationRef = useRef(0);
  const qualityPollingCheckIdRef = useRef<string | null>(null);
  const resumedRunningCheckIdRef = useRef<string | null>(null);

  // 章节进展状态
  const [progressContent, setProgressContent] = useState(chapterProgress ?? "");
  const [showProgress, setShowProgress] = useState(false);
  const [pendingProgress, startProgressTransition] = useTransition();

  useEffect(() => {
    let active = true;
    const storage = createBestEffortChapterDraftStorage(
      window,
      `inkforge:chapter-draft:${userId}:${novelId}:${chapter.id}`,
    );
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: { title: chapter.title, content: chapter.content },
      initialUpdatedAt: chapter.updatedAt,
      delayMs: 1_200,
      storage,
      save: async (request) => requireApiData(await browserApi.PATCH(
        "/api/v1/chapters/{chapter_id}",
        {
          params: { path: { chapter_id: chapter.id } },
          body: request,
        },
      )),
      onStateChange: (state) => {
        if (active) setSaveState(state);
      },
    });
    saveCoordinatorRef.current = coordinator;
    const restoredSnapshot = coordinator.snapshot;
    queueMicrotask(() => {
      if (!active) return;
      setTitle(restoredSnapshot.title);
      setContent(restoredSnapshot.content);
      setSaveState(coordinator.state);
    });

    const unregisterSave = registerActiveChapterSave(() => coordinator.flush());
    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (coordinator.state === "saved") return;
      event.preventDefault();
      event.returnValue = "";
    };
    const handlePageHide = () => {
      void coordinator.flush().catch(() => undefined);
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    window.addEventListener("pagehide", handlePageHide);

    return () => {
      active = false;
      unregisterSave();
      window.removeEventListener("beforeunload", handleBeforeUnload);
      window.removeEventListener("pagehide", handlePageHide);
      if (saveCoordinatorRef.current === coordinator) {
        saveCoordinatorRef.current = null;
      }
      void coordinator.dispose();
    };
  }, [chapter.content, chapter.id, chapter.title, chapter.updatedAt, novelId, userId]);

  useEffect(() => () => {
    qualityPollingGenerationRef.current += 1;
    qualityPollingCheckIdRef.current = null;
    resumedRunningCheckIdRef.current = null;
  }, [chapter.id]);

  const chapterWordCount = useMemo(() => countTextLength(content), [content]);
  const saveStatus = getChapterSaveStatusLabel(saveState);
  const checks = useMemo(
    () => qualityChecks.map((check) => selectLatestQualityCheck(check, localChecks[check.id])),
    [localChecks, qualityChecks],
  );
  const visibleChecks = chapterStatus === "review" || chapterStatus === "completed"
    ? checks.filter((check) => check.type === "consistency")
    : [];
  const openCheckCount = visibleChecks.filter((check) => check.status === "pending" || check.status === "failed").length;
  const doneCheckCount = visibleChecks.filter((check) => check.status === "completed" || check.status === "skipped").length;
  const hasBlockingCheck = visibleChecks.some(
    (check) => check.status !== "completed" && check.status !== "skipped",
  );
  const flowSteps = getChapterFlowSteps(chapterStatus, visibleChecks.length, doneCheckCount);
  const chapterEditable = chapterStatus === "drafting";
  const retryableRunningCheck = qualityError
    ? findRunningQualityCheck(checks, runningCheckId)
    : null;

  const handleSaveProgress = () => {
    startProgressTransition(async () => {
      requireApiData(await browserApi.PUT("/api/v1/chapters/{chapter_id}/progress", {
        params: { path: { chapter_id: chapter.id } },
        body: { content: progressContent },
      }));
    });
  };

  const handleStatusChange = (status: "drafting" | "review" | "completed") => {
    setQualityError(null);
    startStatusTransition(async () => {
      try {
        const coordinator = saveCoordinatorRef.current;
        await coordinator?.flush();
        const response = requireApiData(await browserApi.PATCH("/api/v1/chapters/{chapter_id}/status", {
          params: { path: { chapter_id: chapter.id } },
          body: {
            status,
            expectedUpdatedAt: coordinator?.updatedAt ?? chapter.updatedAt,
          },
        }));
        coordinator?.advanceVersion(response.updatedAt);
        setChapterStatus(status);
        router.refresh();
      } catch (error) {
        setQualityError(error instanceof Error ? error.message : "章节状态更新失败");
        if (status === "completed") setShowQualityDialog(true);
      }
    });
  };

  const pollRunningQualityCheck = useCallback(async (check: QualityCheckDto) => {
    if (qualityPollingCheckIdRef.current !== null) return;
    qualityPollingCheckIdRef.current = check.id;
    resumedRunningCheckIdRef.current = check.id;
    const pollingGeneration = qualityPollingGenerationRef.current + 1;
    qualityPollingGenerationRef.current = pollingGeneration;
    setRunningCheckId(check.id);
    setQualityError(null);
    try {
      const terminalCheck = await pollQualityCheck<QualityCheckDto>({
        fetchCheck: async () => requireApiData(await browserApi.GET(
          "/api/v1/quality-checks/{check_id}",
          { params: { path: { check_id: check.id } } },
        )),
        getStatus: (current) => current.status,
        onUpdate: (current) => {
          setLocalChecks((allChecks) => replaceQualityCheck(allChecks, current));
        },
        isCancelled: () => qualityPollingGenerationRef.current !== pollingGeneration,
        maxAttempts: 18,
      });
      if (terminalCheck?.status === "failed") {
        setQualityError("一致性终检执行失败，请重试");
      }
      if (terminalCheck) router.refresh();
    } catch (error) {
      if (qualityPollingGenerationRef.current === pollingGeneration) {
        setQualityError(error instanceof Error ? error.message : "一致性终检状态更新失败");
      }
    } finally {
      if (qualityPollingGenerationRef.current === pollingGeneration) {
        qualityPollingCheckIdRef.current = null;
        setRunningCheckId(null);
      }
    }
  }, [router]);

  useEffect(() => {
    const runningCheck = findQualityCheckToResume(
      checks,
      runningCheckId,
      resumedRunningCheckIdRef.current,
    );
    if (runningCheck) {
      void pollRunningQualityCheck(runningCheck);
      return;
    }
    if (
      qualityPollingCheckIdRef.current === null
      && !checks.some((check) => check.status === "running")
    ) {
      resumedRunningCheckIdRef.current = null;
    }
  }, [checks, pollRunningQualityCheck, runningCheckId]);

  const runQualityCheck = async (check: QualityCheckDto) => {
    if (qualityPollingCheckIdRef.current !== null) return;
    setRunningCheckId(check.id);
    setQualityError(null);
    try {
      requireApiData(await browserApi.POST("/api/v1/quality-checks/{check_id}/run", {
        params: { path: { check_id: check.id } },
        body: {},
      }));
      const runningCheck: QualityCheckDto = { ...check, status: "running" };
      setLocalChecks((current) => replaceQualityCheck(current, runningCheck));
      await pollRunningQualityCheck(runningCheck);
    } catch (error) {
      setQualityError(error instanceof Error ? error.message : "一致性终检启动失败");
      if (qualityPollingCheckIdRef.current === null) setRunningCheckId(null);
    }
  };

  const markQualityCheck = async (check: QualityCheckDto, status: "skipped" | "pending") => {
    setRunningCheckId(check.id);
    setQualityError(null);
    try {
      const updatedCheck = requireApiData(await browserApi.PATCH("/api/v1/quality-checks/{check_id}", {
        params: { path: { check_id: check.id } },
        body: { status, resetResult: status === "pending" },
      }));
      setLocalChecks((current) => replaceQualityCheck(current, updatedCheck));
      router.refresh();
    } catch (error) {
      setQualityError(error instanceof Error ? error.message : "一致性终检状态更新失败");
    } finally {
      setRunningCheckId(null);
    }
  };

  return (
    <div className="panel panel-flex">
      <div className="panel-header">
        <div className="meta">
          <span className="badge">当前章节 {chapterWordCount} 字</span>
          <span className={`status-text ${saveState === "saved" ? "success" : ""}`}>
            {saveStatus}
          </span>
          {saveState === "failed" ? (
            <button
              className="button ghost sm"
              type="button"
              onClick={() => {
                void saveCoordinatorRef.current?.retry().catch(() => undefined);
              }}
            >
              重试保存
            </button>
          ) : null}
          {saveState === "conflict" ? (
            <span className="row">
              <span className="muted error-text">版本冲突，请先复制并保留当前正文</span>
              <button
                className="button ghost sm"
                type="button"
                onClick={() => {
                  setDraftDiscardError(null);
                  const discarded = saveCoordinatorRef.current?.discardLocalDraft();
                  if (discarded) {
                    window.location.reload();
                  } else {
                    setDraftDiscardError("浏览器无法清除本地草稿，请允许站点存储后重试");
                  }
                }}
              >
                放弃本地草稿并重新加载
              </button>
            </span>
          ) : null}
          {draftDiscardError ? (
            <span className="muted error-text">{draftDiscardError}</span>
          ) : null}
          {qualityError && !showQualityDialog ? (
            <span className="muted error-text">{qualityError}</span>
          ) : null}
          <span className="badge">{getChapterStatusLabel(chapterStatus)}</span>
          {styleName ? <span className="badge">文风：{styleName}</span> : null}
        </div>
        <div className="row editor-actions">
          <div className="chapter-flow-compact">
            <div className="chapter-flow-compact-main">
              <span className={`chapter-flow-dot ${chapterStatus}`} />
              <span>{getChapterFlowHeadline(chapterStatus, visibleChecks.length, openCheckCount)}</span>
            </div>
            <div className="chapter-flow-popover">
              {flowSteps.map((step, index) => (
                <div className={`chapter-flow-popover-step ${step.state}`} key={step.title}>
                  <span>{step.state === "done" ? "✓" : index + 1}</span>
                  <div>
                    <strong>{step.title}</strong>
                    <p>{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <button
            className="button ghost sm"
            type="button"
            onClick={() => setShowProgress(!showProgress)}
          >
            {showProgress ? "隐藏章节进展" : "章节进展"}
          </button>
          <button
            className="button ghost sm"
            type="button"
            onClick={() => setShowQualityDialog(true)}
            disabled={visibleChecks.length === 0}
            title={visibleChecks.length === 0 ? "送审后生成一致性终检" : "查看一致性终检"}
          >
            一致性终检{visibleChecks.length > 0 ? ` ${doneCheckCount}/${visibleChecks.length}` : ""}
          </button>
          {chapterStatus === "review" ? (
            <button
              className="button ghost sm"
              type="button"
              onClick={() => handleStatusChange("drafting")}
              disabled={pendingStatus}
            >
              退回草稿
            </button>
          ) : null}
          {chapterStatus === "completed" ? (
            <button
              className="button ghost sm"
              type="button"
              onClick={() => handleStatusChange("drafting")}
              disabled={pendingStatus}
            >
              重新编辑
            </button>
          ) : null}
          {chapterStatus === "drafting" ? (
            <button
              className="button secondary sm"
              type="button"
              onClick={() => handleStatusChange("review")}
              disabled={pendingStatus || saveState === "failed" || saveState === "conflict"}
            >
              送审
            </button>
          ) : null}
          {chapterStatus === "review" ? (
            <button
              className="button sm"
              type="button"
              onClick={() => handleStatusChange("completed")}
              disabled={pendingStatus || hasBlockingCheck}
            >
              标记完成
            </button>
          ) : null}
        </div>
      </div>

      <div className="panel-body stack editor-layout">
        <input
          className="input"
          placeholder="章节标题"
          value={title}
          readOnly={!chapterEditable}
          onChange={(event) => {
            const nextTitle = event.target.value;
            setTitle(nextTitle);
            saveCoordinatorRef.current?.schedule({ title: nextTitle, content });
          }}
        />

        <textarea
          className="textarea editor-area"
          placeholder="正文内容"
          value={content}
          readOnly={!chapterEditable}
          onChange={(event) => {
            const nextContent = event.target.value;
            setContent(nextContent);
            saveCoordinatorRef.current?.schedule({ title, content: nextContent });
          }}
        />

        {/* 章节进展 */}
        {showProgress ? (
          <div className="stack editor-progress">
            <textarea
              className="textarea textarea-resize"
              placeholder="记录本章节的进展、关键事件、伏笔等..."
              value={progressContent}
              onChange={(e) => setProgressContent(e.target.value)}
            />
            <div className="row row-end">
              <button
                className="button secondary sm"
                type="button"
                onClick={handleSaveProgress}
                disabled={pendingProgress}
              >
                {pendingProgress ? "保存中..." : "保存进展"}
              </button>
            </div>
          </div>
        ) : null}

      </div>
      {showQualityDialog ? (
        <div className="modal-backdrop" onClick={() => setShowQualityDialog(false)}>
          <div className="modal chapter-check-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3>一致性终检</h3>
                <p className="muted">正文送审后，最后检查设定一致性、角色边界、伏笔和逻辑问题。</p>
              </div>
              <button className="button ghost sm" type="button" onClick={() => setShowQualityDialog(false)}>关闭</button>
            </div>
            <div className="modal-body chapter-check-list">
              {visibleChecks.length === 0 ? (
                <p className="muted">当前章节还未送审。点击“送审”后会生成一致性终检。</p>
              ) : null}
              {qualityError ? (
                <div className="row">
                  <p className="muted error-text">{qualityError}</p>
                  {retryableRunningCheck ? (
                    <button
                      className="button ghost sm"
                      type="button"
                      onClick={() => {
                        resumedRunningCheckIdRef.current = null;
                        void pollRunningQualityCheck(retryableRunningCheck);
                      }}
                    >
                      继续查询状态
                    </button>
                  ) : null}
                </div>
              ) : null}
              {visibleChecks.map((check) => {
                const finished = check.status === "completed" || check.status === "skipped";
                const busy = runningCheckId === check.id || check.status === "running";
                const actionDisabled = Boolean(runningCheckId) || check.status === "running";
                return (
                  <div className="chapter-check-row" key={check.id}>
                    <div className="chapter-check-row-main">
                      <div className="row">
                        <span className={`chapter-check-status ${check.status}`}>{getQualityStatusLabel(check.status)}</span>
                        <strong>{check.title}</strong>
                        {check.qualityGate ? <span className={`quality-gate ${check.qualityGate}`}>{getQualityGateLabel(check.qualityGate)}</span> : null}
                      </div>
                      {check.summary ? <p>{check.summary}</p> : null}
                      <QualityScoreStrip check={check} />
                      {check.result ? (
                        <details className="chapter-check-result">
                          <summary>查看报告</summary>
                          <div>{check.result}</div>
                        </details>
                      ) : null}
                    </div>
                    <div className="chapter-check-actions">
                      {!finished ? (
                        <>
                          <button className="button sm" type="button" disabled={actionDisabled} onClick={() => void runQualityCheck(check)}>
                            {busy ? "执行中..." : "执行"}
                          </button>
                          <button className="button ghost sm" type="button" disabled={actionDisabled} onClick={() => void markQualityCheck(check, "skipped")}>
                            跳过
                          </button>
                        </>
                      ) : canResetQualityCheck(chapterStatus, check.status) ? (
                        <button className="button ghost sm" type="button" disabled={Boolean(runningCheckId)} onClick={() => void markQualityCheck(check, "pending")}>
                          重置
                        </button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function getChapterSaveStatusLabel(state: ChapterSaveState): string {
  if (state === "waiting") return "等待保存";
  if (state === "saving") return "保存中...";
  if (state === "failed") return "保存失败";
  if (state === "conflict") return "版本冲突";
  return "已保存";
}

function replaceQualityCheck(
  checks: Record<string, QualityCheckDto>,
  updatedCheck: QualityCheckDto,
): Record<string, QualityCheckDto> {
  return { ...checks, [updatedCheck.id]: updatedCheck };
}

function selectLatestQualityCheck(
  serverCheck: QualityCheckDto,
  localCheck: QualityCheckDto | undefined,
): QualityCheckDto {
  if (!localCheck) return serverCheck;
  return Date.parse(localCheck.updatedAt) >= Date.parse(serverCheck.updatedAt)
    ? localCheck
    : serverCheck;
}

function getChapterStatusLabel(status: string) {
  if (status === "review") return "待审";
  if (status === "completed") return "已完成";
  return "草稿";
}

function getChapterFlowHeadline(status: string, checkCount: number, openCheckCount: number) {
  if (status === "completed") return "本章已完成";
  if (status === "review" && openCheckCount > 0) return "一致性终检待处理";
  if (status === "review" && checkCount > 0) return "一致性终检已处理，等待完成章节";
  return "草稿中，正文和计划可以继续调整";
}

function getChapterFlowSteps(status: string, checkCount: number, doneCheckCount: number) {
  const inReview = status === "review" || status === "completed";
  return [
    { title: "规划", desc: "在智能写作中生成或讨论本章计划。", state: "done" },
    { title: "写正文", desc: "正文编辑器保存正式章节文本。", state: status === "drafting" ? "current" : "done" },
    { title: "送审", desc: "送审后生成一致性终检。", state: inReview ? "done" : "blocked" },
    { title: "一致性终检", desc: checkCount > 0 ? `${doneCheckCount}/${checkCount} 已处理` : "送审后出现。", state: checkCount > 0 && doneCheckCount < checkCount ? "current" : checkCount > 0 ? "done" : "blocked" },
    { title: "完成", desc: "终检处理完后标记完成。", state: status === "completed" ? "done" : inReview && checkCount > 0 && doneCheckCount === checkCount ? "current" : "blocked" },
  ] as const;
}

function getQualityStatusLabel(status: string) {
  if (status === "running") return "执行中";
  if (status === "completed") return "完成";
  if (status === "skipped") return "跳过";
  if (status === "failed") return "失败";
  return "待处理";
}

function getQualityGateLabel(gate: string) {
  if (gate === "rewrite") return "建议返工";
  if (gate === "revise") return "建议修改";
  if (gate === "pass") return "可通过";
  return gate;
}

function getScoreTone(score: number) {
  if (score <= 5) return "low";
  if (score <= 7) return "mid";
  return "high";
}

function QualityScoreStrip({ check }: { check: QualityCheckDto }) {
  const scores = [
    ["钩子", check.scoreHook],
    ["冲突", check.scoreTension],
    ["爽点", check.scorePayoff],
    ["节奏", check.scorePacing],
    ["尾钩", check.scoreEndingHook],
    ["承诺", check.scoreReaderPromise],
  ] as const;
  const visibleScores = scores.filter(([, score]) => typeof score === "number");
  if (visibleScores.length === 0 && typeof check.scoreOverall !== "number") return null;

  return (
    <div className="quality-score-strip">
      {typeof check.scoreOverall === "number" ? (
        <span className={`quality-score overall ${getScoreTone(check.scoreOverall)}`}>
          综合 {check.scoreOverall}/10
        </span>
      ) : null}
      {visibleScores.map(([label, score]) => (
        <span key={label} className={`quality-score ${getScoreTone(score ?? 0)}`}>
          {label} {score}/10
        </span>
      ))}
    </div>
  );
}

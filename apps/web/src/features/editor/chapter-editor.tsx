"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import type { QualityCheckDto } from "@/shared/contracts/quality-check";
import { countTextLength } from "@/shared/lib/word-count";

type ChapterEditorProps = {
  chapter: {
    id: string;
    title: string;
    content: string;
    status: string;
    completedAt: string | null;
  };
  chapterProgress: string | null;
  qualityChecks?: QualityCheckDto[];
  styleName?: string | null;
};

export function ChapterEditor({
  chapter,
  chapterProgress,
  qualityChecks = [],
  styleName,
}: ChapterEditorProps) {
  const router = useRouter();
  const [title, setTitle] = useState(chapter.title);
  const [content, setContent] = useState(chapter.content);
  const [saveStatus, setSaveStatus] = useState("已同步");
  const [chapterStatus, setChapterStatus] = useState(chapter.status);
  const [, startStatusTransition] = useTransition();
  const [showQualityDialog, setShowQualityDialog] = useState(false);
  const [runningCheckId, setRunningCheckId] = useState<string | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);

  // 章节进展状态
  const [progressContent, setProgressContent] = useState(chapterProgress ?? "");
  const [showProgress, setShowProgress] = useState(false);
  const [pendingProgress, startProgressTransition] = useTransition();

  const lastSavedRef = useRef({
    title: chapter.title,
    content: chapter.content,
  });

  useEffect(() => {
    if (
      title === lastSavedRef.current.title &&
      content === lastSavedRef.current.content
    ) {
      return;
    }

    const timer = window.setTimeout(async () => {
      setSaveStatus("保存中...");
      requireApiData(await browserApi.PATCH("/api/v1/chapters/{chapter_id}", {
        params: { path: { chapter_id: chapter.id } },
        body: { title, content },
      }));

      lastSavedRef.current = { title, content };
      setSaveStatus("已自动保存");
    }, 1200);

    return () => window.clearTimeout(timer);
  }, [chapter.id, content, title]);

  const chapterWordCount = useMemo(() => countTextLength(content), [content]);
  const visibleChecks = chapterStatus === "review" || chapterStatus === "completed"
    ? qualityChecks.filter((check) => check.type === "consistency")
    : [];
  const openCheckCount = visibleChecks.filter((check) => check.status === "pending" || check.status === "failed").length;
  const doneCheckCount = visibleChecks.filter((check) => check.status === "completed" || check.status === "skipped").length;
  const flowSteps = getChapterFlowSteps(chapterStatus, visibleChecks.length, doneCheckCount);

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
        requireApiData(await browserApi.PATCH("/api/v1/chapters/{chapter_id}/status", {
          params: { path: { chapter_id: chapter.id } },
          body: { status },
        }));
        setChapterStatus(status);
        router.refresh();
      } catch (error) {
        setQualityError(error instanceof Error ? error.message : "章节状态更新失败");
        if (status === "completed") setShowQualityDialog(true);
      }
    });
  };

  const runQualityCheck = async (check: QualityCheckDto) => {
    setRunningCheckId(check.id);
    setQualityError(null);
    try {
      requireApiData(await browserApi.POST("/api/v1/quality-checks/{check_id}/run", {
        params: { path: { check_id: check.id } },
        body: {},
      }));
      router.refresh();
    } catch (error) {
      setQualityError(error instanceof Error ? error.message : "一致性终检启动失败");
    } finally {
      setRunningCheckId(null);
    }
  };

  const markQualityCheck = async (check: QualityCheckDto, status: "skipped" | "pending") => {
    setRunningCheckId(check.id);
    try {
      requireApiData(await browserApi.PATCH("/api/v1/quality-checks/{check_id}", {
        params: { path: { check_id: check.id } },
        body: { status, resetResult: status === "pending" },
      }));
      router.refresh();
    } finally {
      setRunningCheckId(null);
    }
  };

  return (
    <div className="panel panel-flex">
      <div className="panel-header">
        <div className="meta">
          <span className="badge">当前章节 {chapterWordCount} 字</span>
          <span className={`status-text ${saveStatus.includes("已") ? "success" : ""}`}>
            {saveStatus}
          </span>
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
            >
              退回草稿
            </button>
          ) : null}
          {chapterStatus === "completed" ? (
            <button
              className="button ghost sm"
              type="button"
              onClick={() => handleStatusChange("drafting")}
            >
              重新编辑
            </button>
          ) : null}
          {chapterStatus === "drafting" ? (
            <button
              className="button secondary sm"
              type="button"
              onClick={() => handleStatusChange("review")}
            >
              送审
            </button>
          ) : null}
          {chapterStatus === "review" ? (
            <button
              className="button sm"
              type="button"
              onClick={() => handleStatusChange("completed")}
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
          onChange={(event) => {
            setTitle(event.target.value);
            setSaveStatus("等待保存...");
          }}
        />

        <textarea
          className="textarea editor-area"
          placeholder="正文内容"
          value={content}
          onChange={(event) => {
            setContent(event.target.value);
            setSaveStatus("等待保存...");
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
              {qualityError ? <p className="muted error-text">{qualityError}</p> : null}
              {visibleChecks.map((check) => {
                const finished = check.status === "completed" || check.status === "skipped";
                const busy = runningCheckId === check.id;
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
                          <button className="button sm" type="button" disabled={Boolean(runningCheckId)} onClick={() => void runQualityCheck(check)}>
                            {busy ? "执行中..." : "执行"}
                          </button>
                          <button className="button ghost sm" type="button" disabled={Boolean(runningCheckId)} onClick={() => void markQualityCheck(check, "skipped")}>
                            跳过
                          </button>
                        </>
                      ) : check.status === "skipped" ? (
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

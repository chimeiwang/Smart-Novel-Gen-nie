"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ChapterSaveCoordinator,
  createBestEffortChapterDraftStorage,
  type ChapterSaveState,
} from "@/features/editor/chapter-save-coordinator";
import { browserApi } from "@/lib/api/browser";
import { createClientRequestId } from "@/lib/api/client-request-id";
import { requireApiData } from "@/lib/api/response";
import { countTextLength } from "@/shared/lib/word-count";
import { parseSseEvent } from "@/shared/contracts/sse-events";
import {
  buildSelectionIdentity,
  type SelectionIdentity,
} from "./selection-range";
import {
  ShortVersionDrawer,
  type ShortVersionDiff,
  type ShortVersionSummary,
} from "./short-version-drawer";
import {
  canRunDocumentAction,
  canStartSelectionEdit,
  type ConfirmedVersionAction,
  versionActionForInspection,
} from "./short-workspace-state";
import {
  decideShortRunOutcome,
  type ShortRunOutcome,
} from "./short-run-outcome";

type DocumentType = "outline" | "manuscript";

type VersionListItem = ShortVersionSummary & {
  baseVersionId: string | null;
  sourceOutlineVersionId: string | null;
  wordCount: number;
};

type PreviewState = {
  documentType: DocumentType;
  chapterId: string | null;
  baseVersionId: string | null;
  expectedUpdatedAt: string;
  contentHash: string;
  confirmationHash: string;
  diff: ShortVersionDiff;
};

type PendingVersionAction = {
  action: ConfirmedVersionAction;
  targetVersionId: string | null;
  clientRequestId: string;
  preview?: PreviewState;
};

type ShortMediumWorkspaceProps = {
  userId: string;
  novelId: string;
  targetTotalWordCount: number;
  chapter: {
    id: string;
    title: string;
    content: string;
    updatedAt: string;
  };
};

function latestApplied(versions: VersionListItem[]): VersionListItem | null {
  return versions
    .filter((version) => version.status === "applied")
    .sort((left, right) => right.versionNumber - left.versionNumber)[0] ?? null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请稍后重试。";
}

async function waitForTerminalOutcome(taskId: string): Promise<ShortRunOutcome> {
  return await new Promise<ShortRunOutcome>((resolve, reject) => {
    const source = new EventSource(
      `/api/v1/writing/runs/${encodeURIComponent(taskId)}/events`,
      { withCredentials: true },
    );
    const timeout = window.setTimeout(() => {
      source.close();
      reject(new Error("等待 Agent 任务结果超时，请刷新后重试。"));
    }, 30 * 60_000);
    const finish = (outcome: ShortRunOutcome) => {
      window.clearTimeout(timeout);
      source.close();
      resolve(outcome);
    };
    source.addEventListener("run_outcome", (event) => {
      if (!(event instanceof MessageEvent)) return;
      try {
        const parsed = parseSseEvent(JSON.parse(event.data), "run_outcome");
        if (!parsed || parsed.type !== "run_outcome") return;
        if (decideShortRunOutcome(parsed).kind !== "continue") {
          finish(parsed);
        }
      } catch {
        // 非法控制帧不改变生命周期，等待下一次权威结果或自动重连。
      }
    });
  });
}

export function ShortMediumWorkspace({
  userId,
  novelId,
  targetTotalWordCount,
  chapter,
}: ShortMediumWorkspaceProps) {
  const [activeDocument, setActiveDocument] = useState<DocumentType>("outline");
  const [outline, setOutline] = useState("");
  const [outlineUpdatedAt, setOutlineUpdatedAt] = useState<string | null>(null);
  const [manuscript, setManuscript] = useState(chapter.content);
  const [outlineSaveState, setOutlineSaveState] = useState<ChapterSaveState>("saved");
  const [manuscriptSaveState, setManuscriptSaveState] = useState<ChapterSaveState>("saved");
  const [outlineVersions, setOutlineVersions] = useState<VersionListItem[]>([]);
  const [manuscriptVersions, setManuscriptVersions] = useState<VersionListItem[]>([]);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [diff, setDiff] = useState<ShortVersionDiff | null>(null);
  const [pendingVersionAction, setPendingVersionAction] =
    useState<PendingVersionAction | null>(null);
  const [instruction, setInstruction] = useState("");
  const [selection, setSelection] = useState<SelectionIdentity | null>(null);
  const [runningTaskId, setRunningTaskId] = useState<string | null>(null);
  const [checkReport, setCheckReport] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const outlineCoordinatorRef = useRef<ChapterSaveCoordinator | null>(null);
  const manuscriptCoordinatorRef = useRef<ChapterSaveCoordinator | null>(null);
  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  const initialOutlineContentRef = useRef("");

  const currentOutlineVersion = useMemo(
    () => latestApplied(outlineVersions),
    [outlineVersions],
  );
  const currentManuscriptVersion = useMemo(
    () => latestApplied(manuscriptVersions),
    [manuscriptVersions],
  );
  const activeVersions = activeDocument === "outline"
    ? outlineVersions
    : manuscriptVersions;
  const activeSaveState = activeDocument === "outline"
    ? outlineSaveState
    : manuscriptSaveState;
  const activeContent = activeDocument === "outline" ? outline : manuscript;
  const currentVersion = activeDocument === "outline"
    ? currentOutlineVersion
    : currentManuscriptVersion;

  const loadVersions = useCallback(async () => {
    const [outlineResult, manuscriptResult] = await Promise.all([
      browserApi.GET("/api/v1/novels/{novel_id}/versions", {
        params: {
          path: { novel_id: novelId },
          query: { documentType: "outline" },
        },
      }),
      browserApi.GET("/api/v1/novels/{novel_id}/versions", {
        params: {
          path: { novel_id: novelId },
          query: { documentType: "manuscript", chapterId: chapter.id },
        },
      }),
    ]);
    setOutlineVersions(requireApiData(outlineResult));
    setManuscriptVersions(requireApiData(manuscriptResult));
  }, [chapter.id, novelId]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const planning = requireApiData(await browserApi.GET(
          "/api/v1/novels/{novel_id}/workspace/planning",
          { params: { path: { novel_id: novelId } } },
        ));
        if (!active) return;
        initialOutlineContentRef.current = planning.outline?.content ?? "";
        setOutline(initialOutlineContentRef.current);
        setOutlineUpdatedAt(planning.outline?.updatedAt ?? null);
        await loadVersions();
      } catch (loadError) {
        if (active) setError(errorMessage(loadError));
      }
    })();
    return () => {
      active = false;
    };
  }, [loadVersions, novelId]);

  useEffect(() => {
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: { title: chapter.title, content: chapter.content },
      initialUpdatedAt: chapter.updatedAt,
      delayMs: 1_200,
      storage: createBestEffortChapterDraftStorage(
        window,
        `inkforge:short-medium:${userId}:${novelId}:manuscript`,
      ),
      save: async (request) => requireApiData(await browserApi.PATCH(
        "/api/v1/chapters/{chapter_id}",
        {
          params: { path: { chapter_id: chapter.id } },
          body: request,
        },
      )),
      onStateChange: setManuscriptSaveState,
    });
    manuscriptCoordinatorRef.current = coordinator;
    let active = true;
    queueMicrotask(() => {
      if (!active || manuscriptCoordinatorRef.current !== coordinator) return;
      setManuscript(coordinator.snapshot.content);
      setManuscriptSaveState(coordinator.state);
    });
    return () => {
      active = false;
      if (manuscriptCoordinatorRef.current === coordinator) {
        manuscriptCoordinatorRef.current = null;
      }
      void coordinator.dispose();
    };
  }, [chapter.content, chapter.id, chapter.title, chapter.updatedAt, novelId, userId]);

  useEffect(() => {
    if (outlineUpdatedAt === null) return;
    const initialContent = initialOutlineContentRef.current;
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: { title: "蓝图", content: initialContent },
      initialUpdatedAt: outlineUpdatedAt,
      delayMs: 1_200,
      storage: createBestEffortChapterDraftStorage(
        window,
        `inkforge:short-medium:${userId}:${novelId}:outline`,
      ),
      save: async (request) => requireApiData(await browserApi.PUT(
        "/api/v1/novels/{novel_id}/outline",
        {
          params: { path: { novel_id: novelId } },
          body: {
            content: request.content,
            expectedUpdatedAt: request.expectedUpdatedAt,
          },
        },
      )),
      onStateChange: setOutlineSaveState,
    });
    outlineCoordinatorRef.current = coordinator;
    let active = true;
    queueMicrotask(() => {
      if (!active || outlineCoordinatorRef.current !== coordinator) return;
      setOutline(coordinator.snapshot.content);
      setOutlineSaveState(coordinator.state);
    });
    return () => {
      active = false;
      if (outlineCoordinatorRef.current === coordinator) {
        outlineCoordinatorRef.current = null;
      }
      void coordinator.dispose();
    };
  }, [novelId, outlineUpdatedAt, userId]);

  const updateContent = (value: string) => {
    setSelection(null);
    if (activeDocument === "outline") {
      setOutline(value);
      outlineCoordinatorRef.current?.schedule({ title: "蓝图", content: value });
    } else {
      setManuscript(value);
      manuscriptCoordinatorRef.current?.schedule({
        title: chapter.title,
        content: value,
      });
    }
  };

  const refreshSelection = async () => {
    const editor = editorRef.current;
    if (!editor) return;
    try {
      setSelection(await buildSelectionIdentity(
        activeContent,
        editor.selectionStart,
        editor.selectionEnd,
      ));
    } catch {
      setSelection(null);
    }
  };

  const previewSubmit = async () => {
    if (!canRunDocumentAction(activeSaveState)) return;
    setBusy(true);
    setError(null);
    try {
      const preview = requireApiData(await browserApi.POST(
        "/api/v1/novels/{novel_id}/versions/preview",
        {
          params: { path: { novel_id: novelId } },
          body: {
            documentType: activeDocument,
            chapterId: activeDocument === "manuscript" ? chapter.id : null,
            baseVersionId: currentVersion?.id ?? null,
          },
        },
      ));
      if (!preview.dirty) {
        setError("工作稿与当前版本一致，没有需要提交的变化。");
        return;
      }
      const state: PreviewState = {
        ...preview,
        diff: preview.diff,
      };
      setDiff(preview.diff);
      setPendingVersionAction({
        action: "submit",
        targetVersionId: null,
        clientRequestId: createClientRequestId(),
        preview: state,
      });
      setVersionsOpen(true);
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setBusy(false);
    }
  };

  const inspectVersion = async (versionId: string) => {
    setBusy(true);
    setError(null);
    try {
      const detail = requireApiData(await browserApi.GET(
        "/api/v1/novels/{novel_id}/versions/{version_id}",
        {
          params: {
            path: { novel_id: novelId, version_id: versionId },
          },
        },
      ));
      let inspectedDiff = detail.diff;
      if (currentVersion && currentVersion.id !== versionId) {
        inspectedDiff = requireApiData(await browserApi.GET(
          "/api/v1/novels/{novel_id}/version-diff",
          {
            params: {
              path: { novel_id: novelId },
              query: {
                fromVersionId: currentVersion.id,
                toVersionId: versionId,
              },
            },
          },
        ));
      }
      if (!inspectedDiff) {
        setError("该版本没有可展示的差异。");
        return;
      }
      setDiff(inspectedDiff);
      const action = versionActionForInspection({
        versionId,
        status: detail.status,
        baseVersionId: detail.baseVersionId,
        currentVersionId: currentVersion?.id ?? null,
      });
      setPendingVersionAction(action ? {
        action,
        targetVersionId: versionId,
        clientRequestId: createClientRequestId(),
      } : null);
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setBusy(false);
    }
  };

  const confirmVersionAction = async (
    action: ConfirmedVersionAction,
    confirmationHash: string,
  ) => {
    const pending = pendingVersionAction;
    if (!pending || pending.action !== action || !canRunDocumentAction(activeSaveState)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (action === "submit" && pending.preview) {
        await browserApi.POST("/api/v1/novels/{novel_id}/versions", {
          params: { path: { novel_id: novelId } },
          body: {
            documentType: activeDocument,
            chapterId: activeDocument === "manuscript" ? chapter.id : null,
            clientRequestId: pending.clientRequestId,
            baseVersionId: pending.preview.baseVersionId,
            expectedUpdatedAt: pending.preview.expectedUpdatedAt,
            contentHash: pending.preview.contentHash,
            confirmationHash,
          },
        }).then(requireApiData);
      } else if (pending.targetVersionId) {
        const endpoint = action === "adopt"
          ? "/api/v1/novels/{novel_id}/versions/{version_id}/adopt" as const
          : "/api/v1/novels/{novel_id}/versions/{version_id}/restore" as const;
        await browserApi.POST(endpoint, {
          params: {
            path: {
              novel_id: novelId,
              version_id: pending.targetVersionId,
            },
          },
          body: {
            documentType: activeDocument,
            chapterId: activeDocument === "manuscript" ? chapter.id : null,
            clientRequestId: pending.clientRequestId,
            baseVersionId: currentVersion?.id ?? null,
            confirmationHash,
          },
        }).then(requireApiData);
      }
      await loadVersions();
      setPendingVersionAction(null);
      setDiff(null);
      setVersionsOpen(false);
      window.location.reload();
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setBusy(false);
    }
  };

  const startAgent = async (
    operation:
      | "generate_outline"
      | "generate_manuscript"
      | "replace_selection"
      | "full_check",
  ) => {
    if (!canRunDocumentAction(activeSaveState)) return;
    if (
      operation === "replace_selection"
      && !canStartSelectionEdit(Boolean(selection), instruction)
    ) {
      setError("请先选择需要修改的文字，并填写本轮修改要求。");
      return;
    }
    const documentType: DocumentType = operation === "generate_outline"
      ? "outline"
      : operation === "generate_manuscript" || operation === "full_check"
        ? "manuscript"
        : activeDocument;
    const base = documentType === "outline"
      ? currentOutlineVersion
      : currentManuscriptVersion;
    const sourceOutline = currentOutlineVersion;
    if (operation === "generate_manuscript" && !sourceOutline) {
      setError("请先提交并确认一个蓝图版本。");
      return;
    }
    if (
      operation === "generate_manuscript"
      && !canRunDocumentAction(outlineSaveState)
    ) {
      setError("蓝图工作稿尚未保存，请等待保存完成后再生成正文。");
      return;
    }
    setBusy(true);
    setError(null);
    setCheckReport(null);
    try {
      if (operation === "generate_manuscript") {
        const outlinePreview = requireApiData(await browserApi.POST(
          "/api/v1/novels/{novel_id}/versions/preview",
          {
            params: { path: { novel_id: novelId } },
            body: {
              documentType: "outline",
              chapterId: null,
              baseVersionId: sourceOutline?.id ?? null,
            },
          },
        ));
        if (outlinePreview.dirty) {
          throw new Error("蓝图工作稿有尚未提交的修改，请先提交蓝图版本。");
        }
      }
      const cleanPreview = requireApiData(await browserApi.POST(
        "/api/v1/novels/{novel_id}/versions/preview",
        {
          params: { path: { novel_id: novelId } },
          body: {
            documentType,
            chapterId: documentType === "manuscript" ? chapter.id : null,
            baseVersionId: base?.id ?? null,
          },
        },
      ));
      if (cleanPreview.dirty) {
        throw new Error("工作稿有尚未提交的修改，请先提交版本再启动 Agent。");
      }
      const run = requireApiData(await browserApi.POST("/api/v1/writing/runs", {
        body: {
          clientRequestId: createClientRequestId(),
          workflow: "short_medium",
          novelId,
          operation,
          documentType,
          chapterId: documentType === "manuscript" ? chapter.id : null,
          baseVersionId: base?.id ?? null,
          sourceOutlineVersionId: documentType === "manuscript"
            ? sourceOutline?.id ?? null
            : null,
          selectionStart: operation === "replace_selection"
            ? selection?.selectionStart ?? null
            : null,
          selectionEnd: operation === "replace_selection"
            ? selection?.selectionEnd ?? null
            : null,
          selectedTextHash: operation === "replace_selection"
            ? selection?.selectedTextHash ?? null
            : null,
          userInstruction: instruction.trim() || null,
        },
      }));
      setRunningTaskId(run.id);
      await waitForTerminalOutcome(run.id);
      const terminal = requireApiData(await browserApi.GET(
        "/api/v1/writing/runs/{task_id}",
        { params: { path: { task_id: run.id } } },
      ));
      const outcomeDecision = decideShortRunOutcome(terminal.outcome);
      if (outcomeDecision.kind === "failed") {
        throw new Error(
          terminal.error
            ? JSON.stringify(terminal.error, null, 2)
            : `Agent 任务失败（${outcomeDecision.code}）。`,
        );
      }
      if (outcomeDecision.kind === "inconsistent") {
        throw new Error(
          `任务状态对账异常（${outcomeDecision.code}），不能把本次运行显示为成功。`,
        );
      }
      if (outcomeDecision.kind === "continue") {
        throw new Error("任务流已结束，但权威状态仍未收敛，请刷新后重试。");
      }
      if (outcomeDecision.resultKind === "check_report" && terminal.checkReport) {
        setCheckReport(JSON.stringify(terminal.checkReport, null, 2));
      }
      await loadVersions();
      const candidateVersionId = outcomeDecision.resultKind === "short_candidate"
        ? outcomeDecision.resultId
        : null;
      setVersionsOpen(Boolean(candidateVersionId));
      if (candidateVersionId) {
        await inspectVersion(candidateVersionId);
      }
    } catch (actionError) {
      setError(errorMessage(actionError));
    } finally {
      setRunningTaskId(null);
      setBusy(false);
    }
  };

  return (
    <div className="short-medium-shell">
      <section className="panel short-medium-editor-panel">
        <header className="short-medium-toolbar">
          <div className="short-document-tabs" role="tablist" aria-label="中短篇文档">
            {(["outline", "manuscript"] as const).map((documentType) => (
              <button
                key={documentType}
                className={activeDocument === documentType ? "active" : ""}
                type="button"
                role="tab"
                aria-selected={activeDocument === documentType}
                onClick={() => {
                  setActiveDocument(documentType);
                  setSelection(null);
                  setDiff(null);
                  setPendingVersionAction(null);
                }}
              >
                {documentType === "outline" ? "蓝图" : "正文"}
              </button>
            ))}
          </div>
          <div className="row">
            <span className={`badge save-${activeSaveState}`}>
              {activeSaveState === "saved" ? "已保存工作稿" : "工作稿保存中"}
            </span>
            <span className="badge">{countTextLength(activeContent)} 字</span>
            <span className="badge">
              {currentVersion ? `当前 v${currentVersion.versionNumber}` : "尚无版本"}
            </span>
            <button
              className="button secondary"
              type="button"
              onClick={() => {
                setVersionsOpen(true);
                setDiff(null);
                setPendingVersionAction(null);
              }}
            >
              版本
            </button>
            <button
              className="button"
              type="button"
              disabled={busy || !canRunDocumentAction(activeSaveState)}
              onClick={() => void previewSubmit()}
            >
              提交版本
            </button>
          </div>
        </header>

        <textarea
          ref={editorRef}
          className="textarea short-medium-editor"
          aria-label={activeDocument === "outline" ? "蓝图工作稿" : "正文工作稿"}
          value={activeContent}
          onChange={(event) => updateContent(event.target.value)}
          onSelect={() => void refreshSelection()}
          placeholder={activeDocument === "outline"
            ? "在这里编辑完整故事蓝图……"
            : "在这里编辑完整正文……"}
        />
      </section>

      <aside className="panel short-medium-agent-panel">
        <div className="panel-body stack">
          <div>
            <h2 className="title-md">短篇 Agent</h2>
            <p className="muted">
              Agent 每次只生成候选版本。不会自动采用，也不会在一次任务里继续下一阶段。
            </p>
          </div>
          <label className="stack">
            <span>本轮要求</span>
            <textarea
              className="textarea textarea-resize"
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              placeholder="例如：加强人物在高潮处的两难选择"
            />
          </label>
          <div className="short-agent-actions">
            {activeDocument === "outline" ? (
              <button
                className="button"
                type="button"
                disabled={busy || !canRunDocumentAction(activeSaveState)}
                onClick={() => void startAgent("generate_outline")}
              >
                生成蓝图候选
              </button>
            ) : (
              <button
                className="button"
                type="button"
                disabled={
                  busy
                  || !currentOutlineVersion
                  || !canRunDocumentAction(activeSaveState)
                  || !canRunDocumentAction(outlineSaveState)
                }
                onClick={() => void startAgent("generate_manuscript")}
              >
                生成正文候选
              </button>
            )}
            <button
              className="button secondary"
              type="button"
              disabled={
                busy
                || !canStartSelectionEdit(Boolean(selection), instruction)
                || !currentVersion
                || !canRunDocumentAction(activeSaveState)
              }
              onClick={() => void startAgent("replace_selection")}
            >
              AI 修改选中内容
            </button>
            <button
              className="button secondary"
              type="button"
              disabled={busy || !currentManuscriptVersion || !canRunDocumentAction(manuscriptSaveState)}
              onClick={() => void startAgent("full_check")}
            >
              全文检查
            </button>
          </div>
          <p className="muted">
            目标 {targetTotalWordCount} 字
            {selection
              ? `；已选择 ${selection.selectionEnd - selection.selectionStart} 个码点`
              : "；未选择修改区域"}
          </p>
          {runningTaskId ? <p className="agent-running">Agent 正在执行：{runningTaskId}</p> : null}
          {checkReport ? <pre className="short-check-report">{checkReport}</pre> : null}
          {error ? <p className="form-error" role="alert">{error}</p> : null}
        </div>
      </aside>

      <ShortVersionDrawer
        open={versionsOpen}
        title={activeDocument === "outline" ? "蓝图" : "正文"}
        versions={activeVersions}
        diff={diff}
        pendingAction={pendingVersionAction?.action ?? null}
        currentOutlineVersionId={currentOutlineVersion?.id ?? null}
        disabled={busy || !canRunDocumentAction(activeSaveState)}
        onInspect={(versionId) => void inspectVersion(versionId)}
        onConfirm={(action, confirmationHash) => {
          void confirmVersionAction(action, confirmationHash);
        }}
        onClose={() => {
          setVersionsOpen(false);
          setDiff(null);
          setPendingVersionAction(null);
        }}
      />
    </div>
  );
}

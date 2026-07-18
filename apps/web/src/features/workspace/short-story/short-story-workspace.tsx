"use client";

import type { components } from "@inkforge/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LogoutButton } from "@/features/auth/user-menu";
import { browserApi } from "@/lib/api/browser";
import { CoreApiPageError, requireApiData } from "@/lib/api/response";
import { countTextLength } from "@/shared/lib/word-count";
import { buildWorkspaceChapterHref } from "../workspace-view";
import {
  classifyClientRequestFailure,
  StableClientRequestIds,
} from "./short-story-action-ids";
import { ShortStoryContent } from "./short-story-content";
import {
  applySavedOutlineToAggregate,
  createOutlineEditorBase,
  type OutlineEditorBase,
  shouldAdoptAggregateOutline,
} from "./short-story-outline-lifecycle";
import {
  appendOutlineItem,
  createEditableOutlineSections,
  type EditableOutlineSection,
  moveOutlineItem,
  removeOutlineItem,
  serializeOutlineSections,
  updateOutlineItem,
} from "./short-story-outline-state";
import {
  getAcceptedPollingStatus,
  getShortStoryPollDelay,
  shouldPollShortStory,
  shouldRefreshOnVisibilityChange,
  type ShortStoryCommandStatus,
} from "./short-story-polling";
import {
  canRestoreOutlineRevision,
  shouldLoadOutlineRevisions,
  type ShortStoryPane,
} from "./short-story-revision-policy";
import { buildWritingBibleTargetUpdate } from "./short-story-settings";
import {
  deriveShortStoryActions,
  isShortStoryInteractionLocked,
  isValidShortStoryTarget,
} from "./short-story-workflow-state";
import "./short-story-workspace.css";

type ShortStoryWorkspaceProps = {
  bootstrap: components["schemas"]["WorkspaceBootstrapResponse"];
};
type ShortStoryAggregate = components["schemas"]["ShortStoryArtifactsResponse"];
type ShortStoryArtifact = components["schemas"]["ShortStoryArtifactResponse"];
type ShortStoryOutlineDraft = components["schemas"]["ShortStoryOutlineDraft"];
type ShortStoryChapterDraft = components["schemas"]["ShortStoryChapterDraft"];
type ShortStoryAnchors = components["schemas"]["ShortStoryAnchors"];
type ShortStoryTask = components["schemas"]["ShortStoryTaskStatus"];
type RevisionSummary = components["schemas"]["ReviewArtifactRevisionSummary"];
type RevisionDetail = components["schemas"]["ReviewArtifactRevisionDetail"];
type ArtifactDecision = components["schemas"]["ReviewArtifactDecisionRequest"]["decision"];
type ActivePane = ShortStoryPane;

const ACTIVE_COMMAND_STATUSES = new Set<ShortStoryCommandStatus>([
  "pending",
  "submitted",
  "processing",
]);

const ANCHOR_FIELDS: Array<{ key: keyof ShortStoryAnchors; label: string }> = [
  { key: "mustKeep", label: "必须保留" },
  { key: "confirmed", label: "已经确认" },
  { key: "avoid", label: "明确不要" },
];

function getOutlinePayload(artifact: ShortStoryArtifact | null | undefined): ShortStoryOutlineDraft | null {
  return artifact?.payload.kind === "outline_draft" ? artifact.payload : null;
}

function getDraftPayload(artifact: ShortStoryArtifact | null | undefined): ShortStoryChapterDraft | null {
  return artifact?.payload.kind === "chapter_draft" ? artifact.payload : null;
}

function getRevisionContent(revision: RevisionDetail | null): string | null {
  if (!revision) return null;
  const payload = revision.payload;
  if (payload.kind === "outline_draft" || payload.kind === "chapter_draft") {
    return typeof payload.content === "string" ? payload.content : null;
  }
  return null;
}

function getLatestTask(aggregate: ShortStoryAggregate | null): ShortStoryTask | null {
  return aggregate?.latestTask
    ?? aggregate?.workflowSession?.currentTask
    ?? aggregate?.workflowSession?.lastTask
    ?? null;
}

function formatArtifactStatus(status: ShortStoryArtifact["status"]): string {
  return {
    draft: "生成中",
    under_review: "全稿审核中",
    awaiting_user: "等待你确认",
    applying: "正在应用",
    applied: "已确认",
  }[status];
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function splitAnchorLines(value: string): string[] {
  return value
    .split(/\r?\n/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message.trim() ? error.message : fallback;
}

async function submitWithStableClientRequestId<T>(
  requestIds: StableClientRequestIds,
  actionKey: string,
  submit: (clientRequestId: string) => Promise<T>,
): Promise<T> {
  const clientRequestId = requestIds.get(actionKey);
  try {
    const result = await submit(clientRequestId);
    requestIds.settle(actionKey, "accepted");
    return result;
  } catch (error) {
    requestIds.settle(
      actionKey,
      classifyClientRequestFailure(
        error instanceof CoreApiPageError ? error.status : undefined,
      ),
    );
    throw error;
  }
}

export function ShortStoryWorkspace({ bootstrap }: ShortStoryWorkspaceProps) {
  const { novel, currentChapter } = bootstrap;
  const router = useRouter();
  const [aggregate, setAggregate] = useState<ShortStoryAggregate | null>(null);
  const aggregateRef = useRef<ShortStoryAggregate | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [consecutiveErrors, setConsecutiveErrors] = useState(0);
  const refreshInFlightRef = useRef<Promise<ShortStoryAggregate | null> | null>(null);
  const writingSessionIdRef = useRef<string | null>(null);
  const pollingTimerRef = useRef<number | null>(null);
  const [pageVisible, setPageVisible] = useState(
    () => typeof document === "undefined" || document.visibilityState === "visible",
  );

  const [activePane, setActivePane] = useState<ActivePane>(
    currentChapter?.content.trim() ? "formal" : "outline",
  );
  const [outlineDisplayMode, setOutlineDisplayMode] = useState<"read" | "edit">("read");
  const [optimisticCommand, setOptimisticCommand] = useState<{
    id: string;
    status: ShortStoryCommandStatus;
  } | null>(null);
  const optimisticCommandRef = useRef(optimisticCommand);

  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const pendingActionRef = useRef<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [requestIds] = useState(() => new StableClientRequestIds());

  const [titleInput, setTitleInput] = useState(novel.name);
  const [displayTitle, setDisplayTitle] = useState(novel.name);
  const [titleUpdatedAt, setTitleUpdatedAt] = useState(novel.updatedAt);
  const [titleConflict, setTitleConflict] = useState(false);
  const [targetInput, setTargetInput] = useState(String(bootstrap.targetTotalWordCount ?? ""));
  const [targetWordCount, setTargetWordCount] = useState(bootstrap.targetTotalWordCount);

  const [outlineCorePremise, setOutlineCorePremise] = useState("");
  const [outlineAnchors, setOutlineAnchors] = useState<ShortStoryAnchors>({
    mustKeep: [],
    confirmed: [],
    avoid: [],
  });
  const [outlineSections, setOutlineSections] = useState<EditableOutlineSection[]>([]);
  const [outlineChangeSummary, setOutlineChangeSummary] = useState("用户直接编辑");
  const [outlineDirty, setOutlineDirty] = useState(false);
  const outlineDirtyRef = useRef(false);
  const [editorBaseArtifactId, setEditorBaseArtifactId] = useState<string | null>(null);
  const [editorBaseRevision, setEditorBaseRevision] = useState<number | null>(null);
  const editorBaseRef = useRef<OutlineEditorBase | null>(null);
  const [outlineConflictBase, setOutlineConflictBase] = useState<OutlineEditorBase | null>(null);

  const [outlineRevisionRequest, setOutlineRevisionRequest] = useState("");
  const [draftRevisionRequest, setDraftRevisionRequest] = useState("");
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [revisionsLoading, setRevisionsLoading] = useState(false);
  const [revisionDetail, setRevisionDetail] = useState<RevisionDetail | null>(null);
  const [revisionLoading, setRevisionLoading] = useState(false);
  const revisionLoadTokenRef = useRef(0);

  const updateOutlineEditorBase = useCallback((base: OutlineEditorBase | null) => {
    editorBaseRef.current = base;
    setEditorBaseArtifactId(base?.artifactId ?? null);
    setEditorBaseRevision(base?.revision ?? null);
  }, []);

  const synchronizeOutlineEditor = useCallback((next: ShortStoryAggregate) => {
    const artifact = next.outline;
    const payload = getOutlinePayload(artifact);
    if (!artifact || !payload || !shouldAdoptAggregateOutline({
      dirty: outlineDirtyRef.current,
      base: editorBaseRef.current,
      next: artifact,
    })) return;

    updateOutlineEditorBase(createOutlineEditorBase(artifact));
    setOutlineConflictBase(null);
    setOutlineCorePremise(payload.corePremise);
    setOutlineAnchors({
      mustKeep: [...(payload.anchors.mustKeep ?? [])],
      confirmed: [...(payload.anchors.confirmed ?? [])],
      avoid: [...(payload.anchors.avoid ?? [])],
    });
    setOutlineSections(createEditableOutlineSections(payload.sections));
    setOutlineChangeSummary(payload.changeSummary || "用户直接编辑");
  }, [updateOutlineEditorBase]);

  const applyAggregate = useCallback((next: ShortStoryAggregate) => {
    const previous = aggregateRef.current;
    aggregateRef.current = next;
    setAggregate(next);
    synchronizeOutlineEditor(next);
    if (next.workflowSession?.id) writingSessionIdRef.current = next.workflowSession.id;

    if (next.chapterDraft && !previous?.chapterDraft) {
      setActivePane("draft");
      revisionLoadTokenRef.current += 1;
      setRevisions([]);
      setRevisionsLoading(false);
      setRevisionDetail(null);
    }
    if (!next.outline && previous?.outline) {
      revisionLoadTokenRef.current += 1;
      setRevisions([]);
      setRevisionsLoading(false);
      setRevisionDetail(null);
    }
    if (
      previous?.chapterDraft
      && previous?.chapterDraft?.status !== "applied"
      && next.chapterDraft?.status === "applied"
    ) {
      setActivePane("formal");
      router.refresh();
    }

    const optimistic = optimisticCommandRef.current;
    const latestTask = getLatestTask(next);
    if (optimistic && latestTask?.latestCommandId === optimistic.id) {
      if (ACTIVE_COMMAND_STATUSES.has(latestTask.latestCommandStatus)) {
        const tracked = { id: optimistic.id, status: latestTask.latestCommandStatus };
        optimisticCommandRef.current = tracked;
        setOptimisticCommand(tracked);
      } else {
        optimisticCommandRef.current = null;
        setOptimisticCommand(null);
      }
    }
  }, [router, synchronizeOutlineEditor]);

  const refreshAggregate = useCallback((): Promise<ShortStoryAggregate | null> => {
    const existing = refreshInFlightRef.current;
    if (existing) return existing;

    const request = (async () => {
      try {
        const next = requireApiData(await browserApi.GET(
          "/api/v1/novels/{novel_id}/short-story/artifacts",
          { params: { path: { novel_id: novel.id } } },
        ));
        applyAggregate(next);
        setConsecutiveErrors(0);
        setLoadError(null);
        return next;
      } catch (error) {
        setConsecutiveErrors((current) => current + 1);
        setLoadError(getErrorMessage(error, "读取中短篇写作状态失败"));
        return null;
      } finally {
        setInitialLoading(false);
      }
    })();
    refreshInFlightRef.current = request;
    void request.finally(() => {
      if (refreshInFlightRef.current === request) refreshInFlightRef.current = null;
    });
    return request;
  }, [applyAggregate, novel.id]);

  const refreshAfterMutation = useCallback(async (): Promise<ShortStoryAggregate | null> => {
    const existing = refreshInFlightRef.current;
    if (existing) await existing;
    return refreshAggregate();
  }, [refreshAggregate]);

  useEffect(() => {
    const timer = window.setTimeout(() => void refreshAggregate(), 0);
    return () => window.clearTimeout(timer);
  }, [refreshAggregate]);

  const clearPollingTimer = useCallback(() => {
    if (pollingTimerRef.current === null) return;
    window.clearTimeout(pollingTimerRef.current);
    pollingTimerRef.current = null;
  }, []);

  const latestTask = getLatestTask(aggregate);
  const effectiveCommandStatus = optimisticCommand?.status
    ?? latestTask?.latestCommandStatus
    ?? null;
  const artifactStatuses = useMemo(
    () => [aggregate?.outline?.status ?? null, aggregate?.chapterDraft?.status ?? null],
    [aggregate?.chapterDraft?.status, aggregate?.outline?.status],
  );
  const pollingRequired = consecutiveErrors > 0 || shouldPollShortStory({
    commandStatus: effectiveCommandStatus,
    taskPhase: latestTask?.phase ?? null,
    artifactStatuses,
  });

  useEffect(() => {
    clearPollingTimer();
    if (!pollingRequired) return clearPollingTimer;
    pollingTimerRef.current = window.setTimeout(
      () => {
        pollingTimerRef.current = null;
        void refreshAggregate();
      },
      getShortStoryPollDelay({
        visible: pageVisible,
        consecutiveErrors,
      }),
    );
    return clearPollingTimer;
  }, [
    aggregate,
    clearPollingTimer,
    consecutiveErrors,
    pageVisible,
    pollingRequired,
    refreshAggregate,
  ]);

  useEffect(() => {
    const initiallyVisible = document.visibilityState === "visible";
    let wasVisible = initiallyVisible;
    clearPollingTimer();
    const handleVisibilityChange = () => {
      const isVisible = document.visibilityState === "visible";
      clearPollingTimer();
      setPageVisible(isVisible);
      if (shouldRefreshOnVisibilityChange(wasVisible, isVisible)) {
        void refreshAggregate();
      }
      wasVisible = isVisible;
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange);
  }, [clearPollingTimer, refreshAggregate]);

  const outlineArtifact = aggregate?.outline ?? null;
  const draftArtifact = aggregate?.chapterDraft ?? null;
  const loadOutlineRevisions = shouldLoadOutlineRevisions(activePane, outlineArtifact !== null);
  const outlineArtifactId = loadOutlineRevisions ? outlineArtifact?.id ?? null : null;
  const outlineArtifactRevision = loadOutlineRevisions ? outlineArtifact?.revision ?? null : null;

  useEffect(() => {
    if (activePane !== "outline" || !outlineArtifactId) return;

    let current = true;
    const timer = window.setTimeout(() => void (async () => {
      setRevisionsLoading(true);
      try {
        const next = requireApiData(await browserApi.GET(
          "/api/v1/review-artifacts/{artifact_id}/revisions",
          { params: { path: { artifact_id: outlineArtifactId } } },
        ));
        if (current) setRevisions(next);
      } catch (error) {
        if (current) setActionError(getErrorMessage(error, "读取草案版本失败"));
      } finally {
        if (current) setRevisionsLoading(false);
      }
    })(), 0);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [activePane, outlineArtifactId, outlineArtifactRevision]);

  const actions = deriveShortStoryActions({
    authoritativeStateReady: aggregate !== null,
    targetWordCount,
    chapterCount: bootstrap.chapters.length,
    outlineStatus: aggregate?.outline?.status ?? null,
    draftStatus: aggregate?.chapterDraft?.status ?? null,
    commandStatus: effectiveCommandStatus,
    taskPhase: latestTask?.phase ?? null,
  });
  const interactionLocked = isShortStoryInteractionLocked({
    pendingAction,
    commandStatus: effectiveCommandStatus,
    taskPhase: latestTask?.phase ?? null,
  });
  const legacyMultiChapter = bootstrap.chapters.length > 1;

  const markOutlineDirty = useCallback(() => {
    outlineDirtyRef.current = true;
    setOutlineDirty(true);
    setActionNotice(null);
  }, []);

  const runMutation = async (actionKey: string, mutation: () => Promise<void>) => {
    const currentTask = getLatestTask(aggregateRef.current);
    if (isShortStoryInteractionLocked({
      pendingAction: pendingActionRef.current,
      commandStatus: optimisticCommandRef.current?.status
        ?? currentTask?.latestCommandStatus
        ?? null,
      taskPhase: currentTask?.phase ?? null,
    })) return;
    pendingActionRef.current = actionKey;
    setPendingAction(actionKey);
    setActionError(null);
    setActionNotice(null);
    try {
      await mutation();
    } catch (error) {
      if (error instanceof CoreApiPageError && error.status === 409) {
        if (actionKey.startsWith("title:")) {
          setTitleConflict(true);
          setActionError("标题已在其他位置更新。请刷新页面同步标题后再修改，避免覆盖较新的内容。");
        } else {
          const refreshed = await refreshAfterMutation();
          const latestOutline = refreshed?.outline ?? aggregateRef.current?.outline ?? null;
          if (outlineDirtyRef.current && latestOutline) {
            setOutlineConflictBase(createOutlineEditorBase(latestOutline));
          }
          setActionError(
            outlineDirtyRef.current
              ? "服务端大纲已更新，你的本地编辑仍保留。请先查看最新 revision，再明确选择基于最新版重试。"
              : "服务端版本已更新，已刷新当前 revision，请重新执行操作。",
          );
        }
      } else {
        setActionError(getErrorMessage(error, "操作失败"));
      }
    } finally {
      pendingActionRef.current = null;
      setPendingAction(null);
    }
  };

  const trackAcceptedCommand = (commandId: string, status: ShortStoryCommandStatus) => {
    const tracked = { id: commandId, status: getAcceptedPollingStatus(status) };
    optimisticCommandRef.current = tracked;
    setOptimisticCommand(tracked);
  };

  const ensureWritingSession = async (): Promise<string> => {
    const existing = writingSessionIdRef.current ?? aggregateRef.current?.workflowSession?.id;
    if (existing) return existing;
    if (!currentChapter) throw new Error("中短篇正文占位章节不存在");

    const session = requireApiData(await browserApi.POST("/api/v1/writing/sessions", {
      body: {
        novelId: novel.id,
        chapterId: currentChapter.id,
        title: "中短篇创作",
      },
    }));
    writingSessionIdRef.current = session.id;
    return session.id;
  };

  const startOperation = (operation: "develop_short_outline" | "write_short_story") => {
    const operationLabel = operation === "develop_short_outline" ? "生成完整大纲" : "生成完整初稿";
    const operationRevision = aggregateRef.current?.outline?.revision ?? 0;
    const actionKey = `start:${operation}:${operationRevision}:${targetWordCount ?? "invalid"}`;
    void runMutation(actionKey, async () => {
      if (!aggregateRef.current) {
        throw new Error("尚未读取到权威工作流状态，请先重试读取状态");
      }
      if (legacyMultiChapter) {
        throw new Error("需整理为单一正文后才能启动新中短篇流程");
      }
      if (!isValidShortStoryTarget(targetWordCount)) {
        throw new Error("请先把目标字数修正到 6000～80000 字并保存");
      }
      if (!currentChapter) throw new Error("中短篇正文占位章节不存在");

      const writingSessionId = await ensureWritingSession();
      const accepted = await submitWithStableClientRequestId(
        requestIds,
        actionKey,
        async (clientRequestId) => requireApiData(await browserApi.POST("/api/v1/writing/runs", {
          body: {
            clientRequestId,
            novelId: novel.id,
            chapterId: currentChapter.id,
            writingSessionId,
            workflowKind: "short_medium",
            operation,
            targetWordCount,
            userMessage: operation === "develop_short_outline"
              ? "请根据原始灵感生成可供完整通读和确认的中短篇大纲。"
              : "请严格根据已批准大纲一次生成完整正文，并完成全稿审核。",
          },
        })),
      );
      trackAcceptedCommand(accepted.commandId, accepted.commandStatus);
      setActionNotice(`${operationLabel}任务已接受，正在后台处理。`);
      await refreshAfterMutation();
    });
  };

  const decideArtifact = (
    artifact: ShortStoryArtifact,
    decision: ArtifactDecision,
    userMessage?: string,
  ) => {
    const normalizedMessage = userMessage?.trim() ?? "";
    const actionKey = `decision:${artifact.id}:${artifact.revision}:${decision}:${normalizedMessage}`;
    void runMutation(actionKey, async () => {
      if (legacyMultiChapter) {
        throw new Error("需整理为单一正文后才能启动新中短篇流程");
      }
      const accepted = await submitWithStableClientRequestId(
        requestIds,
        actionKey,
        async (clientRequestId) => requireApiData(await browserApi.POST(
          "/api/v1/review-artifacts/{artifact_id}/decision",
          {
            params: { path: { artifact_id: artifact.id } },
            body: {
              clientRequestId,
              decision,
              expectedRevision: artifact.revision,
              ...(normalizedMessage ? { userMessage: normalizedMessage } : {}),
            },
          },
        )),
      );
      trackAcceptedCommand(accepted.commandId, accepted.status);
      setActionNotice("操作已接受，状态会自动更新。");
      await refreshAfterMutation();
    });
  };

  const saveOutline = () => {
    if (!editorBaseArtifactId || editorBaseRevision === null) return;
    void runMutation(`save-outline:${editorBaseArtifactId}:${editorBaseRevision}`, async () => {
      if (legacyMultiChapter) {
        throw new Error("需整理为单一正文后才能启动新中短篇流程");
      }
      const corePremise = outlineCorePremise.trim();
      if (!corePremise) throw new Error("核心前提不能为空");
      if (outlineSections.length === 0) throw new Error("大纲至少需要一个分节");
      if (outlineSections.some((section) => !section.title.trim() || !section.events.trim())) {
        throw new Error("每一节都需要标题和“发生了什么”");
      }

      const saved = requireApiData(await browserApi.PUT("/api/v1/review-artifacts/{artifact_id}/outline", {
        params: { path: { artifact_id: editorBaseArtifactId } },
        body: {
          expectedRevision: editorBaseRevision,
          corePremise,
          anchors: outlineAnchors,
          sections: serializeOutlineSections(outlineSections).map((section) => ({
            ...section,
            title: section.title.trim(),
            events: section.events.trim(),
          })),
          changeSummary: outlineChangeSummary.trim() || "用户直接编辑",
          anchorChanges: [],
        },
      }));
      const current = aggregateRef.current;
      if (!current) throw new Error("保存成功，但当前工作流状态尚未载入");
      outlineDirtyRef.current = false;
      setOutlineDirty(false);
      setOutlineConflictBase(null);
      applyAggregate(applySavedOutlineToAggregate(current, saved));
      setActionNotice("大纲编辑已保存为新的 revision。");
      await refreshAfterMutation();
    });
  };

  const rebaseOutlineEditor = () => {
    if (!outlineConflictBase) return;
    updateOutlineEditorBase(outlineConflictBase);
    setOutlineConflictBase(null);
    setActionError(null);
    setActionNotice("本地编辑内容未改变。已切换保存基线，请核对后基于最新 revision 重试。");
  };

  const saveTitle = () => {
    const name = titleInput.trim();
    if (!name || name === displayTitle) return;
    void runMutation(`title:${titleUpdatedAt}:${name}`, async () => {
      const result = requireApiData(await browserApi.PATCH(
        "/api/v1/novels/{novel_id}/title",
        {
          params: { path: { novel_id: novel.id } },
          body: { name, expectedUpdatedAt: titleUpdatedAt },
        },
      ));
      setDisplayTitle(result.name);
      setTitleInput(result.name);
      setTitleUpdatedAt(result.updatedAt);
      setTitleConflict(false);
      setActionNotice("标题已更新。");
    });
  };

  const saveTargetWordCount = () => {
    const target = Number(targetInput);
    if (aggregateRef.current === null) {
      setActionError("尚未读取到权威写作状态，请先重试读取状态");
      return;
    }
    if (!isValidShortStoryTarget(target)) {
      setActionError("中短篇目标字数必须是 6000～80000 的整数");
      return;
    }
    void runMutation(`target:${target}`, async () => {
      const planning = requireApiData(await browserApi.GET(
        "/api/v1/novels/{novel_id}/workspace/planning",
        { params: { path: { novel_id: novel.id } } },
      ));
      if (!planning.writingBible) throw new Error("作品圣经不存在，无法修正目标字数");
      const result = requireApiData(await browserApi.PUT(
        "/api/v1/novels/{novel_id}/writing-bible",
        {
          params: { path: { novel_id: novel.id } },
          body: buildWritingBibleTargetUpdate(planning.writingBible, target),
        },
      ));
      const savedTarget = result.targetTotalWordCount ?? target;
      setTargetWordCount(savedTarget);
      setTargetInput(String(savedTarget));
      setActionNotice("目标字数已更新。");
    });
  };

  const loadRevision = (revision: number) => {
    if (activePane !== "outline" || !outlineArtifact) return;
    const loadToken = ++revisionLoadTokenRef.current;
    setRevisionLoading(true);
    setActionError(null);
    void (async () => {
      try {
        const detail = requireApiData(await browserApi.GET(
          "/api/v1/review-artifacts/{artifact_id}/revisions/{revision}",
          {
            params: {
              path: { artifact_id: outlineArtifact.id, revision },
            },
          },
        ));
        if (revisionLoadTokenRef.current === loadToken) setRevisionDetail(detail);
      } catch (error) {
        if (revisionLoadTokenRef.current === loadToken) {
          setActionError(getErrorMessage(error, "读取版本详情失败"));
        }
      } finally {
        if (revisionLoadTokenRef.current === loadToken) setRevisionLoading(false);
      }
    })();
  };

  const restoreRevision = () => {
    if (
      activePane !== "outline"
      || !outlineArtifact
      || !revisionDetail
      || !canRestoreOutlineRevision({ pane: activePane, status: outlineArtifact.status })
    ) return;
    const actionKey = `restore:${outlineArtifact.id}:${revisionDetail.revision}:${outlineArtifact.revision}`;
    void runMutation(actionKey, async () => {
      if (legacyMultiChapter) {
        throw new Error("需整理为单一正文后才能启动新中短篇流程");
      }
      const restored = requireApiData(await browserApi.POST(
        "/api/v1/review-artifacts/{artifact_id}/revisions/{revision}/restore",
        {
          params: {
            path: {
              artifact_id: outlineArtifact.id,
              revision: revisionDetail.revision,
            },
          },
          body: { expectedRevision: outlineArtifact.revision },
        },
      ));
      outlineDirtyRef.current = false;
      setOutlineDirty(false);
      setOutlineConflictBase(null);
      setRevisionDetail(null);
      const current = aggregateRef.current;
      if (current) applyAggregate(applySavedOutlineToAggregate(current, restored));
      setActionNotice("历史版本已复制为新的当前 revision。");
      await refreshAfterMutation();
    });
  };

  const switchPane = (pane: ActivePane) => {
    revisionLoadTokenRef.current += 1;
    setRevisionLoading(false);
    setRevisionsLoading(false);
    setRevisions([]);
    setActivePane(pane);
    setRevisionDetail(null);
  };

  const outlinePayload = getOutlinePayload(outlineArtifact);
  const draftPayload = getDraftPayload(draftArtifact);
  const draftTextLength = useMemo(
    () => countTextLength(draftPayload?.content ?? ""),
    [draftPayload?.content],
  );
  const formalTextLength = useMemo(
    () => countTextLength(currentChapter?.content ?? ""),
    [currentChapter?.content],
  );
  const visibleRevisionDetail = activePane === "outline" ? revisionDetail : null;
  const revisionContent = getRevisionContent(visibleRevisionDetail);
  const visibleRevisions = activePane === "outline" ? revisions : [];
  const outlineEditable = actions.canEditOutline && !interactionLocked;
  const taskFailed = actions.runFailed && !optimisticCommand;

  const renderOutlineCanvas = () => {
    if (!outlineArtifact || !outlinePayload) {
      return (
        <div className="short-story-empty-state">
          <h2>尚未生成大纲</h2>
          <p className="muted">项目已保留。确认目标字数有效后，可以在右侧重试生成完整大纲。</p>
        </div>
      );
    }

    if (outlineDisplayMode === "read") {
      return (
        <ShortStoryContent
          content={outlinePayload.content}
          emptyLabel="大纲正在生成，请稍候。"
        />
      );
    }

    return (
      <div className="short-story-outline-editor stack">
        <label className="stack short-story-field">
          <span className="label">原始灵感（只读）</span>
          <textarea className="textarea" value={outlinePayload.originalInspiration} readOnly rows={4} />
        </label>
        <label className="stack short-story-field">
          <span className="label">核心前提</span>
          <textarea
            className="textarea"
            value={outlineCorePremise}
            disabled={!outlineEditable}
            rows={4}
            onChange={(event) => {
              setOutlineCorePremise(event.target.value);
              markOutlineDirty();
            }}
          />
        </label>

        <div className="short-story-anchor-grid">
          {ANCHOR_FIELDS.map((field) => (
            <label className="stack short-story-field" key={field.key}>
              <span className="label">{field.label}</span>
              <textarea
                className="textarea"
                value={(outlineAnchors[field.key] ?? []).join("\n")}
                disabled={!outlineEditable}
                rows={5}
                placeholder="每行一个锚点"
                onChange={(event) => {
                  setOutlineAnchors((current) => ({
                    ...current,
                    [field.key]: splitAnchorLines(event.target.value),
                  }));
                  markOutlineDirty();
                }}
              />
            </label>
          ))}
        </div>

        <div className="short-story-sections stack">
          {outlineSections.map((section, index) => (
            <section className="short-story-section-card" key={section.key}>
              <div className="short-story-section-toolbar">
                <strong>第 {index + 1} 节</strong>
                <div className="meta">
                  <button
                    className="button ghost compact"
                    type="button"
                    disabled={!outlineEditable || index === 0}
                    onClick={() => {
                      setOutlineSections((current) => moveOutlineItem(current, section.key, "up"));
                      markOutlineDirty();
                    }}
                  >上移</button>
                  <button
                    className="button ghost compact"
                    type="button"
                    disabled={!outlineEditable || index === outlineSections.length - 1}
                    onClick={() => {
                      setOutlineSections((current) => moveOutlineItem(current, section.key, "down"));
                      markOutlineDirty();
                    }}
                  >下移</button>
                  <button
                    className="button ghost compact danger"
                    type="button"
                    disabled={!outlineEditable || outlineSections.length <= 1}
                    onClick={() => {
                      setOutlineSections((current) => removeOutlineItem(current, section.key));
                      markOutlineDirty();
                    }}
                  >删除</button>
                </div>
              </div>
              <input
                className="input"
                value={section.title}
                disabled={!outlineEditable}
                aria-label={`第 ${index + 1} 节标题`}
                placeholder="分节标题"
                onChange={(event) => {
                  const title = event.target.value;
                  setOutlineSections((current) => updateOutlineItem(
                    current,
                    section.key,
                    (item) => ({ ...item, title }),
                  ));
                  markOutlineDirty();
                }}
              />
              <textarea
                className="textarea"
                value={section.events}
                disabled={!outlineEditable}
                aria-label={`第 ${index + 1} 节发生了什么`}
                placeholder="这一节发生了什么"
                rows={7}
                onChange={(event) => {
                  const events = event.target.value;
                  setOutlineSections((current) => updateOutlineItem(
                    current,
                    section.key,
                    (item) => ({ ...item, events }),
                  ));
                  markOutlineDirty();
                }}
              />
            </section>
          ))}
          <button
            className="button secondary"
            type="button"
            disabled={!outlineEditable}
            onClick={() => {
              setOutlineSections((current) => appendOutlineItem(current, () => ({
                key: crypto.randomUUID(),
                persistedId: null,
                title: "",
                events: "",
              })));
              markOutlineDirty();
            }}
          >新增一节</button>
        </div>

        <label className="stack short-story-field">
          <span className="label">本版修改摘要</span>
          <input
            className="input"
            value={outlineChangeSummary}
            disabled={!outlineEditable}
            onChange={(event) => {
              setOutlineChangeSummary(event.target.value);
              markOutlineDirty();
            }}
          />
        </label>
        <button
          className="button primary"
          type="button"
          disabled={!outlineDirty || !outlineEditable}
          onClick={saveOutline}
        >{pendingAction?.startsWith("save-outline") ? "保存中…" : "保存为新 revision"}</button>
        {outlineConflictBase ? (
          <div className="short-story-error stack" role="alert">
            <span>
              服务端当前为 revision {outlineConflictBase.revision}，本地编辑基于 revision {editorBaseRevision ?? "未知"}。
              本地内容尚未改变，请先核对最新大纲。
            </span>
            <button
              className="button secondary"
              type="button"
              disabled={interactionLocked}
              onClick={rebaseOutlineEditor}
            >基于最新 revision 重试</button>
          </div>
        ) : null}
      </div>
    );
  };

  const renderDraftCanvas = () => {
    if (!draftArtifact || !draftPayload) {
      return (
        <div className="short-story-empty-state">
          <h2>完整初稿尚未生成</h2>
          <p className="muted">批准大纲后，可从右侧一次生成完整正文。</p>
        </div>
      );
    }
    return (
      <div className="stack short-story-draft-view">
        <div className="meta short-story-draft-meta">
          <span className="badge">目标 {draftPayload.metadata.targetWordCount} 字</span>
          <span className="badge">实际 {draftTextLength} 字</span>
          <span className="badge">来源大纲 revision {draftPayload.metadata.sourceOutlineRevision}</span>
          <span className="badge">自动返工 {draftPayload.metadata.automaticRewriteCount}/1</span>
        </div>
        <ShortStoryContent content={draftPayload.content} />
      </div>
    );
  };

  const renderFormalCanvas = () => (
    <div className="stack short-story-draft-view">
      <div className="meta short-story-draft-meta">
        <span className="badge">{currentChapter?.title ?? "正式正文"}</span>
        <span className="badge">{formalTextLength} 字</span>
        <span className="badge">只读</span>
      </div>
      <ShortStoryContent
        content={currentChapter?.content ?? ""}
        emptyLabel="这个正文文件目前还没有内容。"
      />
    </div>
  );

  const renderEvaluations = (agent: "编辑" | "校验", title: string) => {
    const evaluations = (draftArtifact?.evaluations ?? []).filter(
      (evaluation) => evaluation.evaluatorAgent === agent,
    );
    return (
      <section className="short-story-evaluations stack">
        <h3>{title}</h3>
        {evaluations.length ? evaluations.map((evaluation) => (
          <div className="short-story-evaluation" key={evaluation.id}>
            <div className="meta">
              <span className={`badge verdict-${evaluation.verdict}`}>{evaluation.verdict}</span>
              <span>revision {evaluation.revision}</span>
            </div>
            <p>{evaluation.summary}</p>
            {evaluation.requiredChanges ? <p className="muted">需修改：{evaluation.requiredChanges}</p> : null}
          </div>
        )) : <p className="muted">尚无审核结论。</p>}
      </section>
    );
  };

  return (
    <main className="page stack short-story-page">
      <header className="panel short-story-header">
        <div>
          <Link href="/" className="muted">← 返回</Link>
          <h1 className="title-lg">{displayTitle}</h1>
          <div className="meta">
            <span className="badge">中短篇</span>
            <span className="badge">目标 {targetWordCount ?? "未设置"} 字</span>
            {latestTask ? <span className="badge">{latestTask.operation} · {latestTask.phase}</span> : null}
          </div>
        </div>
        <LogoutButton />
      </header>

      <div className="short-story-grid">
        <aside className="panel short-story-workflow" aria-label="中短篇写作流程">
          <h2 className="title-sm">写作进度</h2>
          <ol>
            <li className={outlineArtifact?.status === "applied" ? "done" : "active"}>
              <strong>完整大纲</strong>
              <span>{aggregate === null
                ? "状态未确认"
                : outlineArtifact
                  ? formatArtifactStatus(outlineArtifact.status)
                  : "等待生成"}</span>
            </li>
            <li className={draftArtifact ? "done" : outlineArtifact?.status === "applied" ? "active" : ""}>
              <strong>完整初稿</strong>
              <span>{draftArtifact ? formatArtifactStatus(draftArtifact.status) : "批准大纲后开始"}</span>
            </li>
            <li className={draftArtifact?.evaluations?.length ? "done" : draftArtifact ? "active" : ""}>
              <strong>全稿审核与返工</strong>
              <span>{draftArtifact?.evaluations?.length ? "已有审核结论" : "正文生成后串行执行"}</span>
            </li>
            <li className={draftArtifact?.status === "applied" ? "done" : ""}>
              <strong>正式正文</strong>
              <span>{draftArtifact?.status === "applied" ? "已应用到正文" : "等待你的最终确认"}</span>
            </li>
          </ol>
          {legacyMultiChapter ? (
            <section className="short-story-legacy-chapters stack" role="status">
              <strong>需整理为单一正文后才能启动新中短篇流程</strong>
              <p>
                检测到 {bootstrap.chapters.length} 个历史正文文件。你可以逐个只读查看；
                请先将它们整理为唯一“正文”，之后才能启动新的中短篇流程。标题和目标字数仍可修改。
              </p>
              <ul>
                {bootstrap.chapters.map((chapter) => (
                  <li key={chapter.id}>
                    <Link
                      href={buildWorkspaceChapterHref({
                        novelId: novel.id,
                        chapterId: chapter.id,
                        view: "reading",
                      })}
                      onClick={() => switchPane("formal")}
                    >{chapter.title}</Link>
                    <small>{chapter.wordCount} 字</small>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {taskFailed ? (
            <div className="short-story-error" role="alert">
              最近一次运行失败。若已有大纲或正文，旧版内容已保留；你可以继续处理旧版，或重试对应操作。
            </div>
          ) : null}
        </aside>

        <section className="panel short-story-main-canvas" aria-label="中短篇完整内容">
          <div className="short-story-canvas-toolbar">
            <div className="meta">
              <button
                className={`button ghost compact ${activePane === "outline" ? "active" : ""}`}
                type="button"
                onClick={() => switchPane("outline")}
              >完整大纲</button>
              <button
                className={`button ghost compact ${activePane === "draft" ? "active" : ""}`}
                type="button"
                onClick={() => switchPane("draft")}
              >完整初稿</button>
              <button
                className={`button ghost compact ${activePane === "formal" ? "active" : ""}`}
                type="button"
                onClick={() => switchPane("formal")}
              >正式正文</button>
            </div>
            {activePane === "outline" && outlineArtifact ? (
              <div className="meta">
                <span className="badge">revision {outlineArtifact.revision}</span>
                <button
                  className="button ghost compact"
                  type="button"
                  onClick={() => setOutlineDisplayMode("read")}
                >阅读完整大纲</button>
                <button
                  className="button ghost compact"
                  type="button"
                  disabled={!actions.canEditOutline}
                  onClick={() => setOutlineDisplayMode("edit")}
                >直接编辑</button>
              </div>
            ) : activePane === "draft" && draftArtifact ? (
              <span className="badge">revision {draftArtifact.revision}</span>
            ) : activePane === "formal" && currentChapter ? (
              <span className="badge">{formalTextLength} 字 · 只读</span>
            ) : null}
          </div>

          {initialLoading ? <p className="empty">正在读取中短篇工作区…</p> : null}
          {!initialLoading && aggregate === null && activePane !== "formal" ? (
            <div className="short-story-empty-state">
              <h2>尚未确认工作流状态</h2>
              <p className="muted">读取失败不代表尚未生成大纲或初稿。请使用右侧“重试读取状态”。</p>
            </div>
          ) : null}
          {!initialLoading && visibleRevisionDetail ? (
            <div className="stack short-story-version-preview">
              <div className="meta">
                <strong>历史 revision {visibleRevisionDetail.revision}</strong>
                <span>{formatDateTime(visibleRevisionDetail.createdAt)}</span>
                <button className="button ghost compact" type="button" onClick={() => setRevisionDetail(null)}>
                  返回当前版本
                </button>
              </div>
              <ShortStoryContent content={revisionContent ?? ""} emptyLabel="该历史版本没有可显示的完整内容。" />
            </div>
          ) : null}
          {!initialLoading && aggregate !== null && !visibleRevisionDetail && activePane === "outline" ? renderOutlineCanvas() : null}
          {!initialLoading && aggregate !== null && !visibleRevisionDetail && activePane === "draft" ? renderDraftCanvas() : null}
          {!initialLoading && activePane === "formal" ? renderFormalCanvas() : null}
        </section>

        <aside className="panel short-story-review-rail" aria-label="版本与审核操作">
          <div className="short-story-review-scroll stack">
            <section className="stack short-story-settings">
              <h2 className="title-sm">作品信息</h2>
              <label className="stack short-story-field">
                <span className="label">标题</span>
                <div className="short-story-inline-form">
                  <input className="input" value={titleInput} onChange={(event) => setTitleInput(event.target.value)} />
                  <button
                    className="button secondary compact"
                    type="button"
                    disabled={titleConflict || interactionLocked || !titleInput.trim() || titleInput.trim() === displayTitle}
                    onClick={saveTitle}
                  >保存</button>
                </div>
              </label>
              {titleConflict ? (
                <button
                  className="button secondary"
                  type="button"
                  onClick={() => window.location.reload()}
                >刷新页面同步标题</button>
              ) : null}
              <label className="stack short-story-field">
                <span className="label">目标总字数（6000～80000）</span>
                <div className="short-story-inline-form">
                  <input
                    className="input"
                    inputMode="numeric"
                    value={targetInput}
                    onChange={(event) => setTargetInput(event.target.value)}
                  />
                  <button
                    className="button secondary compact"
                    type="button"
                    disabled={
                      !actions.canUpdateTargetWordCount
                      || interactionLocked
                      || !isValidShortStoryTarget(Number(targetInput))
                    }
                    onClick={saveTargetWordCount}
                  >更新</button>
                </div>
              </label>
              {!actions.targetWordCountValid ? (
                <p className="short-story-error" role="alert">
                  当前目标字数不在 6000～80000 范围内，新流程已阻止；请先修正并更新。
                </p>
              ) : null}
            </section>

            {loadError ? <p className="short-story-error" role="alert">{loadError}</p> : null}
            {actionError ? <p className="short-story-error" role="alert">{actionError}</p> : null}
            {actionNotice ? <p className="short-story-notice" role="status">{actionNotice}</p> : null}

            <section className="stack short-story-actions">
              <h2 className="title-sm">当前操作</h2>
              {aggregate === null ? (
                <button
                  className="button primary"
                  type="button"
                  disabled={initialLoading}
                  onClick={() => void refreshAggregate()}
                >{initialLoading ? "正在读取状态…" : "重试读取状态"}</button>
              ) : (
                <>
                  {!outlineArtifact ? (
                    <button
                      className="button primary"
                      type="button"
                      disabled={!actions.canRetryOutline || interactionLocked}
                      onClick={() => startOperation("develop_short_outline")}
                    >{interactionLocked ? "正在生成…" : "重试生成完整大纲"}</button>
                  ) : null}

                  {outlineArtifact && activePane === "outline" && outlineArtifact.status === "awaiting_user" ? (
                    <>
                      <textarea
                        className="textarea"
                        rows={4}
                        value={outlineRevisionRequest}
                        placeholder="例如：只修改第 3 节，让冲突更早爆发"
                        onChange={(event) => setOutlineRevisionRequest(event.target.value)}
                      />
                      {outlineDirty ? <p className="muted">请先保存直接编辑，才能批准或要求 Agent 返工。</p> : null}
                      <div className="short-story-action-grid">
                        <button
                          className="button secondary"
                          type="button"
                          disabled={!actions.canDecideOutline || outlineDirty || !outlineRevisionRequest.trim() || interactionLocked}
                          onClick={() => decideArtifact(outlineArtifact, "revise", outlineRevisionRequest)}
                        >按要求修改大纲</button>
                        <button
                          className="button primary"
                          type="button"
                          disabled={!actions.canDecideOutline || outlineDirty || interactionLocked}
                          onClick={() => decideArtifact(outlineArtifact, "approve")}
                        >批准当前大纲</button>
                        <button
                          className="button ghost danger"
                          type="button"
                          disabled={!actions.canDecideOutline || outlineDirty || interactionLocked}
                          onClick={() => decideArtifact(outlineArtifact, "discard")}
                        >放弃当前大纲</button>
                      </div>
                    </>
                  ) : null}

                  {actions.canGenerateDraft ? (
                    <button
                      className="button primary"
                      type="button"
                      disabled={interactionLocked}
                      onClick={() => startOperation("write_short_story")}
                    >生成完整初稿</button>
                  ) : null}

                  {draftArtifact && activePane === "draft" ? (
                    <>
                      {renderEvaluations("编辑", "编辑审核")}
                      {renderEvaluations("校验", "校验审核")}
                      {draftArtifact.status === "awaiting_user" ? (
                        <>
                          <textarea
                            className="textarea"
                            rows={5}
                            value={draftRevisionRequest}
                            placeholder="写下新的整稿修改要求，可反复修改，不受自动返工次数限制"
                            onChange={(event) => setDraftRevisionRequest(event.target.value)}
                          />
                          <div className="short-story-action-grid">
                            <button
                              className="button secondary"
                              type="button"
                              disabled={!actions.canReviseDraft || !draftRevisionRequest.trim() || interactionLocked}
                              onClick={() => decideArtifact(draftArtifact, "revise", draftRevisionRequest)}
                            >按要求完整返工</button>
                            <button
                              className="button primary"
                              type="button"
                              disabled={!actions.canDecideDraft || interactionLocked}
                              onClick={() => decideArtifact(draftArtifact, "approve")}
                            >批准并应用正式正文</button>
                            <button
                              className="button ghost danger"
                              type="button"
                              disabled={!actions.canDecideDraft || interactionLocked}
                              onClick={() => decideArtifact(draftArtifact, "discard")}
                            >放弃当前正文草案</button>
                          </div>
                        </>
                      ) : null}
                    </>
                  ) : null}
                </>
              )}
            </section>

            {activePane === "outline" && outlineArtifact ? (
              <section className="stack short-story-history">
                <div className="short-story-section-toolbar">
                  <h2 className="title-sm">版本历史</h2>
                  <span className="badge">当前 {outlineArtifact.revision}</span>
                </div>
                {revisionsLoading ? <p className="muted">正在读取版本…</p> : null}
                {!revisionsLoading && visibleRevisions.length === 0 ? <p className="muted">暂无可查看版本。</p> : null}
                {visibleRevisions.map((revision) => (
                  <button
                    className={`short-story-history-item ${revisionDetail?.revision === revision.revision ? "active" : ""}`}
                    type="button"
                    key={revision.revision}
                    disabled={revisionLoading}
                    onClick={() => loadRevision(revision.revision)}
                  >
                    <strong>revision {revision.revision}</strong>
                    <span>{revision.summary || "无修改摘要"}</span>
                    <small>{formatDateTime(revision.createdAt)}</small>
                  </button>
                ))}
                {visibleRevisionDetail
                  && visibleRevisionDetail.revision !== outlineArtifact.revision
                  && canRestoreOutlineRevision({ pane: activePane, status: outlineArtifact.status }) ? (
                    <button
                      className="button secondary"
                      type="button"
                      disabled={legacyMultiChapter || interactionLocked || outlineDirty}
                      onClick={restoreRevision}
                    >恢复此版本为新 revision</button>
                  ) : null}
              </section>
            ) : null}
          </div>
        </aside>
      </div>
    </main>
  );
}

"use client";

import { useCallback, useOptimistic, useReducer, useRef, useState, useTransition, useEffect } from "react";
import { parseSseFrame } from "@inkforge/api-client";

import {
  AGENT_REGISTRY,
  type AgentId,
} from "@/features/writing/agent-registry";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import type { WritingSseEvent } from "@/shared/contracts/sse-events";
import { parseSseEvent } from "@/shared/contracts/sse-events";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import {
  getCreativeOperationLabel,
  getCreativeOperationOutputLabel,
} from "@/shared/contracts/creative-operation";
import type { AgentUpdateSelectionRef } from "@/shared/contracts/agent-updates";
import type { ReviewArtifactDecision } from "@/shared/contracts/review-artifact";
import type { WritingSessionTaskSummary } from "@/shared/contracts/writing-session";
import { countTextLength } from "@/shared/lib/word-count";
import {
  EMPTY_AGENT_ACTIVITY_STATE,
  reduceAgentActivityState,
  type AgentActivityAction,
  type AgentActivityEntry as ToolActivityEntry,
  type AgentActivityRound as ToolActivityRound,
  type AgentActivityState,
} from "./agent-activity-state";
import {
  listAgentLiveRuns,
  reduceAgentLiveRuns,
  resolveFinalAgentContent,
  type AgentLiveAction,
  type AgentLiveRuns,
} from "./agent-live-state";
import { normalizeParagraphTextDisplay, ParagraphText, renderParagraphMessageContent } from "./plain-text";
import {
  applyOptimisticReviewArtifactDecision,
  attachReviewArtifactToConversation,
  clearReviewArtifactFromMessages,
  resolveReviewArtifactActionTaskId,
  resolveTerminalStreamPhase,
  resolveReviewArtifactTaskId,
  resolveVisibleReviewArtifact,
  shouldRefreshAwaitingReviewArtifact,
} from "./review-artifact-state";
import {
  resolveLoadedSessionRecoveryState,
} from "./session-task-state";
import {
  getWritingNextActions,
  WRITING_SHORTCUT_ACTIONS,
  type WritingProductAction,
} from "./product-actions";
import { shouldPersistOptimisticWritingMessage } from "./message-persistence";
import { createAsyncActionGuard } from "./send-guard";
import {
  createWritingEventCursors,
  type WritingEventCursors,
} from "./writing-event-cursor";
import {
  createEmptySessionWorkspace,
  isCurrentSessionStream,
  reduceSessionWorkspace,
  resolveArtifactInteractionScope,
  type SessionWorkspaceState,
  type WritingConversationPhase,
} from "./session-workspace-state";
import {
  countVisibleToolCalls,
  getToolActivityLabel,
  getToolActivitySummary,
  isVisibleToolActivity,
} from "./tool-activity";
import "./writing-conversation.css";

type WritingConversationProps = {
  novelId: string;
  chapterId: string;
  chapterContext?: {
    title: string;
    status: string;
    wordCount: number;
    openConsistencyCheckCount: number;
    approvedBeatPlan: {
      id: string;
      chapterGoal: string;
      sceneCount: number;
      totalEstimatedWords: number;
    } | null;
  };
  selectedAgents: AgentId[];
  targetWordCount: number;
  onComplete?: () => void;
};

async function openWritingRunEvents(
  taskId: string,
  cursors: WritingEventCursors,
  signal?: AbortSignal,
): Promise<Response> {
  const response = await fetch(`/api/v1/writing/runs/${encodeURIComponent(taskId)}/events`, {
    credentials: "include",
    headers: cursors.headers(taskId),
    signal,
  });
  if (response.ok) return response;
  const error = await response.json().catch(() => null) as { message?: string } | null;
  throw new Error(error?.message || "连接写作事件流失败");
}

// 会话类型
type Session = {
  id: string;
  novelId: string;
  chapterId: string;
  title: string | null;
  phase: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  lastMessage: {
    content: string;
    role: string;
    agentId: string | null;
  } | null;
};

type LoadedSessionResponse = Omit<Session, "messageCount" | "lastMessage"> & {
  messages: Array<{
    id: string;
    role: string;
    agentId: string | null;
    content: string;
    intent: string | null;
    createdAt: string;
  }>;
  currentTask?: WritingSessionTaskSummary | null;
  lastTask?: WritingSessionTaskSummary | null;
};

// 消息类型
type Message = {
  id: string;
  role: "user" | "agent" | "system";
  agentId?: string;
  agentName?: string;
  content: string;
  intent?: string;
  timestamp: number;
  pendingUpdates?: PendingUpdatesData | null;
  reviewArtifact?: ReviewArtifactData | null;
  /** 提取的完整版本内容（用于复制） */
  fullVersion?: string;
  /**
   * Phase D 返工：标记消息是否来自新协议（段落文本 + control tools）。
   * true = 新协议，content 是段落文本，直接渲染
   * undefined/false = 可能是旧 JSON 协议，走 legacy extractDisplayContent
   */
  isNewProtocol?: boolean;
};

type AddMessageInput = {
  role: "user" | "agent" | "system";
  agentId?: string;
  agentName?: string;
  content: string;
  intent?: string;
  isNewProtocol?: boolean;
  sessionId?: string | null;
  persist?: boolean;
};

type PendingUpdatesData = {
  characters?: Record<string, unknown>[];
  locations?: Record<string, unknown>[];
  items?: Record<string, unknown>[];
  factions?: Record<string, unknown>[];
  glossaries?: Record<string, unknown>[];
  characterExperiences?: Record<string, unknown>[];
  foreshadowing?: Record<string, unknown>[];
  references?: Record<string, unknown>[];
  outlineContent?: string;
  outlineAdjustments?: Record<string, unknown>[];
  outline?: Record<string, unknown>[];
  worldSetting?: string;
  storyBackground?: string;
  __diff?: UpdateDiffItem[];
};

type ReviewArtifactData = {
  id: string;
  taskId?: string | null;
  artifactKey?: string | null;
  kind: string;
  status: string;
  summary?: string | null;
  revision: number;
  diff?: UpdateDiffItem[] | null;
  payload?: {
    kind?: string;
    updates?: PendingUpdatesData;
    content?: string;
    markdown?: string;
    beatPlan?: {
      title?: string;
      summary?: string;
      chapterGoal?: string;
      mainPlotConnection?: string;
      chapterAcceptanceCriteria?: string;
      totalEstimatedWords?: number;
      sceneBeats?: Array<{
        order?: number;
        goal?: string;
        conflict?: string;
        characters?: string[];
        foreshadowingRefs?: string[];
        estimatedWords?: number;
        acceptanceCriteria?: string;
      }>;
    };
  };
  evaluations?: Array<{
    evaluatorAgent: string;
    verdict: string;
    summary: string;
    requiredChanges?: string | null;
  }>;
  optimisticStatus?: "applying" | "discarding" | "revising";
};

type ReviewArtifactActionStatus = "pending" | "succeeded" | "failed";

type ReviewArtifactActionState = {
  artifactId: string;
  decision: ReviewArtifactDecision;
  status: ReviewArtifactActionStatus;
  message: string;
};

type ChapterTargetPrompt = {
  summary?: string;
  content?: string;
};

function isActionableReviewArtifact(artifact: ReviewArtifactData) {
  return artifact.status === "awaiting_user";
}

function getReviewArtifactActionMessage(
  decision: ReviewArtifactDecision,
  status: ReviewArtifactActionStatus,
  fallback?: string
) {
  if (fallback) return fallback;
  if (decision === "approve") {
    if (status === "succeeded") return "已应用到项目，正在刷新状态...";
    if (status === "failed") return "应用失败，请检查错误后重试";
    return "正在应用到项目...";
  }
  if (decision === "discard") {
    if (status === "succeeded") return "已丢弃变更，正在刷新状态...";
    if (status === "failed") return "丢弃失败，请检查错误后重试";
    return "正在丢弃变更...";
  }
  if (status === "succeeded") return "已进入返工流程，正在返回会话...";
  if (status === "failed") return "返工启动失败，请检查错误后重试";
  return "正在准备返工流程...";
}

function isReviewArtifactActionLocked(action: ReviewArtifactActionState | null) {
  return action?.status === "pending" || action?.status === "succeeded";
}

function getReviewArtifactActionButtonLabel(action: ReviewArtifactActionState | null, decision: ReviewArtifactDecision) {
  if (!action || action.decision !== decision || action.status === "failed") return null;
  if (decision === "approve") return action.status === "succeeded" ? "已应用" : "应用中...";
  if (decision === "discard") return action.status === "succeeded" ? "已丢弃" : "丢弃中...";
  return action.status === "succeeded" ? "已开始返工" : "准备返工...";
}

type QuickReviewActionsProps = {
  artifact: ReviewArtifactData;
  action: ReviewArtifactActionState | null;
  editedContent?: string;
  isSending: boolean;
  onDecision: (
    artifact: ReviewArtifactData,
    decision: ReviewArtifactDecision,
    userMessage?: string,
    editedContent?: string,
  ) => Promise<void>;
  onRevise: () => void;
};

function QuickReviewActions({
  artifact,
  action,
  editedContent,
  isSending,
  onDecision,
  onRevise,
}: QuickReviewActionsProps) {
  const actionLocked = isReviewArtifactActionLocked(action);
  const isApplyDisabled = isSending ||
    actionLocked ||
    Boolean(artifact.optimisticStatus) ||
    (editedContent !== undefined && !editedContent.trim());

  return (
    <>
      <button
        disabled={isApplyDisabled}
        onClick={() => void onDecision(artifact, "approve", undefined, editedContent)}
      >
        {getReviewArtifactActionButtonLabel(action, "approve") ?? (artifact.optimisticStatus === "applying" ? "应用中..." : "应用到项目")}
      </button>
      <button
        disabled={isSending || actionLocked || Boolean(artifact.optimisticStatus)}
        onClick={onRevise}
      >
        {getReviewArtifactActionButtonLabel(action, "revise") ?? (artifact.optimisticStatus === "revising" ? "准备返工..." : "继续修改")}
      </button>
      <button
        disabled={isSending || actionLocked || Boolean(artifact.optimisticStatus)}
        onClick={() => void onDecision(artifact, "discard")}
      >
        {getReviewArtifactActionButtonLabel(action, "discard") ?? (artifact.optimisticStatus === "discarding" ? "丢弃中..." : "丢弃变更")}
      </button>
    </>
  );
}

type UpdateDiffItem = {
  section: string;
  action: string;
  name: string;
  fields: UpdateDiffField[];
};

type UpdateDiffField = {
  field: string;
  label: string;
  oldValue?: string;
  newValue?: string;
};

type WritingPhase = WritingConversationPhase;

type OutlinePreviewNode = {
  key: string;
  title: string;
  action: string;
  kind: string;
  status?: string;
  estimatedWordCount?: number;
  content?: string;
  children: OutlinePreviewNode[];
};

// Agent 信息（v5.2 中文 ID，Phase 1.3 清理旧 ID 回退）
const AGENT_INFO: Record<string, { tone: string; emoji: string }> = {
  system: { tone: "gray", emoji: "系" },
  设定: { tone: "blue", emoji: "设" },
  剧情: { tone: "orange", emoji: "剧" },
  写作: { tone: "purple", emoji: "写" },
  校验: { tone: "green", emoji: "验" },
  编辑: { tone: "cyan", emoji: "编" },
};

type FlowLogEntry = {
  id: string;
  timestamp: number;
  type: "phase" | "agent_start" | "agent_done" | "intent" | "operation" | "user" | "error" | "agent_status";
  agentId?: string;
  content: string;
  duration?: number;
};

type StreamUiScope =
  | { mode: "session"; sessionId: string }
  | { mode: "artifact"; artifactId: string };

function getReviewArtifactStatusLabel(status: string, optimisticStatus?: ReviewArtifactData["optimisticStatus"]) {
  if (optimisticStatus === "applying") return "应用中";
  if (optimisticStatus === "discarding") return "丢弃中";
  if (optimisticStatus === "revising") return "准备返工";
  if (status === "draft") return "草稿";
  if (status === "under_review") return "复审中";
  if (status === "awaiting_user") return "等待确认";
  if (status === "applying") return "应用中";
  if (status === "applied") return "已应用";
  return "状态异常";
}

function getReviewVerdictLabel(verdict: string) {
  if (verdict === "pass") return "通过";
  if (verdict === "revise") return "需修改";
  if (verdict === "block") return "阻止";
  return "评审结果";
}

function getReviewArtifactKindLabel(kind: string) {
  if (kind === "agent_updates") return "结构化变更";
  if (kind === "outline_draft") return "大纲草案";
  if (kind === "chapter_draft" || kind === "chapter_content") return "正文草案";
  if (kind === "lore_draft") return "设定草案";
  if (kind === "revision_brief") return "返工说明";
  if (kind === "beat_plan_draft" || kind === "beat_plan") return "章节规划";
  return "草案";
}

function getReviewArtifactImpactLabel(kind: string) {
  if (kind === "agent_updates") return "会改设定、大纲、伏笔或参考资料";
  if (kind === "chapter_draft" || kind === "chapter_content") return "会改当前章节正文";
  if (kind === "beat_plan_draft" || kind === "beat_plan") return "会保存为本章写作计划";
  if (kind === "outline_draft") return "会改作品总纲";
  if (kind === "lore_draft") return "会改设定资料";
  return "应用后会写入正式项目";
}

function getReviewArtifactContent(artifact: ReviewArtifactData): string {
  if (artifact.payload?.kind === "beat_plan" && artifact.payload.beatPlan) {
    const plan = artifact.payload.beatPlan;
    const lines: string[] = [];
    if (plan.title) lines.push(plan.title);
    if (plan.chapterGoal) lines.push(`章节目标：${plan.chapterGoal}`);
    if (plan.mainPlotConnection) lines.push(`主线关联：${plan.mainPlotConnection}`);
    if (plan.chapterAcceptanceCriteria) lines.push(`验收标准：${plan.chapterAcceptanceCriteria}`);
    if (typeof plan.totalEstimatedWords === "number") lines.push(`预计字数：${plan.totalEstimatedWords}`);
    if (plan.summary) lines.push(`摘要：${plan.summary}`);
    if (plan.sceneBeats?.length) {
      lines.push("");
      lines.push("场景节拍：");
      for (const beat of plan.sceneBeats) {
        lines.push(`${beat.order ?? ""}. ${beat.goal ?? "未命名场景"}`.trim());
        if (beat.conflict) lines.push(`阻力/冲突：${beat.conflict}`);
        if (beat.characters?.length) lines.push(`角色：${beat.characters.join("、")}`);
        if (beat.foreshadowingRefs?.length) lines.push(`伏笔：${beat.foreshadowingRefs.join("、")}`);
        if (typeof beat.estimatedWords === "number") lines.push(`预计字数：${beat.estimatedWords}`);
        if (beat.acceptanceCriteria) lines.push(`验收：${beat.acceptanceCriteria}`);
      }
    }
    return lines.join("\n");
  }
  return artifact.payload?.content ?? artifact.payload?.markdown ?? "";
}

function getUpdateActionLabel(action: string) {
  if (action === "create") return "新增";
  if (action === "update") return "修改";
  if (action === "delete") return "删除";
  if (action === "payoff") return "回收";
  if (action === "abandon") return "废弃";
  return "变更";
}

function getScoreTone(score: number) {
  if (score <= 5) return "low";
  if (score <= 7) return "mid";
  return "high";
}

function getOutlineKindLabel(kind: string) {
  if (kind === "stage") return "阶段/卷";
  if (kind === "plot_unit") return "剧情单元";
  if (kind === "chapter_group") return "章节组";
  return "大纲节点";
}

function getOutlineStatusLabel(status?: string) {
  if (status === "planned") return "计划中";
  if (status === "in_progress") return "正在写";
  if (status === "completed") return "已完成";
  if (status === "skipped") return "已跳过";
  return null;
}

function getStringField(item: Record<string, unknown>, key: string): string | undefined {
  const value = item[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function buildOutlinePreviewNodes(items: Record<string, unknown>[] = []): OutlinePreviewNode[] {
  const nodes: Array<OutlinePreviewNode & { parentKey?: string }> = items.map((item, index) => {
    const title = getStringField(item, "title") ?? getStringField(item, "nodeTitle") ?? getStringField(item, "nodeId") ?? "未命名节点";
    const key = getStringField(item, "clientKey") ?? getStringField(item, "nodeId") ?? `${title}-${index}`;
    return {
      key,
      title,
      action: getStringField(item, "action") ?? "update",
      kind: getStringField(item, "kind") ?? "unknown",
      status: getStringField(item, "status"),
      estimatedWordCount: typeof item.estimatedWordCount === "number" ? item.estimatedWordCount : undefined,
      content: getStringField(item, "content"),
      children: [],
      parentKey: getStringField(item, "parentKey"),
    };
  });

  const kindOrder: Record<string, number> = { stage: 0, plot_unit: 1, chapter_group: 2 };
  const orderedNodes = [...nodes].sort((a, b) => (kindOrder[a.kind] ?? 9) - (kindOrder[b.kind] ?? 9));
  const byKey = new Map(nodes.map((node) => [node.key, node]));
  const roots: OutlinePreviewNode[] = [];
  let lastStage: (OutlinePreviewNode & { parentKey?: string }) | null = null;
  let lastPlotUnit: (OutlinePreviewNode & { parentKey?: string }) | null = null;

  for (const node of orderedNodes) {
    const parentKey = node.parentKey;
    const parent = parentKey
      ? byKey.get(parentKey)
      : node.kind === "plot_unit"
        ? lastStage
        : node.kind === "chapter_group"
          ? lastPlotUnit
          : null;
    if (parent) parent.children.push(node);
    else roots.push(node);

    if (node.kind === "stage") {
      lastStage = node;
      lastPlotUnit = null;
    } else if (node.kind === "plot_unit") {
      lastPlotUnit = node;
    }
  }

  const sortNodes = (list: OutlinePreviewNode[]) => {
    list.sort((a, b) => (kindOrder[a.kind] ?? 9) - (kindOrder[b.kind] ?? 9));
    for (const node of list) sortNodes(node.children);
  };
  sortNodes(roots);
  return roots;
}

function getOutlinePreviewUpdates(updates: PendingUpdatesData | null | undefined): PendingUpdatesData | null {
  if (!updates?.outlineContent && !updates?.outlineAdjustments?.length && !updates?.outline?.length) return null;
  return updates;
}

const SELECTABLE_ARRAY_UPDATE_SECTIONS: Array<{ section: AgentUpdateSelectionRef["section"]; label: string }> = [
  { section: "characters", label: "角色" },
  { section: "characterExperiences", label: "角色经历" },
  { section: "locations", label: "地点" },
  { section: "items", label: "物品" },
  { section: "factions", label: "势力" },
  { section: "glossaries", label: "术语" },
  { section: "foreshadowing", label: "伏笔" },
  { section: "references", label: "参考资料" },
  { section: "outline", label: "大纲状态" },
  { section: "outlineAdjustments", label: "大纲节点" },
];

const SELECTABLE_TEXT_UPDATE_SECTIONS: Array<{ section: AgentUpdateSelectionRef["section"]; label: string }> = [
  { section: "outlineContent", label: "总纲文本" },
  { section: "worldSetting", label: "世界设定" },
  { section: "storyBackground", label: "故事背景" },
];

function getUpdateSelectionKey(ref: AgentUpdateSelectionRef): string {
  return ref.index === undefined ? ref.section : `${ref.section}:${ref.index}`;
}

function getUpdateItemName(item: Record<string, unknown>): string {
  return String(item.name || item.characterName || item.term || item.title || item.nodeTitle || item.nodeId || item.content || "");
}

function getStructuredUpdateRefs(updates: PendingUpdatesData | null | undefined): AgentUpdateSelectionRef[] {
  if (!updates) return [];
  const refs: AgentUpdateSelectionRef[] = [];

  for (const { section } of SELECTABLE_ARRAY_UPDATE_SECTIONS) {
    const items = updates[section as keyof PendingUpdatesData];
    if (!Array.isArray(items)) continue;
    items.forEach((_, index) => refs.push({ section, index }));
  }

  for (const { section } of SELECTABLE_TEXT_UPDATE_SECTIONS) {
    const value = updates[section as keyof PendingUpdatesData];
    if (typeof value === "string" && value.trim()) refs.push({ section });
  }

  return refs;
}

export function WritingConversation({
  novelId,
  chapterId,
  chapterContext,
  selectedAgents,
  targetWordCount,
  onComplete,
}: WritingConversationProps) {
  const [workspace, dispatchWorkspace] = useReducer(
    reduceSessionWorkspace<ReviewArtifactData>,
    createEmptySessionWorkspace<ReviewArtifactData>()
  );
  const {
    sessionId: currentSessionId,
    taskId,
    phase,
    currentOperation,
    operationStage: currentOperationStage,
    activeReviewArtifact,
  } = workspace;
  const currentSessionIdRef = useRef<string | null>(null);
  const taskIdRef = useRef<string | null>(null);
  const activeReviewArtifactRef = useRef<ReviewArtifactData | null>(null);
  const sessionLoadVersionRef = useRef(0);

  const replaceSessionWorkspace = useCallback((next: SessionWorkspaceState<ReviewArtifactData>) => {
    currentSessionIdRef.current = next.sessionId;
    taskIdRef.current = next.taskId;
    activeReviewArtifactRef.current = next.activeReviewArtifact;
    dispatchWorkspace({ type: "replace", state: next });
  }, []);

  const setTaskId = useCallback((nextTaskId: string | null) => {
    taskIdRef.current = nextTaskId;
    dispatchWorkspace({ type: "set_task", taskId: nextTaskId });
  }, []);

  const setPhase = useCallback((nextPhase: WritingPhase) => {
    dispatchWorkspace({ type: "set_phase", phase: nextPhase });
  }, []);

  const setCurrentOperation = useCallback((operation: CreativeOperation | null) => {
    dispatchWorkspace({ type: "set_operation", operation });
  }, []);

  const setCurrentOperationStage = useCallback((stage: string | null) => {
    dispatchWorkspace({ type: "set_operation_stage", stage });
  }, []);

  const setActiveReviewArtifact = useCallback((artifact: ReviewArtifactData | null) => {
    activeReviewArtifactRef.current = artifact;
    dispatchWorkspace({ type: "set_active_artifact", artifact });
  }, []);

  // 会话状态
  const [sessions, setSessions] = useState<Session[]>([]);
  const [showSessionModal, setShowSessionModal] = useState(false);
  const [showArtifactTray, setShowArtifactTray] = useState(false);

  // 消息状态
  const [messages, setMessages] = useState<Message[]>([]);
  const [reviewDialogArtifact, setReviewDialogArtifact] = useState<ReviewArtifactData | null>(null);
  const [reviewArtifacts, setReviewArtifacts] = useState<ReviewArtifactData[]>([]);
  const [optimisticReviewArtifact, addOptimisticReviewArtifactDecision] = useOptimistic(
    activeReviewArtifact,
    (
      current,
      action: { artifactId: string; decision: ReviewArtifactDecision }
    ) => applyOptimisticReviewArtifactDecision(current, action)
  );
  const [showReviewArtifactModal, setShowReviewArtifactModal] = useState(false);
  const [reviewDraftText, setReviewDraftText] = useState("");
  const [selectedUpdateRefKeys, setSelectedUpdateRefKeys] = useState<Set<string>>(new Set());
  const [reviewArtifactAction, setReviewArtifactAction] = useState<ReviewArtifactActionState | null>(null);
  const [chapterTargetPrompt, setChapterTargetPrompt] = useState<ChapterTargetPrompt | null>(null);
  const [reviewDraftSourceKey, setReviewDraftSourceKey] = useState<string | null>(null);
  const [reviewUpdateSelectionSourceKey, setReviewUpdateSelectionSourceKey] = useState<string | null>(null);

  // 其他状态
  const [generatedContent, setGeneratedContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const [userInput, setUserInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isAssigningTask, setIsAssigningTask] = useState(false);
  const [agentLiveRuns, setAgentLiveRuns] = useState<AgentLiveRuns>({});
  const agentLiveRunsRef = useRef<AgentLiveRuns>({});

  const applyAgentLiveAction = useCallback((action: AgentLiveAction) => {
    const next = reduceAgentLiveRuns(agentLiveRunsRef.current, action);
    agentLiveRunsRef.current = next;
    setAgentLiveRuns(next);
  }, []);

  const clearAgentLiveRuns = useCallback(() => {
    applyAgentLiveAction({ type: "reset" });
  }, [applyAgentLiveAction]);

  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const [agentPickerQuery, setAgentPickerQuery] = useState("");
  const [agentPickerActiveIndex, setAgentPickerActiveIndex] = useState(0);

  // 中断控制
  const abortRef = useRef<AbortController | null>(null);
  const sendGuardRef = useRef(createAsyncActionGuard());
  const eventCursorsRef = useRef(createWritingEventCursors());

  const [cursorPosition, setCursorPosition] = useState(0);
  const [showFlowLog, setShowFlowLog] = useState(false);
  const [flowLogs, setFlowLogs] = useState<FlowLogEntry[]>([]);
  const [activityState, setActivityState] = useState<AgentActivityState>(EMPTY_AGENT_ACTIVITY_STATE);
  const activityStateRef = useRef<AgentActivityState>(EMPTY_AGENT_ACTIVITY_STATE);

  const applyAgentActivityAction = useCallback((action: AgentActivityAction) => {
    const next = reduceAgentActivityState(activityStateRef.current, action);
    activityStateRef.current = next;
    setActivityState(next);
  }, []);

  const resetAgentActivity = useCallback(() => {
    applyAgentActivityAction({ type: "reset" });
  }, [applyAgentActivityAction]);

  const activityRounds = activityState.rounds;

  // 编辑相关
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  const reviewArtifactActionRef = useRef<ReviewArtifactActionState | null>(null);
  const reviewActionCloseTimerRef = useRef<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const pendingReviewArtifactRefreshRef = useRef(false);

  const updateReviewArtifactAction = useCallback((next: ReviewArtifactActionState | null) => {
    reviewArtifactActionRef.current = next;
    setReviewArtifactAction(next);
  }, []);

  const resetSessionContext = useCallback((sessionId: string | null) => {
    sessionLoadVersionRef.current += 1;
    replaceSessionWorkspace(createEmptySessionWorkspace<ReviewArtifactData>(sessionId));
    setMessages([]);
    setGeneratedContent("");
    setError(null);
    setReviewDialogArtifact(null);
    setShowReviewArtifactModal(false);
    setChapterTargetPrompt(null);
    setReviewDraftText("");
    setSelectedUpdateRefKeys(new Set());
    setReviewDraftSourceKey(null);
    setReviewUpdateSelectionSourceKey(null);
    pendingReviewArtifactRefreshRef.current = false;
    updateReviewArtifactAction(null);
    resetAgentActivity();
    clearAgentLiveRuns();
    setIsAssigningTask(false);
  }, [clearAgentLiveRuns, replaceSessionWorkspace, resetAgentActivity, updateReviewArtifactAction]);

  const clearReviewActionCloseTimer = useCallback(() => {
    if (reviewActionCloseTimerRef.current === null) return;
    window.clearTimeout(reviewActionCloseTimerRef.current);
    reviewActionCloseTimerRef.current = null;
  }, []);

  const openReviewArtifactModal = useCallback((artifact: ReviewArtifactData) => {
    clearReviewActionCloseTimer();
    if (
      reviewArtifactActionRef.current &&
      reviewArtifactActionRef.current.status !== "pending" &&
      reviewArtifactActionRef.current.artifactId !== artifact.id
    ) {
      updateReviewArtifactAction(null);
    }
    setReviewDialogArtifact(artifact);
    const draftSourceKey = `${artifact.id}:${artifact.revision}`;
    if (reviewDraftSourceKey !== draftSourceKey) {
      setReviewDraftSourceKey(draftSourceKey);
      setReviewDraftText(getReviewArtifactContent(artifact));
    }
    const updateSelectionSourceKey = `${artifact.id}:${artifact.revision}:updates`;
    if (reviewUpdateSelectionSourceKey !== updateSelectionSourceKey) {
      setReviewUpdateSelectionSourceKey(updateSelectionSourceKey);
      setSelectedUpdateRefKeys(new Set(getStructuredUpdateRefs(artifact.payload?.updates).map(getUpdateSelectionKey)));
    }
    setShowReviewArtifactModal(true);
  }, [
    clearReviewActionCloseTimer,
    reviewDraftSourceKey,
    reviewUpdateSelectionSourceKey,
    updateReviewArtifactAction,
  ]);

  const closeReviewArtifactModal = useCallback((options?: { force?: boolean }) => {
    if (!options?.force && reviewArtifactActionRef.current?.status === "pending") return;
    clearReviewActionCloseTimer();
    setShowReviewArtifactModal(false);
    setReviewDialogArtifact(null);
    updateReviewArtifactAction(null);
  }, [clearReviewActionCloseTimer, updateReviewArtifactAction]);

  const focusChatForArtifactRevision = useCallback(() => {
    closeReviewArtifactModal({ force: true });
    setPhase("recording");
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [closeReviewArtifactModal, setPhase]);

  const scheduleReviewArtifactModalClose = useCallback(() => {
    clearReviewActionCloseTimer();
    reviewActionCloseTimerRef.current = window.setTimeout(() => {
      closeReviewArtifactModal({ force: true });
      reviewActionCloseTimerRef.current = null;
    }, 900);
  }, [clearReviewActionCloseTimer, closeReviewArtifactModal]);

  const getReviewArtifactAction = useCallback((artifactId: string) => {
    return reviewArtifactAction?.artifactId === artifactId ? reviewArtifactAction : null;
  }, [reviewArtifactAction]);

  useEffect(() => {
    return () => {
      clearReviewActionCloseTimer();
    };
  }, [clearReviewActionCloseTimer]);

  const getLocalReviewDraftForApply = useCallback((artifact: ReviewArtifactData): string | undefined => {
    if (!getReviewArtifactContent(artifact)) return undefined;
    const draftSourceKey = `${artifact.id}:${artifact.revision}`;
    if (reviewDraftSourceKey !== draftSourceKey) return undefined;
    return reviewDraftText;
  }, [reviewDraftSourceKey, reviewDraftText]);

  const getSelectedUpdateRefsForApply = useCallback((artifact: ReviewArtifactData): AgentUpdateSelectionRef[] | undefined => {
    const allRefs = getStructuredUpdateRefs(artifact.payload?.updates);
    if (allRefs.length === 0) return undefined;
    const updateSelectionSourceKey = `${artifact.id}:${artifact.revision}:updates`;
    if (reviewUpdateSelectionSourceKey !== updateSelectionSourceKey) return undefined;
    return allRefs.filter((ref) => selectedUpdateRefKeys.has(getUpdateSelectionKey(ref)));
  }, [reviewUpdateSelectionSourceKey, selectedUpdateRefKeys]);

  const toggleUpdateSelection = useCallback((ref: AgentUpdateSelectionRef) => {
    const key = getUpdateSelectionKey(ref);
    setSelectedUpdateRefKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const selectAllStructuredUpdates = useCallback((artifact: ReviewArtifactData) => {
    setSelectedUpdateRefKeys(new Set(getStructuredUpdateRefs(artifact.payload?.updates).map(getUpdateSelectionKey)));
  }, []);

  const clearStructuredUpdateSelection = useCallback(() => {
    setSelectedUpdateRefKeys(new Set());
  }, []);

  // 加载会话列表
  const loadSessions = useCallback(async () => {
    try {
      const data = requireApiData(await browserApi.GET("/api/v1/writing/sessions", {
        params: { query: { novelId, chapterId } },
      }));
      setSessions(data);
    } catch (err) {
      console.error("加载会话列表失败", err);
    }
  }, [novelId, chapterId]);

  const loadReviewArtifacts = useCallback(async () => {
    try {
      const currentTaskId = taskIdRef.current;
      if (!currentTaskId) {
        setReviewArtifacts([]);
        return;
      }
      const artifact = requireApiData(await browserApi.GET(
        "/api/v1/writing/tasks/{task_id}/artifact",
        { params: { path: { task_id: currentTaskId } }, cache: "no-store" },
      )) as ReviewArtifactData | null;
      setReviewArtifacts(artifact && isActionableReviewArtifact(artifact) ? [artifact] : []);
    } catch (err) {
      console.error("加载待确认变更失败", err);
    }
  }, []);

  // 加载会话消息
  const loadSessionMessages = useCallback(async (sessionId: string) => {
    const requestVersion = sessionLoadVersionRef.current;
    try {
      const session = requireApiData(await browserApi.GET(
        "/api/v1/writing/sessions/{session_id}",
        { params: { path: { session_id: sessionId } } },
      )) as LoadedSessionResponse;
        if (
          currentSessionIdRef.current !== sessionId ||
          sessionLoadVersionRef.current !== requestVersion
        ) {
          return;
        }
        const loadedMessages: Message[] = session.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "agent" | "system",
          agentId: m.agentId || undefined,
          agentName: m.agentId ? AGENT_REGISTRY.find(a => a.id === m.agentId)?.name : undefined,
          content: normalizeParagraphTextDisplay(m.content),
          intent: m.intent || undefined,
          timestamp: new Date(m.createdAt).getTime(),
        }));

        const sessionTaskState = resolveLoadedSessionRecoveryState(session.currentTask ?? null);
        setReviewDialogArtifact(null);
        updateReviewArtifactAction(null);
        setShowReviewArtifactModal(false);
        setReviewDraftSourceKey(null);
        setReviewDraftText("");
        setMessages(loadedMessages);
        replaceSessionWorkspace({
          sessionId,
          taskId: sessionTaskState.taskId,
          phase: sessionTaskState.phase,
          currentOperation: sessionTaskState.currentOperation,
          operationStage: sessionTaskState.operationStage,
          activeReviewArtifact: null,
        });
        resetAgentActivity();
        setIsAssigningTask(false);
        clearAgentLiveRuns();
        pendingReviewArtifactRefreshRef.current =
          sessionTaskState.shouldRefreshAwaitingReviewArtifact;
    } catch (err) {
      console.error("加载会话消息失败", err);
    }
  }, [clearAgentLiveRuns, replaceSessionWorkspace, resetAgentActivity, updateReviewArtifactAction]);

  // 创建新会话
  const createSession = useCallback(async (): Promise<string | null> => {
    try {
      const session = requireApiData(await browserApi.POST("/api/v1/writing/sessions", {
        body: { novelId, chapterId },
      }));
      await loadSessions();
      resetSessionContext(session.id);
      setShowSessionModal(false);
      return session.id;
    } catch (err) {
      console.error("创建会话失败", err);
    }
    return null;
  }, [novelId, chapterId, loadSessions, resetSessionContext]);

  // 删除会话
  const deleteSession = useCallback(async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除这个会话吗？")) return;
    try {
      requireApiData(await browserApi.DELETE("/api/v1/writing/sessions/{session_id}", {
        params: { path: { session_id: sessionId } },
      }));
      await loadSessions();
      if (currentSessionId === sessionId) {
        resetSessionContext(null);
      }
    } catch (err) {
      console.error("删除会话失败", err);
    }
  }, [currentSessionId, loadSessions, resetSessionContext]);

  // 保存消息到服务器
  const saveMessageToServer = useCallback(async (
    role: "user" | "agent" | "system",
    content: string,
    agentId?: string,
    intent?: string,
    explicitSessionId?: string | null
  ) => {
    const targetSessionId = explicitSessionId ?? currentSessionId;
    if (!targetSessionId) return;

    try {
      requireApiData(await browserApi.POST("/api/v1/writing/sessions/{session_id}/messages", {
        params: { path: { session_id: targetSessionId } },
        body: {
          role,
          agentId: agentId ?? null,
          content,
          intent: intent ?? null,
        },
      }));
    } catch (err) {
      console.error("保存消息失败", err);
    }
  }, [currentSessionId]);

  // 选择会话
  const selectSession = useCallback(async (sessionId: string) => {
    resetSessionContext(sessionId);
    await loadSessionMessages(sessionId);
    setShowSessionModal(false);
  }, [loadSessionMessages, resetSessionContext]);

  // 初始加载
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadSessions();
      void loadReviewArtifacts();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadSessions, loadReviewArtifacts]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const addMessage = useCallback((msg: AddMessageInput) => {
    const { sessionId, persist, ...message } = msg;
    const newMsg: Message = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp: Date.now(),
      ...message,
    };
    setMessages((prev) => [...prev, newMsg]);
    if (shouldPersistOptimisticWritingMessage({ persist })) {
      saveMessageToServer(msg.role, msg.content, msg.agentId, msg.intent, sessionId);
    }
    setTimeout(scrollToBottom, 50);
    return newMsg.id;
  }, [saveMessageToServer]);

  const getAgentInfo = (agentId: string) => {
    return AGENT_INFO[agentId] ?? { tone: "gray", emoji: "助" };
  };

  const getAgentName = useCallback((agentId: string): string => {
    if (agentId === "system") return "系统";
    return AGENT_REGISTRY.find((a) => a.id === agentId)?.name ?? agentId;
  }, []);

  const startActivityRound = useCallback((agentId: string) => {
    const roundId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    applyAgentActivityAction({ type: "start", agentId, roundId, now: Date.now() });
    return roundId;
  }, [applyAgentActivityAction]);

  const addActivityEntry = useCallback((entry: Omit<ToolActivityEntry, "id" | "timestamp">) => {
    if (!entry.agentId) return;
    const roundId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const nextEntry: ToolActivityEntry = {
      ...entry,
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp: Date.now(),
    };
    applyAgentActivityAction({
      type: "add",
      agentId: entry.agentId,
      roundId,
      entry: nextEntry,
      now: Date.now(),
    });
  }, [applyAgentActivityAction]);

  const attachActivityRoundToMessage = useCallback((agentId: string, messageId: string) => {
    applyAgentActivityAction({ type: "attach", agentId, messageId, now: Date.now() });
  }, [applyAgentActivityAction]);

  const finishActivityRound = useCallback((status: "done" | "error" = "done", agentId?: string) => {
    const errorEntry: ToolActivityEntry | undefined = status === "error"
      ? {
          id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
          status: "error",
          label: "出错",
          message: "处理出错",
          timestamp: Date.now(),
        }
      : undefined;
    applyAgentActivityAction({
      type: "finish",
      agentId,
      status,
      now: Date.now(),
      errorEntry,
    });
  }, [applyAgentActivityAction]);

  const discardActivityRound = useCallback((agentId: string) => {
    applyAgentActivityAction({ type: "discard", agentId });
  }, [applyAgentActivityAction]);

  const discardActiveActivityRounds = useCallback(() => {
    const activeAgentIds = Object.keys(activityStateRef.current.activeRoundIds);
    for (const agentId of activeAgentIds) {
      applyAgentActivityAction({ type: "discard", agentId });
    }
  }, [applyAgentActivityAction]);

  // 中断当前 Agent 并立即开始处理新消息
  const abortCurrentAgent = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setIsSending(false);
    setIsAssigningTask(false);
    clearAgentLiveRuns();
    discardActiveActivityRounds();
  }, [clearAgentLiveRuns, discardActiveActivityRounds]);

  const toggleActivityRound = useCallback((roundId: string) => {
    applyAgentActivityAction({ type: "toggle", roundId });
  }, [applyAgentActivityAction]);

  const formatOperationLog = useCallback((operation: CreativeOperation): string => {
    const label = getCreativeOperationLabel(operation.kind);
    return `${label} → ${getAgentName(operation.primaryAgent)} · ${operation.userGoal}`;
  }, [getAgentName]);

  /** 获取状态标签 */
  const getStatusLabel = (status: string): string => {
    const labels: Record<string, string> = {
      understanding: "理解需求",
      thinking: "思考中",
      asking: "询问",
      discussing: "分析",
      drafting: "生成设定",
      refining: "细化设定",
      querying: "查询",
      responding: "输出回复",
      parsing: "整理结果",
      suggestions: "生成建议",
      completed: "完成",
      done: "完成",
      error: "出错",
    };
    return labels[status] || "处理";
  };

  const handleInputChange = useCallback((value: string, cursorPos: number) => {
    setUserInput(value);
    setCursorPosition(cursorPos);

    const textBeforeCursor = value.slice(0, cursorPos);
    const lastAtIndex = textBeforeCursor.lastIndexOf("@");

    if (lastAtIndex !== -1) {
      const textAfterAt = textBeforeCursor.slice(lastAtIndex + 1);
      if (!textAfterAt.includes(" ") && textAfterAt.length <= 20) {
        setAgentPickerQuery(textAfterAt);
        setShowAgentPicker(true);
        setAgentPickerActiveIndex(0);
        return;
      }
    }

    setShowAgentPicker(false);
    setAgentPickerQuery("");
    setAgentPickerActiveIndex(0);
  }, []);

  const insertAgentMention = useCallback((agentId: string) => {
    const textBeforeCursor = userInput.slice(0, cursorPosition);
    const lastAtIndex = textBeforeCursor.lastIndexOf("@");

    if (lastAtIndex !== -1) {
      const beforeAt = userInput.slice(0, lastAtIndex);
      const afterCursor = userInput.slice(cursorPosition);
      const mention = `@${agentId}`;
      const newValue = `${beforeAt}${mention} ${afterCursor}`;
      setUserInput(newValue);
      setShowAgentPicker(false);
      setAgentPickerQuery("");
      setAgentPickerActiveIndex(0);

      setTimeout(() => {
        inputRef.current?.focus();
        const newCursorPos = beforeAt.length + mention.length + 1;
        inputRef.current?.setSelectionRange(newCursorPos, newCursorPos);
      }, 0);
    }
  }, [userInput, cursorPosition]);

  const agentStartTimes = useRef<Map<string, number>>(new Map());

  const addFlowLog = useCallback((entry: Omit<FlowLogEntry, "id" | "timestamp">) => {
    const newEntry: FlowLogEntry = {
      ...entry,
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp: Date.now(),
    };
    setFlowLogs((prev) => [...prev, newEntry]);
  }, []);

  const setWorkflowReviewArtifact = useCallback((artifact: ReviewArtifactData) => {
    const nextTaskId = resolveReviewArtifactTaskId(taskIdRef.current ?? taskId, artifact);
    if (nextTaskId && nextTaskId !== taskIdRef.current) {
      setTaskId(nextTaskId);
    }
    setActiveReviewArtifact(artifact);
    setReviewArtifacts((prev) => {
      const rest = prev.filter((item) => item.id !== artifact.id);
      return isActionableReviewArtifact(artifact) ? [artifact, ...rest] : rest;
    });
    if (artifact.status === "awaiting_user") setPhase("recording");
    setMessages((prev) => attachReviewArtifactToConversation<Message, ReviewArtifactData>(prev, artifact, () => ({
      id: `restored-review-${artifact.id}`,
      role: "system",
      content: "待确认变更已更新。请在下方卡片中查看、修改或应用。",
      timestamp: Date.now(),
    })));
  }, [setActiveReviewArtifact, setPhase, setTaskId, taskId]);

  const inspectReviewArtifactFromTray = useCallback((artifact: ReviewArtifactData) => {
    setReviewArtifacts((prev) => {
      const rest = prev.filter((item) => item.id !== artifact.id);
      return isActionableReviewArtifact(artifact) ? [artifact, ...rest] : rest;
    });
    setShowArtifactTray(false);
    openReviewArtifactModal(artifact);
  }, [openReviewArtifactModal]);

  const updateDetachedReviewArtifact = useCallback((artifact: ReviewArtifactData) => {
    setReviewArtifacts((prev) => {
      const rest = prev.filter((item) => item.id !== artifact.id);
      return isActionableReviewArtifact(artifact) ? [artifact, ...rest] : rest;
    });
    setReviewDialogArtifact((current) => current?.id === artifact.id ? artifact : current);
  }, []);

  const refreshAwaitingReviewArtifact = useCallback(async (reason: string) => {
    const currentTaskId = taskIdRef.current ?? taskId;
    if (!currentTaskId) return;
    try {
      const artifact = requireApiData(await browserApi.GET(
        "/api/v1/writing/tasks/{task_id}/artifact",
        { params: { path: { task_id: currentTaskId } }, cache: "no-store" },
      )) as ReviewArtifactData | null;
      if (!artifact) return;

      setWorkflowReviewArtifact(artifact);
      addFlowLog({
        type: "phase",
        content: `已恢复待确认变更入口：${artifact.artifactKey ?? artifact.id}`,
      });
      console.debug("[写作草案] 已恢复待确认变更", {
        reason,
        artifactId: artifact.id,
        status: artifact.status,
      });
    } catch (err) {
      console.warn("[写作草案] 恢复失败", err);
    }
  }, [addFlowLog, setWorkflowReviewArtifact, taskId]);

  useEffect(() => {
    if (pendingReviewArtifactRefreshRef.current) {
      pendingReviewArtifactRefreshRef.current = false;
      const timer = window.setTimeout(() => {
        void refreshAwaitingReviewArtifact("session_select");
      }, 0);
      return () => window.clearTimeout(timer);
    }
    if (activeReviewArtifactRef.current?.status === "awaiting_user") return;
    const timer = window.setTimeout(() => {
      void refreshAwaitingReviewArtifact("initial_load");
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshAwaitingReviewArtifact]);

  const handleDetachedArtifactEvent = useCallback((event: WritingSseEvent, artifactId: string) => {
    switch (event.type) {
      case "user_input_required":
      case "artifact_submitted":
      case "artifact_awaiting_user_approval":
      case "review_artifact_requested":
        if ("artifact" in event && event.artifact) {
          updateDetachedReviewArtifact(event.artifact as ReviewArtifactData);
        }
        void loadReviewArtifacts();
        break;

      case "artifact_applied":
        if (event.success) {
          updateReviewArtifactAction({
            artifactId: event.artifactId,
            decision: "approve",
            status: "succeeded",
            message: getReviewArtifactActionMessage("approve", "succeeded", event.summary),
          });
          setReviewArtifacts((prev) => prev.filter((artifact) => artifact.id !== event.artifactId));
          onComplete?.();
          scheduleReviewArtifactModalClose();
        } else {
          updateReviewArtifactAction({
            artifactId: event.artifactId,
            decision: "approve",
            status: "failed",
            message: getReviewArtifactActionMessage("approve", "failed", event.errors?.join("\n") || event.summary),
          });
          if (event.artifact) updateDetachedReviewArtifact(event.artifact as ReviewArtifactData);
          setError(event.errors?.join("\n") || event.summary || "应用待确认变更失败");
        }
        void loadSessions();
        void loadReviewArtifacts();
        break;

      case "artifact_deleted":
        updateReviewArtifactAction({
          artifactId: event.artifactId,
          decision: "discard",
          status: "succeeded",
          message: getReviewArtifactActionMessage("discard", "succeeded"),
        });
        setReviewArtifacts((prev) => prev.filter((artifact) => artifact.id !== event.artifactId));
        onComplete?.();
        void loadReviewArtifacts();
        scheduleReviewArtifactModalClose();
        break;

      case "resume":
        if (
          event.resumeType === "artifact_revision" &&
          reviewArtifactActionRef.current?.artifactId === artifactId &&
          reviewArtifactActionRef.current.decision === "revise" &&
          reviewArtifactActionRef.current.status === "pending"
        ) {
          updateReviewArtifactAction({
            artifactId,
            decision: "revise",
            status: "succeeded",
            message: getReviewArtifactActionMessage("revise", "succeeded"),
          });
          scheduleReviewArtifactModalClose();
        }
        break;

      case "done":
      case "completed":
        void loadSessions();
        void loadReviewArtifacts();
        break;

      case "error":
        if (reviewArtifactActionRef.current?.artifactId === artifactId) {
          updateReviewArtifactAction({
            ...reviewArtifactActionRef.current,
            status: "failed",
            message: getReviewArtifactActionMessage(
              reviewArtifactActionRef.current.decision,
              "failed",
              event.message ?? undefined
            ),
          });
        }
        setError(event.message ?? "处理待确认变更失败");
        break;

      default:
        break;
    }
  }, [loadReviewArtifacts, loadSessions, onComplete, scheduleReviewArtifactModalClose, updateDetachedReviewArtifact, updateReviewArtifactAction]);

  const handleEvent = useCallback((event: WritingSseEvent, scope: StreamUiScope) => {
    if (scope.mode === "session" && !isCurrentSessionStream(currentSessionIdRef.current, scope.sessionId)) {
      return;
    }
    if (scope.mode === "artifact") {
      handleDetachedArtifactEvent(event, scope.artifactId);
      return;
    }

    if (
      event.type === "user_input_required" ||
      event.type === "artifact_submitted" ||
      event.type === "artifact_awaiting_user_approval" ||
      event.type === "artifact_applied" ||
      event.type === "artifact_deleted" ||
      event.type === "review_artifact_requested"
    ) {
      console.debug("[WritingReviewArtifact] event", {
        type: event.type,
        phase: "phase" in event ? event.phase : undefined,
        artifactId: "artifactId" in event ? event.artifactId : undefined,
        artifactStatus:
          "artifact" in event &&
          event.artifact &&
          typeof event.artifact === "object" &&
          "status" in event.artifact
            ? (event.artifact as { status?: string }).status
            : undefined,
      });
    }

    switch (event.type) {
      case "start":
        setTaskId(event.taskId ?? null);
        setFlowLogs([]);
        setCurrentOperation(null);
        setCurrentOperationStage(null);
        setIsAssigningTask(true);
        addFlowLog({ type: "user", content: "会话开始" });
        break;

      case "classifying_intent":
        setIsAssigningTask(true);
        break;

      case "phase_start":
      case "phase_change":
        setPhase(event.phase as WritingPhase);
        addFlowLog({
          type: "phase",
          content: `阶段: ${event.phase}${"agents" in event && event.agents ? ` (${event.agents.join(", ")})` : ""}`,
        });
        break;

      case "agent_start": {
        const agentId = event.agentId as AgentId;
        setIsAssigningTask(false);
        applyAgentLiveAction({
          type: "start",
          agentId,
          startedAt: Date.now(),
          statusMessage: `${getAgentName(agentId)}正在接手...`,
        });
        startActivityRound(agentId);
        agentStartTimes.current.set(event.agentId, Date.now());
        addFlowLog({ type: "agent_start", agentId: event.agentId, content: `${getAgentName(event.agentId)} 开始` });
        break;
      }

      case "agent_status": {
        const agentId = event.agentId as AgentId;
        const visibleToolActivity = Boolean(event.toolName && isVisibleToolActivity(event.toolName));
        if (event.status === "error" && event.message) {
          addMessage({ role: "system", content: event.message, persist: false });
          setError(event.message);
        }
        if (!event.toolName || visibleToolActivity) {
          const statusMessage = visibleToolActivity
            ? ("resultSummary" in event && event.resultSummary) || event.message || `正在${getToolActivityLabel(event.toolName!)}`
            : event.message || getStatusLabel(event.status || "thinking");
          applyAgentLiveAction({
            type: "status",
            agentId,
            statusMessage,
            startedAt: agentStartTimes.current.get(agentId) ?? Date.now(),
          });
        }
        if (event.toolName && visibleToolActivity) {
          const toolLabel = getToolActivityLabel(event.toolName);
          const resultSummary = "resultSummary" in event && typeof event.resultSummary === "string"
            ? event.resultSummary
            : "";
          addActivityEntry({
            status: "querying",
            label: getStatusLabel("querying"),
            message: resultSummary || `正在${toolLabel}`,
            agentId: event.agentId,
            toolName: event.toolName,
            toolLabel,
            argsSummary: event.argsSummary && event.argsSummary !== "无参数" ? event.argsSummary : undefined,
            resultSummary,
          });
        } else if (!event.toolName) {
          const status = event.status || "thinking";
          addActivityEntry({
            status,
            label: getStatusLabel(status),
            message: event.message || getStatusLabel(status),
            agentId: event.agentId,
          });
        }
        addFlowLog({ 
          type: "agent_status",
          agentId: event.agentId,
          content: event.toolName
            ? `调用工具：${event.toolName}${event.argsSummary ? `（${event.argsSummary}）` : ""}${"resultSummary" in event && event.resultSummary ? ` → ${event.resultSummary}` : ""}${event.detailsHidden ? "，结果已隐藏" : ""}`
            : `[${event.status}] ${event.message}${event.question ? `\n问题: ${event.question}` : ""}`
        });
        break;
      }

      case "agent_chunk": {
        const agentId = event.agentId as AgentId;
        applyAgentLiveAction({
          type: "chunk",
          agentId,
          chunk: event.chunk,
          startedAt: agentStartTimes.current.get(agentId) ?? Date.now(),
        });
        break;
      }

      case "agent_done": {
        const agentId = event.agentId as AgentId;
        const bufferedContent = agentLiveRunsRef.current[agentId]?.content;
        const duration = agentStartTimes.current.get(event.agentId);

        // Phase D 返工：新协议下 content 是段落文本，不解析 business protocol。
        // 不调用 extractDisplayContent()，直接使用原始内容。
        const rawEventContent = "content" in event && typeof event.content === "string"
          ? event.content
          : undefined;
        const finalContent = resolveFinalAgentContent(rawEventContent, bufferedContent);

        console.debug("[SSE] agent_done:", {
          agentId: event.agentId,
          savedLen: bufferedContent?.length ?? 0,
          eventHasContent: "content" in event,
          eventContentLen: ("content" in event ? (event as { content?: string }).content?.length ?? 0 : 0),
          finalLen: finalContent?.length ?? 0,
        });

        if (finalContent) {
          const messageId = addMessage({
            role: "agent",
            agentId: event.agentId,
            agentName: getAgentName(event.agentId),
            content: finalContent,
            isNewProtocol: true, // Phase D：新协议消息，不解析 assistant prose
            persist: false,
          });
          attachActivityRoundToMessage(agentId, messageId);
          finishActivityRound("done", agentId);
        } else {
          discardActivityRound(agentId);
        }
        applyAgentLiveAction({ type: "finish", agentId });
        agentStartTimes.current.delete(event.agentId);
        addFlowLog({
          type: "agent_done",
          agentId: event.agentId,
          content: `${getAgentName(event.agentId)} 完成`,
          duration: duration ? Date.now() - duration : undefined,
        });
        break;
      }

      case "operation_classified":
        setCurrentOperation(event.operation);
        setIsAssigningTask(false);
        break;

      case "operation_stage":
        setCurrentOperationStage(event.stage);
        addFlowLog({
          type: "operation",
          content: `${event.stage}：${event.message ?? event.label}`,
        });
        break;

      case "intent_classified":
        if (event.operation) {
          setCurrentOperation(event.operation);
        } else {
          addFlowLog({
            type: "intent",
            agentId: event.targetAgent ?? undefined,
            content: `意图分类: ${event.targetAgent ? getAgentName(event.targetAgent) : "未确定"} · ${event.reasoning}`,
          });
        }
        break;

      case "command_parsed":
        if (event.operation) {
          setCurrentOperation(event.operation);
          addFlowLog({
            type: "operation",
            agentId: event.operation.primaryAgent,
            content: formatOperationLog(event.operation),
          });
        }
        break;

      case "user_input_required":
        if ("decisionType" in event && event.decisionType === "chapter_target_confirmation") {
          setChapterTargetPrompt({
            summary: "summary" in event ? event.summary : undefined,
            content: "content" in event ? event.content : undefined,
          });
          setPhase("recording");
          addFlowLog({ type: "phase", content: ("summary" in event ? event.summary : undefined) ?? "需要确认正文写入目标" });
          break;
        }
        if (event.phase === "recording") {
          setPhase("recording");
        } else if (event.phase === "generating") {
          setPhase("generating");
        } else {
          setPhase("discussing");
        }
        if (event.generatedContent) {
          setGeneratedContent(event.generatedContent);
        }
        if (event.pendingUpdates && messages.length > 0) {
          setMessages((prev) => {
            const newMsgs = [...prev];
            const lastIndex = newMsgs.length - 1;
            return newMsgs.map((m, i) =>
              i === lastIndex ? { ...m, pendingUpdates: event.pendingUpdates as PendingUpdatesData } : m
            );
          });
        }
        if ("artifact" in event && event.artifact) {
          const artifact = event.artifact as ReviewArtifactData;
          setWorkflowReviewArtifact(artifact);
        }
        break;

      case "updates_saved":
        if (event.success) {
          setPhase("completed");
          addFlowLog({
            type: "phase",
            content: event.summary ?? `已保存 ${event.savedCount ?? 0} 项设定变更`,
          });
          loadSessions();
          onComplete?.();
        } else {
          setPhase("error");
          setError(event.errors?.join("\n") || event.summary || "保存设定失败");
        }
        break;

      case "updates_declined":
        setPhase("discussing");
        addFlowLog({ type: "phase", content: "已取消保存设定变更" });
        break;

      case "artifact_submitted":
      case "artifact_awaiting_user_approval":
        if ("artifact" in event && event.artifact) {
          const artifact = event.artifact as ReviewArtifactData;
          setWorkflowReviewArtifact(artifact);
        }
        void loadReviewArtifacts();
        if (event.type === "artifact_awaiting_user_approval") {
          setPhase("recording");
          if (!("artifact" in event) || !event.artifact) {
            void refreshAwaitingReviewArtifact("awaiting_user_event_missing_artifact");
          }
        }
        addFlowLog({
          type: "phase",
          content: event.type === "artifact_awaiting_user_approval"
            ? "待确认变更已通过 Agent 复审，等待你确认"
            : `已提交待确认变更 ${event.artifactId}`,
        });
        break;

      case "review_artifact_requested":
        if ("artifact" in event && event.artifact) {
          const artifact = event.artifact as ReviewArtifactData;
          setWorkflowReviewArtifact(artifact);
          setShowArtifactTray(false);
          addFlowLog({
            type: "phase",
            content: `Agent 请求刷新变更卡片：${artifact.artifactKey ?? artifact.id}`,
          });
        }
        void loadReviewArtifacts();
        break;

      case "artifact_review_started":
        addFlowLog({
          type: "phase",
          content: `ReviewArtifact ${event.artifactId} routed to ${getAgentName(event.toAgent)} for review`,
        });
        break;

      case "artifact_applied":
        if (event.success) {
          updateReviewArtifactAction({
            artifactId: event.artifactId,
            decision: "approve",
            status: "succeeded",
            message: getReviewArtifactActionMessage("approve", "succeeded", event.summary),
          });
          setActiveReviewArtifact(null);
          setReviewArtifacts((prev) => prev.filter((artifact) => artifact.id !== event.artifactId));
          setMessages((prev) => clearReviewArtifactFromMessages(prev, event.artifactId));
          setPhase("completed");
          addFlowLog({ type: "phase", content: event.summary ?? "待确认变更已应用到正式库" });
          loadSessions();
          loadReviewArtifacts();
          onComplete?.();
          scheduleReviewArtifactModalClose();
        } else {
          updateReviewArtifactAction({
            artifactId: event.artifactId,
            decision: "approve",
            status: "failed",
            message: getReviewArtifactActionMessage("approve", "failed", event.errors?.join("\n") || event.summary),
          });
          if (event.artifact) {
            setWorkflowReviewArtifact(event.artifact as ReviewArtifactData);
          }
          setPhase("error");
          setError(event.errors?.join("\n") || event.summary || "应用待确认变更失败");
        }
        break;

      case "artifact_deleted":
        updateReviewArtifactAction({
          artifactId: event.artifactId,
          decision: "discard",
          status: "succeeded",
          message: getReviewArtifactActionMessage("discard", "succeeded"),
        });
        setActiveReviewArtifact(null);
        setReviewArtifacts((prev) => prev.filter((artifact) => artifact.id !== event.artifactId));
        setMessages((prev) => clearReviewArtifactFromMessages(prev, event.artifactId));
        setPhase("completed");
        addFlowLog({ type: "phase", content: "已丢弃待确认变更" });
        onComplete?.();
        loadReviewArtifacts();
        scheduleReviewArtifactModalClose();
        break;

      case "resume":
        if (
          event.resumeType === "artifact_revision" &&
          reviewArtifactActionRef.current?.decision === "revise" &&
          reviewArtifactActionRef.current.status === "pending"
        ) {
          updateReviewArtifactAction({
            artifactId: reviewArtifactActionRef.current.artifactId,
            decision: "revise",
            status: "succeeded",
            message: getReviewArtifactActionMessage("revise", "succeeded"),
          });
          scheduleReviewArtifactModalClose();
        }
        setError(null);
        clearAgentLiveRuns();
        addFlowLog({
          type: "phase",
          content: event.resumeType === "interrupt_resume"
            ? "恢复中断的会话"
            : `恢复会话${event.lastActiveAgent ? `（上次活跃: ${getAgentName(event.lastActiveAgent)}）` : ""}`,
        });
        break;

      case "completed":
      case "done":
        finishActivityRound("done");
        clearAgentLiveRuns();
        if (reviewArtifactActionRef.current?.status === "pending") {
          const completedAction = reviewArtifactActionRef.current;
          updateReviewArtifactAction({
            ...completedAction,
            status: "succeeded",
            message: getReviewArtifactActionMessage(
              completedAction.decision,
              "succeeded",
            ),
          });
          setActiveReviewArtifact(null);
          setReviewArtifacts((previous) => previous.filter(
            (artifact) => artifact.id !== completedAction.artifactId,
          ));
          setMessages((previous) => clearReviewArtifactFromMessages(
            previous,
            completedAction.artifactId,
          ));
          void loadReviewArtifacts();
          scheduleReviewArtifactModalClose();
          onComplete?.();
        }
        setPhase(resolveTerminalStreamPhase<WritingPhase>({
          visibleArtifactStatus: activeReviewArtifactRef.current?.status ?? null,
          completedPhase: "completed",
          awaitingReviewPhase: "recording",
        }));
        if (event.finalContent) {
          addMessage({ role: "system", content: event.finalContent, persist: false });
        }
        addFlowLog({ type: "phase", content: "会话完成" });
        loadSessions();
        break;

      case "error":
        finishActivityRound("error");
        clearAgentLiveRuns();
        if (reviewArtifactActionRef.current?.status === "pending") {
          updateReviewArtifactAction({
            ...reviewArtifactActionRef.current,
            status: "failed",
            message: getReviewArtifactActionMessage(
              reviewArtifactActionRef.current.decision,
              "failed",
              event.message ?? undefined
            ),
          });
        }
        setError(event.message ?? "未知错误");
        setPhase("error");
        addFlowLog({ type: "error", content: `错误: ${event.message ?? "未知错误"}` });
        break;

      default:
        console.debug("[SSE] 未处理的事件类型:", (event as { type: string }).type, event);
        break;
    }
  }, [messages.length, addActivityEntry, addMessage, addFlowLog, applyAgentLiveAction, attachActivityRoundToMessage, clearAgentLiveRuns, discardActivityRound, finishActivityRound, formatOperationLog, getAgentName, handleDetachedArtifactEvent, loadSessions, loadReviewArtifacts, onComplete, refreshAwaitingReviewArtifact, scheduleReviewArtifactModalClose, setActiveReviewArtifact, setCurrentOperation, setCurrentOperationStage, setPhase, setTaskId, setWorkflowReviewArtifact, startActivityRound, updateReviewArtifactAction]);

  const runSendAction = useCallback(<T,>(action: () => Promise<T>) => {
    return sendGuardRef.current.run(action);
  }, []);

  const startDiscussionInternal = async (messageOverride?: string) => {
    const userMessage = (messageOverride ?? userInput).trim();
    if (!userMessage) return;

    const sessionIdForRequest = currentSessionId ?? await createSession();
    if (!sessionIdForRequest) {
      setError("无法创建写作会话");
      return;
    }

    setUserInput("");
    addMessage({ role: "user", content: userMessage, sessionId: sessionIdForRequest, persist: false });
    setIsAssigningTask(true);
    addFlowLog({ type: "user", content: `用户: ${userMessage.slice(0, 50)}${userMessage.length > 50 ? "..." : ""}` });
    setPhase("discussing");
    setIsSending(true);

    try {
      const run = requireApiData(await browserApi.POST("/api/v1/writing/runs", {
        body: {
          clientRequestId: crypto.randomUUID(),
          novelId,
          chapterId,
          targetWordCount,
          selectedAgents,
          userMessage,
          writingSessionId: sessionIdForRequest,
        },
      }));
      setTaskId(run.id);
      const response = await openWritingRunEvents(run.id, eventCursorsRef.current);
      await processStream(run.id, response, { mode: "session", sessionId: sessionIdForRequest });
    } catch (err) {
      setError(err instanceof Error ? err.message : "未知错误");
      setPhase("error");
      setIsAssigningTask(false);
    } finally {
      setIsSending(false);
      clearAgentLiveRuns();
    }
  };

  const handleStartDiscussion = async (messageOverride?: string) => {
    const guarded = runSendAction(() => startDiscussionInternal(messageOverride));
    await guarded;
  };

  const handleSendMessage = async (messageOverride?: string) => {
    const guarded = runSendAction(async () => {
      const message = (messageOverride ?? userInput).trim();
      if (!message) return;

      // 中断当前正在运行的 Agent
      abortCurrentAgent();

      if (!taskId) {
        await startDiscussionInternal(message);
        return;
      }

      if (editingMessageId) {
        const editIndex = messages.findIndex(m => m.id === editingMessageId);
        if (editIndex !== -1) {
          setMessages(prev => prev.slice(0, editIndex + 1));
        }
        setEditingMessageId(null);
      }

      setUserInput("");
      addMessage({ role: "user", content: message, persist: false });
      setIsSending(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const accepted = requireApiData(await browserApi.POST(
          "/api/v1/writing/runs/{task_id}/resume",
          {
            params: { path: { task_id: taskId } },
            body: {
              clientRequestId: crypto.randomUUID(),
              writingSessionId: currentSessionId ?? null,
              userMessage: message,
            },
            signal: controller.signal,
          },
        ));
        const response = await openWritingRunEvents(
          accepted.taskId,
          eventCursorsRef.current,
          controller.signal,
        );
        const sessionIdForRequest = currentSessionIdRef.current;
        if (!sessionIdForRequest) throw new Error("当前写作会话不存在");
        await processStream(
          accepted.taskId,
          response,
          { mode: "session", sessionId: sessionIdForRequest },
        );
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setError(err instanceof Error ? err.message : "发送失败");
      } finally {
        setIsSending(false);
        clearAgentLiveRuns();
      }
    });
    await guarded;
  };

  const openArtifactTray = () => {
    const currentArtifact = activeReviewArtifactRef.current;
    if (currentArtifact?.status === "awaiting_user") {
      openReviewArtifactModal(currentArtifact);
      return;
    }
    void loadReviewArtifacts();
    setShowArtifactTray(true);
  };

  const runPromptAction = async (message: string) => {
    if (taskId && phase !== "idle") {
      await handleSendMessage(message);
    } else {
      await handleStartDiscussion(message);
    }
  };

  const handleProductAction = async (action: WritingProductAction) => {
    if (action.kind === "open_artifacts") {
      openArtifactTray();
      return;
    }
    if (action.prompt) await runPromptAction(action.prompt);
  };

  const processStream = async (
    streamTaskId: string,
    response: Response,
    scope: StreamUiScope,
  ) => {
    const reader = response.body?.getReader();
    if (!reader) throw new Error("写作事件流没有响应体");

    const decoder = new TextDecoder();
    let buffer = "";
    const sseState = eventCursorsRef.current.state(streamTaskId);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true }).replaceAll("\r\n", "\n");
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";

      for (const frame of frames) {
        const parsedFrame = parseSseFrame(`${frame}\n\n`, sseState);
        if (!parsedFrame) continue;
        eventCursorsRef.current.update(streamTaskId, parsedFrame.id);
        const parsed = parsedFrame.data;
        const event = parseSseEvent(parsed, parsedFrame.event);
        if (!event) {
          console.warn("[SSE] 忽略不符合契约的事件:", parsedFrame.event ?? "message");
          continue;
        }
        handleEvent(event, scope);
      }
    }

    if (buffer.trim()) {
      const parsedFrame = parseSseFrame(`${buffer}\n\n`, sseState);
      if (parsedFrame) {
        eventCursorsRef.current.update(streamTaskId, parsedFrame.id);
        const parsed = parsedFrame.data;
        const event = parseSseEvent(parsed, parsedFrame.event);
        if (event) {
          handleEvent(event, scope);
        } else {
          console.warn("[SSE] 忽略不符合契约的事件:", parsedFrame.event ?? "message");
        }
      }
    }

    if (scope.mode === "session" && shouldRefreshAwaitingReviewArtifact({
      eventType: "done",
      hasTaskId: Boolean(taskIdRef.current ?? taskId),
      visibleArtifactStatus: activeReviewArtifactRef.current?.status ?? null,
    })) {
      await refreshAwaitingReviewArtifact("stream_end");
    }
  };

  const handleAcceptContent = () => {
    const artifact = activeReviewArtifactRef.current;
    if (!artifact) return;
    void handleArtifactDecision(
      artifact,
      "approve",
      undefined,
      generatedContent || undefined,
    );
  };

  const handleChapterTargetDecision = async (decision: "current_chapter" | "next_chapter") => {
    const currentTaskId = taskIdRef.current ?? taskId;
    if (!currentTaskId) return;
    setChapterTargetPrompt(null);
    setIsSending(true);
    try {
      const accepted = requireApiData(await browserApi.POST(
        "/api/v1/writing/runs/{task_id}/resume",
        {
          params: { path: { task_id: currentTaskId } },
          body: {
            clientRequestId: crypto.randomUUID(),
            writingSessionId: currentSessionId ?? null,
            userMessage: decision === "current_chapter" ? "使用当前章节" : "新建下一章",
          },
        },
      ));
      const response = await openWritingRunEvents(
        accepted.taskId,
        eventCursorsRef.current,
      );

      const sessionIdForRequest = currentSessionIdRef.current;
      if (!sessionIdForRequest) throw new Error("当前写作会话不存在");
      await processStream(
        accepted.taskId,
        response,
        { mode: "session", sessionId: sessionIdForRequest },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "恢复写作目标确认失败");
      setPhase("error");
    } finally {
      setIsSending(false);
    }
  };

  const startEditMessage = (msg: Message) => {
    setEditingMessageId(msg.id);
    setUserInput(msg.content);
    inputRef.current?.focus();
  };

  const cancelEdit = () => {
    setEditingMessageId(null);
  };

  /** 从消息内容中提取完整版本 */
  const extractFullVersion = (content: string): string | null => {
    // 查找 "完整版本（可直接复制）" 之后的内容
    const marker = "完整版本（可直接复制）";
    const markerIndex = content.indexOf(marker);
    if (markerIndex === -1) return null;

    // 提取代码块内容
    const codeBlockMatch = content.slice(markerIndex).match(/```[\s\S]*?```/);
    if (codeBlockMatch) {
      // 移除代码块标记
      return codeBlockMatch[0].replace(/```\w*\n?/g, "").trim();
    }

    return null;
  };

  /** 复制消息中的完整版本 */
  const copyFullVersion = async (msg: Message) => {
    const fullVersion = msg.fullVersion || extractFullVersion(msg.content);
    if (!fullVersion) return;

    try {
      await navigator.clipboard.writeText(fullVersion);
      setCopiedMessageId(msg.id);
      setTimeout(() => setCopiedMessageId(null), 2000);
    } catch (err) {
      console.error("复制失败", err);
    }
  };

  const hasCopyableContent = (content: string): boolean => {
    return content.includes("完整版本") && content.includes("```");
  };

  const hasWriter = selectedAgents.includes("写作");

  const UpdatesPreviewCard = ({ updates, compact = false }: { updates: PendingUpdatesData; compact?: boolean }) => {
    const actionLabels: Record<string, string> = {
      create: "新增",
      update: "修改",
      delete: "删除",
      payoff: "回收",
      abandon: "废弃",
    };

    const getName = (item: Record<string, unknown>): string => getUpdateItemName(item);

    const isEmptyValue = (value: string | undefined) => value === undefined || value.trim() === "";

    const renderValue = (value: string | undefined, emptyText: string) => (
      <div className={isEmptyValue(value) ? "diff-value diff-empty" : "diff-value"}>
        {isEmptyValue(value) ? emptyText : value}
      </div>
    );

    const renderDiffItem = (item: UpdateDiffItem, idx: number) => (
      <details
        key={`${item.section}-${item.name}-${idx}`}
        className="updates-diff-item"
        open={!compact && idx < 3}
      >
        <summary>
          <span className="diff-summary-main">
            <span className={`action-badge ${item.action}`}>
              {actionLabels[item.action] ?? item.action}
            </span>
            <span className="diff-section">{item.section}</span>
            <span className="item-name">{item.name}</span>
          </span>
          <span className="diff-summary-meta">
            <span className="diff-count">{item.fields.length} 项</span>
            <span className="diff-toggle-text" aria-hidden="true" />
          </span>
        </summary>
        {item.fields.length > 0 ? (
          <div className="diff-fields">
            {item.fields.map((field) => (
              <div key={`${field.field}-${field.label}`} className="diff-field">
                <div className="diff-field-label">{field.label}</div>
                <div className="diff-columns">
                  <div className="diff-column diff-old">
                    <div className="diff-column-title">当前</div>
                    {renderValue(field.oldValue, "空")}
                  </div>
                  <div className="diff-column diff-new">
                    <div className="diff-column-title">待保存</div>
                    {renderValue(field.newValue, item.action === "delete" ? "将删除" : "空")}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="diff-empty-note">没有字段级差异，可能是目标不存在、删除操作或 Agent 未提供可比对字段。</div>
        )}
      </details>
    );

    const renderDiffs = () => {
      if (!updates.__diff?.length) return null;
      return (
        <div className="updates-diff-list">
          {updates.__diff.map(renderDiffItem)}
        </div>
      );
    };

    const renderOutlineNode = (node: OutlinePreviewNode, depth = 0): React.ReactNode => {
      const status = getOutlineStatusLabel(node.status);
      return (
        <div className="outline-review-node" key={node.key}>
          <div className="outline-review-node-row" style={{ paddingLeft: 10 + depth * 18 }}>
            <span className={`outline-review-kind outline-review-kind-${node.kind}`}>
              {getOutlineKindLabel(node.kind)}
            </span>
            <span className="outline-review-title">{node.title}</span>
            <span className={`action-badge ${node.action}`}>{actionLabels[node.action] ?? node.action}</span>
            {status ? <span className="muted">{status}</span> : null}
            {node.estimatedWordCount ? <span className="muted">{node.estimatedWordCount}字</span> : null}
          </div>
          {node.content ? (
            <div className="outline-review-summary" style={{ marginLeft: 10 + depth * 18 }}>
              {node.content}
            </div>
          ) : null}
          {node.children.map((child) => renderOutlineNode(child, depth + 1))}
        </div>
      );
    };

    const renderOutlinePreview = (previewUpdates: PendingUpdatesData) => {
      const outlineUpdates = getOutlinePreviewUpdates(previewUpdates);
      if (!outlineUpdates) return null;
      const nodes = buildOutlinePreviewNodes(outlineUpdates.outlineAdjustments);
      return (
        <div className="outline-review-preview">
          <div className="outline-review-header">
            <span>结构化大纲</span>
            <span className="muted">
              {outlineUpdates.outlineAdjustments?.length ? `${outlineUpdates.outlineAdjustments.length} 个节点变更` : "总纲更新"}
            </span>
          </div>
          {outlineUpdates.outlineContent ? (
            <div className="outline-review-total">
              <span>总纲</span>
              <p>{outlineUpdates.outlineContent}</p>
            </div>
          ) : null}
          {nodes.length > 0 ? (
            <div className="outline-review-tree">
              {nodes.map((node) => renderOutlineNode(node))}
            </div>
          ) : null}
        </div>
      );
    };

    const renderSection = (title: string, items: Record<string, unknown>[] | undefined) => {
      if (!items || items.length === 0) return null;
      return (
        <div className="updates-section">
          <div className="updates-title">{title}</div>
          {items.map((item, idx) => (
            <div key={idx} className="updates-item">
              <span className={`action-badge ${String(item.action)}`}>
                {actionLabels[String(item.action)] ?? String(item.action)}
              </span>
              <span className="item-name">{getName(item)}</span>
            </div>
          ))}
        </div>
      );
    };

    const renderUpdatesBody = () => (
      <div className="updates-body">
        {renderOutlinePreview(updates)}
        {renderDiffs() ?? (
          <>
            {renderSection("角色", updates.characters)}
            {renderSection("角色经历", updates.characterExperiences)}
            {renderSection("地点", updates.locations)}
            {renderSection("物品", updates.items)}
            {renderSection("势力", updates.factions)}
            {renderSection("术语", updates.glossaries)}
            {renderSection("伏笔", updates.foreshadowing)}
            {renderSection("大纲状态", updates.outline)}
            {renderSection("大纲节点", updates.outlineAdjustments)}
          </>
        )}
      </div>
    );

    if (compact) {
      return (
        <div className="review-updates-preview compact">
          <div className="updates-title">变更预览</div>
          {renderUpdatesBody()}
        </div>
      );
    }

    return (
      <div className="updates-card">
        <div className="updates-header">
          <span>待确认变更</span>
        </div>
        {renderUpdatesBody()}
      </div>
    );
  };

  const renderStructuredUpdateSelection = (artifact: ReviewArtifactData, disabled = false) => {
    const updates = artifact.payload?.updates;
    const allRefs = getStructuredUpdateRefs(updates);
    if (!updates || allRefs.length === 0) return null;

    const selectedCount = allRefs.filter((ref) => selectedUpdateRefKeys.has(getUpdateSelectionKey(ref))).length;
    const renderSection = (section: AgentUpdateSelectionRef["section"], label: string) => {
      const value = updates[section as keyof PendingUpdatesData];
      if (Array.isArray(value)) {
        if (value.length === 0) return null;
        return (
          <div className="review-update-select-section" key={section}>
            <div className="review-update-select-section-title">{label}</div>
            {value.map((item, index) => {
              const ref = { section, index };
              const key = getUpdateSelectionKey(ref);
              const record = item as Record<string, unknown>;
              return (
                <label className="review-update-select-item" key={key}>
                  <input
                    type="checkbox"
                    checked={selectedUpdateRefKeys.has(key)}
                    disabled={disabled}
                    onChange={() => toggleUpdateSelection(ref)}
                  />
                  <span className={`action-badge ${String(record.action ?? "update")}`}>
                    {getUpdateActionLabel(String(record.action ?? "update"))}
                  </span>
                  <span className="item-name">{getUpdateItemName(record) || `第 ${index + 1} 条`}</span>
                </label>
              );
            })}
          </div>
        );
      }

      if (typeof value !== "string" || !value.trim()) return null;
      const ref = { section };
      const key = getUpdateSelectionKey(ref);
      return (
        <div className="review-update-select-section" key={section}>
          <div className="review-update-select-section-title">{label}</div>
          <label className="review-update-select-item">
            <input
              type="checkbox"
              checked={selectedUpdateRefKeys.has(key)}
              disabled={disabled}
              onChange={() => toggleUpdateSelection(ref)}
            />
            <span className="action-badge update">修改</span>
            <span className="item-name">{label}</span>
          </label>
        </div>
      );
    };

    return (
      <div className="review-update-selection">
        <div className="review-update-selection-header">
          <div>
            <div className="review-dialog-section-title">选择要应用的变更</div>
            <div className="review-update-selection-count">
              已选择 {selectedCount} / {allRefs.length} 条
            </div>
          </div>
          <div className="review-update-selection-actions">
            <button className="button ghost sm" type="button" disabled={disabled} onClick={() => selectAllStructuredUpdates(artifact)}>
              全选
            </button>
            <button className="button ghost sm" type="button" disabled={disabled} onClick={clearStructuredUpdateSelection}>
              全不选
            </button>
          </div>
        </div>
        <div className="review-update-select-list">
          {SELECTABLE_TEXT_UPDATE_SECTIONS.map(({ section, label }) => renderSection(section, label))}
          {SELECTABLE_ARRAY_UPDATE_SECTIONS.map(({ section, label }) => renderSection(section, label))}
        </div>
      </div>
    );
  };

  /* eslint-disable react-hooks/refs -- 审核卡片事件处理器只在点击时读取运行句柄。 */
  const renderArtifactReviewCard = (artifact: ReviewArtifactData) => {
    const diffItems = artifact.diff ?? artifact.payload?.updates?.__diff ?? [];
    const hasStructuredUpdates = Boolean(artifact.payload?.updates && (
      artifact.payload.updates.outlineContent ||
      artifact.payload.updates.outline?.length ||
      artifact.payload.updates.outlineAdjustments?.length
    ));
    const latestEvaluation = artifact.evaluations?.[0];
    const awaitingUser = artifact.status === "awaiting_user";
    const underReview = artifact.status === "under_review";
    const isActing = Boolean(artifact.optimisticStatus) || artifact.status === "applying" || artifact.status === "discarding";
    const artifactContent = getReviewArtifactContent(artifact);
    const localDraftForApply = getLocalReviewDraftForApply(artifact);
    const selectedUpdateRefsForApply = getSelectedUpdateRefsForApply(artifact);
    const action = getReviewArtifactAction(artifact.id);
    const actionLocked = isReviewArtifactActionLocked(action);
    const isApplyDisabled = isSending ||
      isActing ||
      actionLocked ||
      (localDraftForApply !== undefined && !localDraftForApply.trim()) ||
      (selectedUpdateRefsForApply !== undefined && selectedUpdateRefsForApply.length === 0);

    return (
      <div className="review-artifact-card">
        <div className="review-artifact-card-header">
          <div>
            <div className="review-artifact-title">待确认变更</div>
            {artifact.summary ? <div className="review-artifact-summary">{artifact.summary}</div> : null}
            <div className="review-artifact-impact">{getReviewArtifactKindLabel(artifact.kind)} · {getReviewArtifactImpactLabel(artifact.kind)}</div>
          </div>
          <span className={`action-badge ${artifact.optimisticStatus ?? artifact.status}`}>
            {getReviewArtifactStatusLabel(artifact.status, artifact.optimisticStatus)} · v{artifact.revision}
          </span>
        </div>
        <div className="review-artifact-card-body">
          {latestEvaluation ? (
            <div className="review-evaluation-row">
              <span className={`action-badge ${latestEvaluation.verdict}`}>
                {getReviewVerdictLabel(latestEvaluation.verdict)}
              </span>
              <span className="review-evaluator">{latestEvaluation.evaluatorAgent}</span>
              <span className="review-evaluation-summary">{latestEvaluation.summary}</span>
            </div>
          ) : null}
          {underReview ? (
            <div className="review-evaluation-row">
              <span className="action-badge running">复审中</span>
              <span className="review-evaluation-summary">变更正在复审，复审通过后再由你确认是否应用。</span>
            </div>
          ) : null}
          {artifactContent ? (
            <div className="review-artifact-preview">
              <div className="review-artifact-preview-title">变更预览</div>
              <div className="review-artifact-preview-text">
                <ParagraphText text={normalizeParagraphTextDisplay(artifactContent)} />
              </div>
            </div>
          ) : null}
          {diffItems.length > 0 || hasStructuredUpdates ? (
            <UpdatesPreviewCard updates={{ ...(artifact.payload?.updates ?? {}), __diff: diffItems.slice(0, 6) }} compact />
          ) : null}
          {action ? (
            <div className={`review-action-status ${action.status}`} role={action.status === "failed" ? "alert" : "status"}>
              {action.status === "pending" ? <span className="review-action-spinner" aria-hidden="true" /> : null}
              <span>{action.message}</span>
            </div>
          ) : null}
          <div className="review-artifact-actions">
            {awaitingUser ? (
              <>
              <button
                className="button ghost sm"
                type="button"
                disabled={isSending || isActing || actionLocked}
                onClick={() => openReviewArtifactModal(artifact)}
              >
                查看全文/编辑
              </button>
              <button
                className="button sm"
                type="button"
                disabled={isApplyDisabled}
                onClick={() => handleArtifactDecision(
                  artifact,
                  "approve",
                  undefined,
                  localDraftForApply,
                  selectedUpdateRefsForApply
                )}
              >
                {getReviewArtifactActionButtonLabel(action, "approve") ?? (artifact.optimisticStatus === "applying" ? "应用中..." : "应用到项目")}
              </button>
              <button
                className="button ghost sm"
                type="button"
                disabled={isSending || isActing || actionLocked}
                onClick={focusChatForArtifactRevision}
              >
                {getReviewArtifactActionButtonLabel(action, "revise") ?? (artifact.optimisticStatus === "revising" ? "准备返工..." : "继续修改")}
              </button>
              <button
                className="button ghost sm"
                type="button"
                disabled={isSending || isActing || actionLocked}
                onClick={() => handleArtifactDecision(artifact, "discard")}
              >
                {getReviewArtifactActionButtonLabel(action, "discard") ?? (artifact.optimisticStatus === "discarding" ? "丢弃中..." : "丢弃变更")}
              </button>
              </>
            ) : (
              <button
                className="button ghost sm"
                type="button"
                onClick={() => openReviewArtifactModal(artifact)}
              >
                查看变更
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };
  /* eslint-enable react-hooks/refs */

  const renderArtifactReviewDialog = (artifact: ReviewArtifactData) => {
    const latestEvaluation = artifact.evaluations?.[0];
    const diffItems = artifact.diff ?? artifact.payload?.updates?.__diff ?? [];
    const hasStructuredUpdates = Boolean(artifact.payload?.updates && (
      artifact.payload.updates.outlineContent ||
      artifact.payload.updates.outline?.length ||
      artifact.payload.updates.outlineAdjustments?.length
    ));
    const isActing = Boolean(artifact.optimisticStatus) || artifact.status === "applying" || artifact.status === "discarding";
    const canEditText = Boolean(getReviewArtifactContent(artifact));
    const awaitingUser = artifact.status === "awaiting_user";
    const selectedUpdateRefsForApply = getSelectedUpdateRefsForApply(artifact);
    const hasEmptyStructuredSelection = selectedUpdateRefsForApply !== undefined && selectedUpdateRefsForApply.length === 0;
    const action = getReviewArtifactAction(artifact.id);
    const actionLocked = isReviewArtifactActionLocked(action);
    const isCurrentSessionArtifact =
      activeReviewArtifact?.id === artifact.id &&
      Boolean(taskId) &&
      taskId === artifact.taskId;

    return (
      <div className={`review-dialog ${actionLocked ? "is-busy" : ""}`} aria-busy={actionLocked}>
        <div className="review-dialog-meta">
          <div>
            <div className="review-dialog-title">待确认变更</div>
            {artifact.summary ? <div className="review-dialog-summary">{artifact.summary}</div> : null}
          </div>
          <span className={`action-badge ${artifact.optimisticStatus ?? artifact.status}`}>
            {getReviewArtifactStatusLabel(artifact.status, artifact.optimisticStatus)} · v{artifact.revision}
          </span>
        </div>

        <div className="review-dialog-scroll">
          {latestEvaluation ? (
            <section className="review-dialog-section">
              <div className="review-dialog-section-title">复审意见</div>
              <div className="review-dialog-evaluation">
                <span className={`action-badge ${latestEvaluation.verdict}`}>
                  {getReviewVerdictLabel(latestEvaluation.verdict)}
                </span>
                <span className="review-evaluator">{latestEvaluation.evaluatorAgent}</span>
                <span>{latestEvaluation.summary}</span>
              </div>
            </section>
          ) : null}

          <section className="review-dialog-section">
            <div className="review-dialog-section-title">{canEditText ? "可编辑正文" : "结构化变更"}</div>
            {canEditText ? (
              <label className="review-editor">
                <textarea
                  value={reviewDraftText}
                  onChange={(event) => setReviewDraftText(event.target.value)}
                  readOnly={!awaitingUser || actionLocked}
                  spellCheck={false}
                />
              </label>
            ) : (
              awaitingUser ? (
                <>
                  {renderStructuredUpdateSelection(artifact, actionLocked)}
                  <div className="review-dialog-note">取消勾选的变更不会在本次应用中落库；需要改写具体内容时，再点“继续修改”回到聊天中返工。</div>
                </>
              ) : (
                <div className="review-dialog-note">这个变更还没有进入等待确认状态，只能查看，不能直接应用。</div>
              )
            )}
          </section>

          {diffItems.length > 0 || hasStructuredUpdates ? (
            <section className="review-dialog-section review-dialog-diffs">
              <UpdatesPreviewCard updates={{ ...(artifact.payload?.updates ?? {}), __diff: diffItems }} compact />
            </section>
          ) : null}
        </div>

        {action ? (
          <div className={`review-action-status ${action.status}`} role={action.status === "failed" ? "alert" : "status"}>
            {action.status === "pending" ? <span className="review-action-spinner" aria-hidden="true" /> : null}
            <span>{action.message}</span>
          </div>
        ) : null}

        <div className="review-dialog-actions">
          {awaitingUser ? (
            <>
              <button
                className="button"
                type="button"
                disabled={isSending || isActing || actionLocked || (canEditText && !reviewDraftText.trim()) || hasEmptyStructuredSelection}
                onClick={() => handleArtifactDecision(
                  artifact,
                  "approve",
                  undefined,
                  canEditText ? reviewDraftText : undefined,
                  canEditText ? undefined : selectedUpdateRefsForApply
                )}
              >
                {getReviewArtifactActionButtonLabel(action, "approve") ?? (artifact.optimisticStatus === "applying" ? "应用中..." : "应用到项目")}
              </button>
              <button
                className="button ghost"
                type="button"
                disabled={isSending || isActing || actionLocked}
                onClick={() => {
                  if (isCurrentSessionArtifact) {
                    focusChatForArtifactRevision();
                    return;
                  }
                  void handleArtifactDecision(artifact, "revise", "继续修改待确认变更");
                }}
              >
                {getReviewArtifactActionButtonLabel(action, "revise") ?? (artifact.optimisticStatus === "revising" ? "准备返工..." : "继续修改")}
              </button>
              <button
                className="button ghost"
                type="button"
                disabled={isSending || isActing || actionLocked}
                onClick={() => handleArtifactDecision(artifact, "discard")}
              >
                {getReviewArtifactActionButtonLabel(action, "discard") ?? (artifact.optimisticStatus === "discarding" ? "丢弃中..." : "丢弃变更")}
              </button>
            </>
          ) : (
            <button className="button ghost" type="button" disabled={actionLocked} onClick={() => closeReviewArtifactModal()}>
              关闭
            </button>
          )}
        </div>
      </div>
    );
  };

  async function handleArtifactDecision(
    artifact: ReviewArtifactData,
    decision: ReviewArtifactDecision,
    userMessage?: string,
    editedContent?: string,
    selectedUpdateRefs?: AgentUpdateSelectionRef[]
  ) {
    const guarded = runSendAction(async () => {
      const currentUiTaskId = taskIdRef.current ?? taskId;
      const isVisibleSessionArtifact = activeReviewArtifactRef.current?.id === artifact.id;
      const currentTaskId = resolveReviewArtifactActionTaskId(
        isVisibleSessionArtifact ? currentUiTaskId : null,
        artifact
      );
      if (!currentTaskId) {
        updateReviewArtifactAction({
          artifactId: artifact.id,
          decision,
          status: "failed",
          message: "找不到当前写作任务，无法处理待确认变更。请刷新页面后重试。",
        });
        setError("找不到当前写作任务，无法处理待确认变更。请刷新页面后重试。");
        setPhase("error");
        return;
      }
      const interactionScope = resolveArtifactInteractionScope({
        activeArtifactId: isVisibleSessionArtifact ? artifact.id : null,
        currentTaskId: currentUiTaskId,
        artifactId: artifact.id,
        artifactTaskId: artifact.taskId,
      });
      const isCurrentSessionArtifact = interactionScope === "session";

      clearReviewActionCloseTimer();
      updateReviewArtifactAction({
        artifactId: artifact.id,
        decision,
        status: "pending",
        message: getReviewArtifactActionMessage(decision, "pending"),
      });
      setIsSending(true);
      startTransition(() => {
        addOptimisticReviewArtifactDecision({ artifactId: artifact.id, decision });
      });
      try {
        const accepted = requireApiData(await browserApi.POST(
          "/api/v1/review-artifacts/{artifact_id}/decision",
          {
            params: { path: { artifact_id: artifact.id } },
            body: {
              clientRequestId: crypto.randomUUID(),
              decision,
              editedContent: decision === "approve" ? editedContent ?? null : null,
              selectedUpdateRefs: decision === "approve" ? selectedUpdateRefs ?? null : null,
              userMessage: userMessage ?? (decision === "revise" ? "继续修改待确认变更" : null),
            },
          },
        ));
        const response = await openWritingRunEvents(
          accepted.taskId,
          eventCursorsRef.current,
        );
        const streamScope: StreamUiScope = isCurrentSessionArtifact && currentSessionIdRef.current
          ? { mode: "session", sessionId: currentSessionIdRef.current }
          : { mode: "artifact", artifactId: artifact.id };
        await processStream(accepted.taskId, response, streamScope);
      } catch (err) {
        const message = err instanceof Error ? err.message : "处理待确认变更失败";
        updateReviewArtifactAction({
          artifactId: artifact.id,
          decision,
          status: "failed",
          message: getReviewArtifactActionMessage(decision, "failed", message),
        });
        setError(message);
        setPhase("error");
      } finally {
        setIsSending(false);
        clearAgentLiveRuns();
      }
    });
    await guarded;
  }

  const getActivityRoundTitle = (round: ToolActivityRound) => {
    const completionStatus = round.completionStatus === "error" ? "error" : "done";
    return getToolActivitySummary(completionStatus, countVisibleToolCalls(round.entries));
  };

  const getActivityGroups = (round: ToolActivityRound) => {
    const groups = [
      { key: "thinking", label: "状态", entries: round.entries.filter((entry) => entry.status !== "querying" && entry.status !== "responding" && entry.status !== "parsing") },
      { key: "querying", label: "查询", entries: round.entries.filter((entry) => entry.status === "querying") },
      { key: "responding", label: "生成", entries: round.entries.filter((entry) => entry.status === "responding") },
      { key: "parsing", label: "整理", entries: round.entries.filter((entry) => entry.status === "parsing") },
    ];
    return groups.filter((group) => group.entries.length > 0);
  };

  const renderActivityRound = (round: ToolActivityRound) => {
    return (
      <div key={round.id} className={`activity-round ${round.running ? "is-running" : "is-finished"}`}>
        <button
          type="button"
          className="activity-round-toggle"
          onClick={() => toggleActivityRound(round.id)}
          aria-expanded={round.expanded}
        >
          <span className="activity-caret" aria-hidden="true">{round.expanded ? "⌄" : "›"}</span>
          <span className="activity-summary">{getActivityRoundTitle(round)}</span>
        </button>
        {round.expanded ? (
          <div className="activity-groups">
            {getActivityGroups(round).map((group) => (
              <div key={group.key} className={`activity-group activity-group-${group.key}`}>
                <div className="activity-group-label">{group.label}</div>
                <div className="activity-group-items">
                  {group.entries.map((entry) => (
                    <div key={entry.id} className={`activity-item ${entry.resultSummary ? "has-result" : ""}`}>
                      <span className="activity-dot" aria-hidden="true" />
                      <span className="activity-item-main">
                        {entry.resultSummary || entry.toolLabel || entry.message}
                        {entry.argsSummary ? <span className="activity-args">参数：{entry.argsSummary}</span> : null}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  const liveAgentRuns = listAgentLiveRuns(agentLiveRuns);

  const currentSession = sessions.find(s => s.id === currentSessionId);
  const workflowReviewArtifact = resolveVisibleReviewArtifact(optimisticReviewArtifact, messages);
  const resolveMessageReviewArtifact = (artifact: ReviewArtifactData) => {
    if (!workflowReviewArtifact) return artifact;
    if (workflowReviewArtifact.id === artifact.id) return workflowReviewArtifact;
    if (workflowReviewArtifact.artifactKey && workflowReviewArtifact.artifactKey === artifact.artifactKey) return workflowReviewArtifact;
    return artifact;
  };
  const modalReviewArtifact =
    reviewDialogArtifact?.id === workflowReviewArtifact?.id
      ? workflowReviewArtifact
      : reviewDialogArtifact ?? workflowReviewArtifact;
  const modalReviewArtifactAction = modalReviewArtifact ? getReviewArtifactAction(modalReviewArtifact.id) : null;
  const isReviewArtifactModalLocked = isReviewArtifactActionLocked(modalReviewArtifactAction);
  const awaitingArtifactCount = reviewArtifacts.filter((artifact) => artifact.status === "awaiting_user").length;
  const workflowAwaitingArtifactExtra = workflowReviewArtifact?.status === "awaiting_user" &&
    !reviewArtifacts.some((artifact) => artifact.id === workflowReviewArtifact.id)
    ? 1
    : 0;
  const effectiveAwaitingArtifactCount = awaitingArtifactCount + workflowAwaitingArtifactExtra;
  const nextActions = getWritingNextActions({
    chapterStatus: chapterContext?.status,
    wordCount: chapterContext?.wordCount ?? 0,
    awaitingArtifactCount: effectiveAwaitingArtifactCount,
    hasApprovedBeatPlan: Boolean(chapterContext?.approvedBeatPlan),
    hasOpenConsistencyCheck: Boolean(chapterContext?.openConsistencyCheckCount),
  });
  const availableAgents = AGENT_REGISTRY.filter(a => !selectedAgents.includes(a.id as AgentId));
  const filteredAgents = agentPickerQuery
    ? availableAgents.filter(a =>
        a.name.toLowerCase().includes(agentPickerQuery.toLowerCase()) ||
        a.id.toLowerCase().includes(agentPickerQuery.toLowerCase())
      )
    : availableAgents;
  const visibleAgentOptions = filteredAgents.slice(0, 5);

  return (
    <div className="writing-chat">
      {/* 顶部栏 */}
      <div className="chat-header">
        <div className="header-left">
          <button className="session-trigger" onClick={() => setShowSessionModal(true)}>
            💬 会话列表
            {currentSession && <span className="current-session-name">：{currentSession.title || "未命名"}</span>}
          </button>
          <button
            className="session-trigger artifact-trigger"
            onClick={openArtifactTray}
          >
            待确认 {effectiveAwaitingArtifactCount}
            {effectiveAwaitingArtifactCount > 0 ? <span className="artifact-count-hot">{effectiveAwaitingArtifactCount}</span> : null}
          </button>
        </div>
        <div className="header-right">
          <span className="phase-indicator">
            {phase === "idle" ? "空闲" :
             phase === "discussing" ? "讨论中" :
             phase === "generating" ? "生成中" :
             phase === "recording" ? "记录中" :
             phase === "completed" ? "已完成" : phase}
          </span>
          <button className="tool-btn" onClick={() => setShowFlowLog(!showFlowLog)} title="流程日志">
            📋
          </button>
        </div>
      </div>

      {chapterContext ? (
        <div className="next-action-panel">
          <div className="next-action-kicker">下一步</div>
          <div className="next-action-buttons">
            {nextActions.map((action) => (
              <button
                className={action.kind === "open_artifacts" ? "next-action-button urgent" : "next-action-button"}
                key={action.kind}
                type="button"
                onClick={() => void handleProductAction(action)}
                disabled={isSending}
              >
                <span>{action.label}</span>
                <small>{action.description}</small>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* 消息区域 */}
      <div className="chat-messages" ref={chatRef}>
        {messages.length === 0 && phase === "idle" && liveAgentRuns.length === 0 && (
          <div className="welcome-state">
            <div className="welcome-icon">✦</div>
            <div className="welcome-text">选择一个任务开始</div>
            <div className="agent-quick-btns">
              <div className="agent-quick-section">
                <div className="agent-quick-label">常用写作动作</div>
                <div className="agent-quick-row">
                  {WRITING_SHORTCUT_ACTIONS.map((action) => (
                    <button
                      className="agent-quick-btn"
                      key={action.kind}
                      onClick={() => void handleProductAction(action)}
                      disabled={isSending}
                    >
                      <span className="agent-name">{action.label}</span>
                      <small>{action.description}</small>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {messages.map((msg, index) => {
          const isUser = msg.role === "user";
          const info = msg.agentId ? getAgentInfo(msg.agentId) : null;
          const isEditing = editingMessageId === msg.id;
          const anchoredRounds = activityRounds.filter((round) => round.anchorMessageId === msg.id);

          return (
            <div key={msg.id} className="message-group">
              <div className={`message ${isUser ? "message-user" : "message-agent"}`}>
                {!isUser && (
                  <div className={`message-avatar tone-${info?.tone ?? "gray"}`}>
                    {info?.emoji}
                  </div>
                )}
                <div className="message-body">
                  <div className="message-header">
                    {msg.agentName || (msg.role === "system" ? "系统" : msg.role === "user" ? "我" : "助手")}
                  </div>
                  <div className="message-content">
                    <ParagraphText text={renderParagraphMessageContent(msg)} />
                    {anchoredRounds.map(renderActivityRound)}
                  </div>
                  {msg.intent && (
                    <div className="message-intent">{msg.intent}</div>
                  )}
                  <div className="message-actions">
                    {!isUser && msg.agentId && (
                      <button className="action-btn" title="重试" onClick={() => {
                        const prevUserMsg = messages.slice(0, index).reverse().find(m => m.role === "user");
                        if (prevUserMsg) handleSendMessage(prevUserMsg.content);
                      }}>↩</button>
                    )}
                    <button className="action-btn" title="删除（从上下文移除）" onClick={() => {
                      setMessages(prev => prev.filter(m => m.id !== msg.id));
                    }}>✕</button>
                    {hasCopyableContent(msg.content) && (
                      <button className={`copy-btn ${copiedMessageId === msg.id ? "copied" : ""}`} onClick={() => copyFullVersion(msg)}>
                        {copiedMessageId === msg.id ? "已复制 ✓" : "复制"}
                      </button>
                    )}
                    {isUser && !isSending && (
                      <button className="edit-btn" onClick={() => startEditMessage(msg)}>✏️</button>
                    )}
                  </div>
                  {isEditing && (
                    <div className="edit-hint">
                      编辑中... 按发送重新提交
                      <button onClick={cancelEdit}>取消</button>
                    </div>
                  )}
                  {msg.reviewArtifact ? (
                    renderArtifactReviewCard(resolveMessageReviewArtifact(msg.reviewArtifact))
                  ) : null}
                </div>
                {isUser && <div className="message-avatar user-avatar">我</div>}
              </div>
            </div>
          );
        })}

        {isAssigningTask ? (
          <div className="assignment-status" aria-live="polite">正在分配任务</div>
        ) : null}

        {liveAgentRuns.map((run) => (
          <div className="message message-agent" key={run.agentId}>
            <div className={`message-avatar tone-${getAgentInfo(run.agentId).tone}`}>
              {getAgentInfo(run.agentId).emoji}
            </div>
            <div className="message-body">
              <div className="message-header">{getAgentName(run.agentId)}</div>
              <div className="message-content streaming">
                <div className="agent-live-status" aria-live="polite">
                  <span className="agent-live-status-dot" aria-hidden="true" />
                  <span>{run.statusMessage}</span>
                </div>
                {run.content ? <ParagraphText text={run.content} /> : null}
                {run.content ? <span className="cursor">●</span> : null}
              </div>
            </div>
          </div>
        ))}

        {currentOperation && phase !== "idle" && phase !== "completed" && (
          <div className="operation-status-card">
            <div className="operation-status-main">
              <span className="operation-status-label">{getCreativeOperationLabel(currentOperation.kind)}</span>
              {currentOperationStage ? <span className="operation-status-stage">{currentOperationStage}</span> : null}
              <span className="operation-status-agent">{getAgentName(currentOperation.primaryAgent)}</span>
              <span className="operation-status-output">{getCreativeOperationOutputLabel(currentOperation.outputKind)}</span>
            </div>
            <div className="operation-status-goal">{currentOperation.userGoal}</div>
            {(currentOperation.requiresArtifact || currentOperation.requiresUserApproval) && (
              <div className="operation-status-flags">
                {currentOperation.requiresArtifact ? <span>待确认变更</span> : null}
                {currentOperation.requiresUserApproval ? <span>用户确认</span> : null}
              </div>
            )}
          </div>
        )}

        {generatedContent && (
          <div className="preview-section">
            <div className="preview-header">
              <span>📝 正文预览</span>
              <span className="word-count">{countTextLength(generatedContent)} 字</span>
            </div>
            <div className="preview-content"><ParagraphText text={generatedContent} /></div>
            <div className="preview-actions">
              <button className="btn-primary" onClick={handleAcceptContent} disabled={isPending}>采纳</button>
              <button className="btn-secondary" onClick={() => setGeneratedContent("")}>继续修改</button>
            </div>
          </div>
        )}

        {chapterTargetPrompt ? (
          <div className="operation-status-card">
            <div className="operation-status-main">
              <span className="operation-status-label">{chapterTargetPrompt.summary ?? "确认写作目标"}</span>
            </div>
            {chapterTargetPrompt.content ? (
              <div className="operation-status-goal">{chapterTargetPrompt.content}</div>
            ) : null}
            <div className="operation-status-flags">
              <button className="button" type="button" disabled={isSending} onClick={() => handleChapterTargetDecision("next_chapter")}>
                写下一章
              </button>
              <button className="button ghost" type="button" disabled={isSending} onClick={() => handleChapterTargetDecision("current_chapter")}>
                继续当前章
              </button>
            </div>
          </div>
        ) : null}

        {messages.length === 0 && workflowReviewArtifact ? (
          renderArtifactReviewCard(workflowReviewArtifact)
        ) : (() => {
          const pendingUpdates = messages[messages.length - 1]?.pendingUpdates;
          return pendingUpdates ? <UpdatesPreviewCard updates={pendingUpdates} /> : null;
        })()}

        {error && (
          <div className="error-toast">
            <span>❌ {error}</span>
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        {showFlowLog && flowLogs.length > 0 && (
          <div className="flow-log">
            <div className="flow-log-title">
              <span>流程日志</span>
              <button onClick={() => setFlowLogs([])}>清空</button>
            </div>
            {flowLogs.map(log => (
              <div key={log.id} className={`flow-log-item flow-${log.type}`}>
                <span className="flow-icon">
                  {log.type === "phase" && "📍"}
                  {log.type === "agent_start" && "▶"}
                  {log.type === "agent_done" && "✓"}
                  {log.type === "agent_status" && "💭"}
                  {log.type === "operation" && "◇"}
                  {log.type === "intent" && "💬"}
                  {log.type === "user" && "👤"}
                  {log.type === "error" && "❌"}
                </span>
                <span className="flow-text">{log.content}</span>
                {log.duration && <span className="flow-duration">{log.duration}ms</span>}
              </div>
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 输入区域 */}
      <div className="chat-input">
        {generatedContent && (
          <div className="quick-actions">
            <button onClick={() => handleSendMessage("采纳")}>采纳</button>
            <button onClick={() => handleSendMessage("继续修改")}>修改</button>
          </div>
        )}
        {phase !== "idle" && phase !== "completed" && (
          <div className="quick-actions">
            {phase === "recording" && workflowReviewArtifact?.status === "awaiting_user" ? (
              <QuickReviewActions
                artifact={workflowReviewArtifact}
                action={getReviewArtifactAction(workflowReviewArtifact.id)}
                editedContent={getLocalReviewDraftForApply(workflowReviewArtifact)}
                isSending={isSending}
                onDecision={handleArtifactDecision}
                onRevise={focusChatForArtifactRevision}
              />
            ) : phase === "reviewing" ? (
              <>
                <button onClick={() => handleSendMessage("确认保存")}>确认保存</button>
                <button onClick={() => handleSendMessage("取消")}>取消</button>
              </>
            ) : (
              <>
                {hasWriter && <button onClick={() => handleSendMessage("开始生成正文")}>开始写作</button>}
                <button onClick={() => handleSendMessage("保存讨论结果")}>保存设定</button>
              </>
            )}
          </div>
        )}

        <div className="input-row">
          <textarea
            ref={inputRef}
            value={userInput}
            onChange={(e) => handleInputChange(e.target.value, e.target.selectionStart)}
            onSelect={(e) => setCursorPosition(e.currentTarget.selectionStart)}
            placeholder="输入消息...（@ 邀请助手）"
            rows={1}
            onKeyDown={(e) => {
              if (showAgentPicker && visibleAgentOptions.length > 0 && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
                e.preventDefault();
                setAgentPickerActiveIndex((current) => {
                  const delta = e.key === "ArrowDown" ? 1 : -1;
                  return (current + delta + visibleAgentOptions.length) % visibleAgentOptions.length;
                });
              } else if (showAgentPicker && visibleAgentOptions.length > 0 && e.key === "Enter") {
                e.preventDefault();
                insertAgentMention(visibleAgentOptions[agentPickerActiveIndex]?.id ?? visibleAgentOptions[0].id);
              } else if (e.key === "Enter" && !e.shiftKey && !showAgentPicker) {
                e.preventDefault();
                handleSendMessage();
              } else if (e.key === "Escape") {
                setShowAgentPicker(false);
                setAgentPickerActiveIndex(0);
                if (editingMessageId) cancelEdit();
              }
            }}
            disabled={isSending}
          />
          <button className="send-btn" onClick={() => handleSendMessage()} disabled={!userInput.trim() || isSending}>
            发送
          </button>
        </div>

        {showAgentPicker && visibleAgentOptions.length > 0 && (
          <div className="agent-picker" role="listbox" aria-label="选择 Agent">
            {visibleAgentOptions.map((agent, index) => {
              const info = getAgentInfo(agent.id);
              return (
                <button
                  key={agent.id}
                  className={`agent-item ${index === agentPickerActiveIndex ? "active" : ""}`}
                  onMouseEnter={() => setAgentPickerActiveIndex(index)}
                  onClick={() => insertAgentMention(agent.id)}
                  role="option"
                  aria-selected={index === agentPickerActiveIndex}
                >
                  <span className={`agent-icon tone-${info.tone}`}>{info.emoji}</span>
                  <span className="agent-name">{agent.name}</span>
                  <span className="agent-id">@{agent.id}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* 待确认变更查看/审核弹窗 */}
      {showReviewArtifactModal && modalReviewArtifact && (
        <div className="modal-overlay" onClick={() => closeReviewArtifactModal()}>
          <div className="modal-content review-artifact-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span>{modalReviewArtifact.status === "awaiting_user" ? "待你确认" : "查看变更"}</span>
              <button
                className="modal-close"
                onClick={() => closeReviewArtifactModal()}
                disabled={isReviewArtifactModalLocked}
                aria-label={isReviewArtifactModalLocked ? "操作进行中，暂不能关闭" : "关闭"}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              {renderArtifactReviewDialog(modalReviewArtifact)}
            </div>
          </div>
        </div>
      )}

      {showArtifactTray && (
        <div className="modal-overlay" onClick={() => setShowArtifactTray(false)}>
          <div className="modal-content artifact-tray-modal" onClick={e => e.stopPropagation()}>
           <div className="modal-header">
              <span>待确认变更</span>
             <button className="modal-close" onClick={() => setShowArtifactTray(false)}>×</button>
           </div>
           <div className="modal-body artifact-tray-body">
             {reviewArtifacts.length === 0 ? (
                <div className="artifact-empty">暂无待确认变更。</div>
             ) : reviewArtifacts.map((artifact) => (
                <button
                  key={artifact.id}
                  className="artifact-tray-item"
                  type="button"
                  onClick={() => {
                    inspectReviewArtifactFromTray(artifact);
                  }}
                >
                  <span className="artifact-tray-main">
                   <span className="artifact-tray-title">{artifact.summary || artifact.artifactKey || artifact.id}</span>
                   <span className="artifact-tray-meta">
                      {getReviewArtifactKindLabel(artifact.kind)} · {getReviewArtifactImpactLabel(artifact.kind)} · v{artifact.revision}
                   </span>
                  </span>
                  <span className={`action-badge ${artifact.status}`}>
                    {getReviewArtifactStatusLabel(artifact.status)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {showSessionModal && (
        <div className="modal-overlay" onClick={() => setShowSessionModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span>会话列表</span>
              <button className="modal-close" onClick={() => setShowSessionModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <button className="new-session-btn" onClick={createSession}>+ 新建会话</button>
              <div className="session-list">
                {sessions.length === 0 ? (
                  <div className="empty-state">暂无会话记录</div>
                ) : (
                  sessions.map(session => (
                    <div
                      key={session.id}
                      className={`session-item ${currentSessionId === session.id ? "active" : ""}`}
                      onClick={() => selectSession(session.id)}
                    >
                      <div className="session-info">
                        <div className="session-title">{session.title || "未命名会话"}</div>
                        <div className="session-meta">
                          <span className={`status ${session.phase}`}>
                            {session.phase === "completed" ? "已完成" :
                             session.phase === "idle" ? "空闲" :
                             session.phase === "discussing" ? "讨论中" :
                             session.phase === "generating" ? "生成中" :
                             session.phase === "recording" ? "记录中" : session.phase}
                          </span>
                          <span className="date">
                            {new Date(session.updatedAt).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}
                          </span>
                        </div>
                      </div>
                      <button className="delete-btn" onClick={(e) => deleteSession(session.id, e)}>×</button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

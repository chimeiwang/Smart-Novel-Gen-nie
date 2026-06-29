"use client";

import { useCallback, useOptimistic, useRef, useState, useTransition, useEffect } from "react";

import { AGENT_REGISTRY, type AgentId, type OrchestrationEvent } from "@/agents/client";
import { acceptGeneratedContentAction } from "@/app/actions";
import type { WritingSseEvent } from "@/shared/contracts/sse-events";
import { parseSseEvent } from "@/shared/contracts/sse-events";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import {
  getCreativeOperationLabel,
  getCreativeOperationOutputLabel,
} from "@/shared/contracts/creative-operation";
import type { AgentUpdateSelectionRef } from "@/shared/contracts/agent-updates";
import type { ReviewArtifactDecision } from "@/shared/contracts/review-artifact";
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
  type LoadedSessionTask,
} from "./session-task-state";
import { shouldPersistOptimisticWritingMessage } from "./message-persistence";
import { createAsyncActionGuard } from "./send-guard";
import { getToolActivityLabel, isVisibleToolActivity } from "./tool-activity";
import "./writing-conversation.css";

type WritingConversationProps = {
  novelId: string;
  chapterId: string;
  selectedAgents: AgentId[];
  targetWordCount: number;
  onComplete?: () => void;
};

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

type LoadedSessionResponse = Session & {
  messages: Array<{
    id: string;
    role: string;
    agentId: string | null;
    content: string;
    intent: string | null;
    createdAt: string;
  }>;
  currentTask?: LoadedSessionTask;
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
    if (status === "succeeded") return "已丢弃草案，正在刷新状态...";
    if (status === "failed") return "丢弃失败，请检查错误后重试";
    return "正在丢弃草案...";
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

type WritingPhase = "idle" | "discussing" | "generating" | "reviewing" | "recording" | "completed" | "error";

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

type ToolActivityStatus =
  | "understanding"
  | "thinking"
  | "asking"
  | "discussing"
  | "drafting"
  | "refining"
  | "querying"
  | "responding"
  | "parsing"
  | "suggestions"
  | "completed"
  | "done"
  | "error"
  | string;

type ToolActivityEntry = {
  id: string;
  status: ToolActivityStatus;
  label: string;
  message: string;
  agentId?: string;
  toolName?: string;
  toolLabel?: string;
  argsSummary?: string;
  resultSummary?: string;
  timestamp: number;
};

type ToolActivityRound = {
  id: string;
  anchorMessageId?: string;
  entries: ToolActivityEntry[];
  expanded: boolean;
  running: boolean;
  updatedAt: number;
};

/** SSE 事件类型从共享契约导入 + Agent 客户端事件 */
type ExtendedEvent = WritingSseEvent | OrchestrationEvent;

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
  selectedAgents,
  targetWordCount,
  onComplete,
}: WritingConversationProps) {
  // 会话状态
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [showSessionModal, setShowSessionModal] = useState(false);
  const [showArtifactTray, setShowArtifactTray] = useState(false);

  // 消息状态
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeReviewArtifact, setActiveReviewArtifact] = useState<ReviewArtifactData | null>(null);
  const [reviewDialogArtifact, setReviewDialogArtifact] = useState<ReviewArtifactData | null>(null);
  const [reviewArtifacts, setReviewArtifacts] = useState<ReviewArtifactData[]>([]);
  const [optimisticReviewArtifact, addOptimisticReviewArtifactDecision] = useOptimistic(
    activeReviewArtifact,
    (
      current,
      action: { artifactId: string; decision: ReviewArtifactDecision }
    ) => applyOptimisticReviewArtifactDecision(current, action)
  );
  const [taskId, setTaskId] = useState<string | null>(null);
  const [showReviewArtifactModal, setShowReviewArtifactModal] = useState(false);
  const [reviewDraftText, setReviewDraftText] = useState("");
  const [selectedUpdateRefKeys, setSelectedUpdateRefKeys] = useState<Set<string>>(new Set());
  const [reviewArtifactAction, setReviewArtifactAction] = useState<ReviewArtifactActionState | null>(null);
  const [chapterTargetPrompt, setChapterTargetPrompt] = useState<ChapterTargetPrompt | null>(null);
  const reviewDraftSourceKeyRef = useRef<string | null>(null);
  const reviewUpdateSelectionSourceKeyRef = useRef<string | null>(null);

  // 其他状态
  const [phase, setPhase] = useState<WritingPhase>("idle");
  const [generatedContent, setGeneratedContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const [userInput, setUserInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isAssigningTask, setIsAssigningTask] = useState(false);
  const [currentStreamingAgent, setCurrentStreamingAgent] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const [pendingAgentHandoff, setPendingAgentHandoff] = useState<string | null>(null);

  const [showAgentPicker, setShowAgentPicker] = useState(false);
  const [agentPickerQuery, setAgentPickerQuery] = useState("");
  const [agentPickerActiveIndex, setAgentPickerActiveIndex] = useState(0);

  // 中断控制
  const abortRef = useRef<AbortController | null>(null);
  const sendGuardRef = useRef(createAsyncActionGuard());

  // 中断当前 Agent 并立即开始处理新消息
  const abortCurrentAgent = () => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setIsSending(false);
    setIsAssigningTask(false);
    setCurrentStreamingAgent(null);
    setStreamingContent("");
    setPendingAgentHandoff(null);
    streamingRef.current = { agentId: "", content: "" };
  };
  const [cursorPosition, setCursorPosition] = useState(0);
  const [showFlowLog, setShowFlowLog] = useState(false);
  const [flowLogs, setFlowLogs] = useState<FlowLogEntry[]>([]);
  const [activityRounds, setActivityRounds] = useState<ToolActivityRound[]>([]);
  const activeActivityRoundRef = useRef<string | null>(null);

  const [currentOperation, setCurrentOperation] = useState<CreativeOperation | null>(null);
  const [currentOperationStage, setCurrentOperationStage] = useState<string | null>(null);

  // 编辑相关
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  const streamingRef = useRef<{ agentId: string; content: string }>({ agentId: "", content: "" });
  const activeReviewArtifactRef = useRef<ReviewArtifactData | null>(null);
  const reviewArtifactActionRef = useRef<ReviewArtifactActionState | null>(null);
  const reviewActionCloseTimerRef = useRef<number | null>(null);
  const taskIdRef = useRef<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const pendingReviewArtifactRefreshRef = useRef(false);

  const updateReviewArtifactAction = useCallback((next: ReviewArtifactActionState | null) => {
    reviewArtifactActionRef.current = next;
    setReviewArtifactAction(next);
  }, []);

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
    if (reviewDraftSourceKeyRef.current !== draftSourceKey) {
      reviewDraftSourceKeyRef.current = draftSourceKey;
      setReviewDraftText(getReviewArtifactContent(artifact));
    }
    const updateSelectionSourceKey = `${artifact.id}:${artifact.revision}:updates`;
    if (reviewUpdateSelectionSourceKeyRef.current !== updateSelectionSourceKey) {
      reviewUpdateSelectionSourceKeyRef.current = updateSelectionSourceKey;
      setSelectedUpdateRefKeys(new Set(getStructuredUpdateRefs(artifact.payload?.updates).map(getUpdateSelectionKey)));
    }
    setShowReviewArtifactModal(true);
  }, [clearReviewActionCloseTimer, updateReviewArtifactAction]);

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
  }, [closeReviewArtifactModal]);

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

  useEffect(() => {
    setCurrentSessionId(null);
    setTaskId(null);
    taskIdRef.current = null;
    setPhase("idle");
    setGeneratedContent("");
    setActiveReviewArtifact(null);
    activeReviewArtifactRef.current = null;
    setReviewDialogArtifact(null);
    setReviewArtifacts([]);
    setChapterTargetPrompt(null);
    setCurrentOperation(null);
    setCurrentOperationStage(null);
    setActivityRounds([]);
    activeActivityRoundRef.current = null;
    updateReviewArtifactAction(null);
  }, [chapterId, updateReviewArtifactAction]);

  const getLocalReviewDraftForApply = useCallback((artifact: ReviewArtifactData): string | undefined => {
    if (!getReviewArtifactContent(artifact)) return undefined;
    const draftSourceKey = `${artifact.id}:${artifact.revision}`;
    if (reviewDraftSourceKeyRef.current !== draftSourceKey) return undefined;
    return reviewDraftText;
  }, [reviewDraftText]);

  const getSelectedUpdateRefsForApply = useCallback((artifact: ReviewArtifactData): AgentUpdateSelectionRef[] | undefined => {
    const allRefs = getStructuredUpdateRefs(artifact.payload?.updates);
    if (allRefs.length === 0) return undefined;
    const updateSelectionSourceKey = `${artifact.id}:${artifact.revision}:updates`;
    if (reviewUpdateSelectionSourceKeyRef.current !== updateSelectionSourceKey) return undefined;
    return allRefs.filter((ref) => selectedUpdateRefKeys.has(getUpdateSelectionKey(ref)));
  }, [selectedUpdateRefKeys]);

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
      const res = await fetch(`/api/writing/sessions?novelId=${novelId}&chapterId=${chapterId}`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
      }
    } catch (err) {
      console.error("加载会话列表失败", err);
    }
  }, [novelId, chapterId]);

  const loadReviewArtifacts = useCallback(async () => {
    try {
      const response = await fetch(`/api/writing/review-artifact?novelId=${novelId}`, { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json() as { artifacts?: ReviewArtifactData[] };
      setReviewArtifacts((data.artifacts ?? []).filter(isActionableReviewArtifact));
    } catch (err) {
      console.error("加载草案箱失败", err);
    }
  }, [novelId]);

  // 加载会话消息
  const loadSessionMessages = useCallback(async (sessionId: string) => {
    try {
      const res = await fetch(`/api/writing/sessions/${sessionId}`);
      if (res.ok) {
        const session = await res.json() as LoadedSessionResponse;
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
        activeReviewArtifactRef.current = null;
        setActiveReviewArtifact(null);
        setReviewDialogArtifact(null);
        updateReviewArtifactAction(null);
        setShowReviewArtifactModal(false);
        reviewDraftSourceKeyRef.current = null;
        setReviewDraftText("");
        setMessages(loadedMessages);
        setTaskId(sessionTaskState.taskId);
        taskIdRef.current = sessionTaskState.taskId;
        setPhase(sessionTaskState.phase);
        setCurrentOperation(sessionTaskState.currentOperation);
        setCurrentOperationStage(sessionTaskState.operationStage);
        activeActivityRoundRef.current = null;
        setActivityRounds([]);
        setIsAssigningTask(false);
        setPendingAgentHandoff(null);
        pendingReviewArtifactRefreshRef.current =
          sessionTaskState.shouldRefreshAwaitingReviewArtifact;
      }
    } catch (err) {
      console.error("加载会话消息失败", err);
    }
  }, [updateReviewArtifactAction]);

  // 创建新会话
  const createSession = useCallback(async (): Promise<string | null> => {
    try {
      const res = await fetch("/api/writing/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ novelId, chapterId }),
      });
      if (res.ok) {
        const session = await res.json();
        await loadSessions();
        setCurrentSessionId(session.id);
        setMessages([]);
        activeActivityRoundRef.current = null;
        setActivityRounds([]);
        setIsAssigningTask(false);
        setPendingAgentHandoff(null);
        setPhase("idle");
        setTaskId(null);
        taskIdRef.current = null;
        setReviewDialogArtifact(null);
        updateReviewArtifactAction(null);
        setShowSessionModal(false);
        return session.id;
      }
    } catch (err) {
      console.error("创建会话失败", err);
    }
    return null;
  }, [novelId, chapterId, loadSessions, updateReviewArtifactAction]);

  // 删除会话
  const deleteSession = useCallback(async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("确定要删除这个会话吗？")) return;
    try {
      const res = await fetch(`/api/writing/sessions/${sessionId}`, { method: "DELETE" });
      if (res.ok) {
        await loadSessions();
      if (currentSessionId === sessionId) {
        setCurrentSessionId(null);
        setMessages([]);
        setPhase("idle");
        setTaskId(null);
        taskIdRef.current = null;
        setReviewDialogArtifact(null);
        updateReviewArtifactAction(null);
      }
      }
    } catch (err) {
      console.error("删除会话失败", err);
    }
  }, [currentSessionId, loadSessions, updateReviewArtifactAction]);

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
      await fetch("/api/writing/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: targetSessionId,
          role,
          agentId,
          content,
          intent,
        }),
      });
    } catch (err) {
      console.error("保存消息失败", err);
    }
  }, [currentSessionId]);

  // 选择会话
  const selectSession = useCallback(async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    await loadSessionMessages(sessionId);
    setShowSessionModal(false);
  }, [loadSessionMessages]);

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

  const startActivityRound = useCallback((anchorMessageId?: string) => {
    const roundId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    activeActivityRoundRef.current = roundId;
    setActivityRounds((prev) => [
      ...prev,
      {
        id: roundId,
        anchorMessageId,
        entries: [],
        expanded: true,
        running: true,
        updatedAt: Date.now(),
      },
    ]);
    return roundId;
  }, []);

  const ensureActivityRound = useCallback(() => {
    if (activeActivityRoundRef.current) return activeActivityRoundRef.current;
    return startActivityRound();
  }, [startActivityRound]);

  const addActivityEntry = useCallback((entry: Omit<ToolActivityEntry, "id" | "timestamp">) => {
    const roundId = ensureActivityRound();
    const nextEntry: ToolActivityEntry = {
      ...entry,
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      timestamp: Date.now(),
    };
    setActivityRounds((prev) =>
      prev.map((round) =>
        round.id === roundId
          ? { ...round, entries: [...round.entries, nextEntry], running: true, expanded: true, updatedAt: Date.now() }
          : round
      )
    );
  }, [ensureActivityRound]);

  const attachActivityRoundToMessage = useCallback((messageId: string) => {
    const roundId = activeActivityRoundRef.current;
    if (!roundId) return;
    setActivityRounds((prev) =>
      prev.map((round) =>
        round.id === roundId ? { ...round, anchorMessageId: messageId, updatedAt: Date.now() } : round
      )
    );
  }, []);

  const finishActivityRound = useCallback((status: "done" | "error" = "done") => {
    const roundId = activeActivityRoundRef.current;
    if (!roundId) return;
    setActivityRounds((prev) =>
      prev.map((round) =>
        round.id === roundId
          ? {
              ...round,
              running: false,
              expanded: false,
              updatedAt: Date.now(),
              entries: status === "error"
                ? [
                    ...round.entries,
                    {
                      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
                      status: "error",
                      label: "出错",
                      message: "处理出错",
                      timestamp: Date.now(),
                    },
                  ]
                : round.entries,
            }
          : round
      )
    );
    activeActivityRoundRef.current = null;
  }, []);

  const collapseActivityRound = useCallback(() => {
    const roundId = activeActivityRoundRef.current;
    if (!roundId) return;
    setActivityRounds((prev) =>
      prev.map((round) =>
        round.id === roundId ? { ...round, running: false, expanded: false, updatedAt: Date.now() } : round
      )
    );
  }, []);

  const toggleActivityRound = useCallback((roundId: string) => {
    setActivityRounds((prev) =>
      prev.map((round) => round.id === roundId ? { ...round, expanded: !round.expanded } : round)
    );
  }, []);

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
      taskIdRef.current = nextTaskId;
      setTaskId(nextTaskId);
    }
    activeReviewArtifactRef.current = artifact;
    setActiveReviewArtifact(artifact);
    setReviewArtifacts((prev) => {
      const rest = prev.filter((item) => item.id !== artifact.id);
      return isActionableReviewArtifact(artifact) ? [artifact, ...rest] : rest;
    });
    if (artifact.status === "awaiting_user") setPhase("recording");
    setMessages((prev) => attachReviewArtifactToConversation<Message, ReviewArtifactData>(prev, artifact, () => ({
      id: `restored-review-${artifact.id}`,
      role: "system",
      content: "待审核草案已更新。请在下方卡片中查看、修改或应用。",
      timestamp: Date.now(),
    })));
  }, [taskId]);

  const inspectReviewArtifactFromTray = useCallback((artifact: ReviewArtifactData) => {
    setReviewArtifacts((prev) => {
      const rest = prev.filter((item) => item.id !== artifact.id);
      return isActionableReviewArtifact(artifact) ? [artifact, ...rest] : rest;
    });
    setShowArtifactTray(false);
    openReviewArtifactModal(artifact);
  }, [openReviewArtifactModal]);

  const refreshAwaitingReviewArtifact = useCallback(async (reason: string) => {
    const currentTaskId = taskIdRef.current ?? taskId;
    if (!currentTaskId) return;
    try {
      const response = await fetch(`/api/writing/tasks/${currentTaskId}/review-artifact`, { cache: "no-store" });
      if (!response.ok) return;
      const data = await response.json() as { artifact?: ReviewArtifactData | null };

      if (!data?.artifact) return;

      setWorkflowReviewArtifact(data.artifact);
      addFlowLog({
        type: "phase",
        content: `已恢复待审核草案入口：${data.artifact.artifactKey ?? data.artifact.id}`,
      });
      console.debug("[WritingReviewArtifact] recovered awaiting artifact", {
        reason,
        artifactId: data.artifact.id,
        status: data.artifact.status,
      });
    } catch (err) {
      console.warn("[WritingReviewArtifact] refresh failed", err);
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

  const handleEvent = useCallback((event: ExtendedEvent) => {
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
        taskIdRef.current = event.taskId ?? null;
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

      case "agent_start":
        setIsAssigningTask(false);
        setCurrentStreamingAgent(event.agentId);
        setStreamingContent("");
        setPendingAgentHandoff(event.agentId);
        streamingRef.current = { agentId: event.agentId, content: "" };
        agentStartTimes.current.set(event.agentId, Date.now());
        addFlowLog({ type: "agent_start", agentId: event.agentId, content: `${getAgentName(event.agentId)} 开始` });
        break;

      case "agent_status":
        if (event.status === "error" && event.message) {
          addMessage({ role: "system", content: event.message, persist: false });
          setError(event.message);
        }
        if (event.toolName && isVisibleToolActivity(event.toolName)) {
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

      case "agent_chunk":
        setPendingAgentHandoff(null);
        setStreamingContent((prev) => prev + event.chunk);
        streamingRef.current.content += event.chunk;
        break;

      case "agent_done":
        const savedContent = streamingRef.current;
        const duration = agentStartTimes.current.get(event.agentId);

        // Phase D 返工：新协议下 content 是段落文本，不解析 business protocol。
        // 不调用 extractDisplayContent()，直接使用原始内容。
        const rawEventContent = "content" in event ? (event as { content?: string }).content ?? "" : "";
        const rawStreamContent = savedContent.content;
        const finalContent =
          rawEventContent.length >= rawStreamContent.length
            ? rawEventContent
            : rawStreamContent;

        console.debug("[SSE] agent_done:", {
          agentId: event.agentId,
          savedLen: savedContent.content.length,
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
          attachActivityRoundToMessage(messageId);
        }
        setCurrentStreamingAgent(null);
        setStreamingContent("");
        setPendingAgentHandoff(null);
        streamingRef.current = { agentId: "", content: "" };
        agentStartTimes.current.delete(event.agentId);
        collapseActivityRound();
        addFlowLog({
          type: "agent_done",
          agentId: event.agentId,
          content: `${getAgentName(event.agentId)} 完成`,
          duration: duration ? Date.now() - duration : undefined,
        });
        break;

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

      case "host_intent":
        addFlowLog({
          type: "intent",
          content: `主持人意图: ${event.intent?.action ?? "unknown"}${event.intent?.reason ? ` - ${event.intent.reason}` : ""}`,
        });
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
            ? "待审核草案已通过 Agent 复审，等待用户确认"
            : `已提交待审核草案 ${event.artifactId}`,
        });
        break;

      case "review_artifact_requested":
        if ("artifact" in event && event.artifact) {
          const artifact = event.artifact as ReviewArtifactData;
          setWorkflowReviewArtifact(artifact);
          setShowArtifactTray(false);
          addFlowLog({
            type: "phase",
            content: `Agent 请求刷新草案卡片：${artifact.artifactKey ?? artifact.id}`,
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
          activeReviewArtifactRef.current = null;
          setActiveReviewArtifact(null);
          setReviewArtifacts((prev) => prev.filter((artifact) => artifact.id !== event.artifactId));
          setMessages((prev) => clearReviewArtifactFromMessages(prev, event.artifactId));
          setPhase("completed");
          addFlowLog({ type: "phase", content: event.summary ?? "待审核草案已应用到正式库" });
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
          setError(event.errors?.join("\n") || event.summary || "应用待审核草案失败");
        }
        break;

      case "artifact_deleted":
        updateReviewArtifactAction({
          artifactId: event.artifactId,
          decision: "discard",
          status: "succeeded",
          message: getReviewArtifactActionMessage("discard", "succeeded"),
        });
        activeReviewArtifactRef.current = null;
        setActiveReviewArtifact(null);
        setReviewArtifacts((prev) => prev.filter((artifact) => artifact.id !== event.artifactId));
        setMessages((prev) => clearReviewArtifactFromMessages(prev, event.artifactId));
        setPhase("completed");
        addFlowLog({ type: "phase", content: "已丢弃待审核草案" });
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
        setCurrentStreamingAgent(null);
        setStreamingContent("");
        setPendingAgentHandoff(null);
        streamingRef.current = { agentId: "", content: "" };
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
        setPendingAgentHandoff(null);
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
        setPendingAgentHandoff(null);
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
        console.debug("[SSE] 未处理的事件类型:", (event as ExtendedEvent).type, event);
        break;
    }
  }, [messages.length, addActivityEntry, addMessage, addFlowLog, attachActivityRoundToMessage, collapseActivityRound, finishActivityRound, formatOperationLog, getAgentName, loadSessions, loadReviewArtifacts, onComplete, openReviewArtifactModal, refreshAwaitingReviewArtifact, scheduleReviewArtifactModalClose, setWorkflowReviewArtifact, updateReviewArtifactAction]);

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
    startActivityRound();
    setIsAssigningTask(true);
    addFlowLog({ type: "user", content: `用户: ${userMessage.slice(0, 50)}${userMessage.length > 50 ? "..." : ""}` });
    setPhase("discussing");
    setIsSending(true);

    try {
      const response = await fetch("/api/writing/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          novelId,
          chapterId,
          targetWordCount,
          selectedAgents,
          userMessage,
          writingSessionId: sessionIdForRequest,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "启动会话失败");
      }

      await processStream(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "未知错误");
      setPhase("error");
      setIsAssigningTask(false);
    } finally {
      setIsSending(false);
      setCurrentStreamingAgent(null);
      setStreamingContent("");
      setPendingAgentHandoff(null);
      streamingRef.current = { agentId: "", content: "" };
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
      startActivityRound();
      setIsSending(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch("/api/writing/resume", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ taskId, writingSessionId: currentSessionId ?? undefined, userMessage: message }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "继续会话失败");
        }

        await processStream(response);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setError(err instanceof Error ? err.message : "发送失败");
      } finally {
        setIsSending(false);
        setCurrentStreamingAgent(null);
        setStreamingContent("");
        setPendingAgentHandoff(null);
        streamingRef.current = { agentId: "", content: "" };
      }
    });
    await guarded;
  };

  const handleSyncRecentLore = async () => {
    const message = "@设定 根据当前章节及最近几章正文，维护设定库。请只提取明确发生的事实变化：优先新增角色经历和更新当前状态；不要用最近几章的临时描写覆盖角色性格、背景、外貌、身份等长期设定。";
    if (taskId && phase !== "idle") {
      await handleSendMessage(message);
    } else {
      await handleStartDiscussion(message);
    }
  };

  const handleStartWriting = async () => {
    const message = "开始生成正文";
    if (taskId && phase !== "idle") {
      await handleSendMessage(message);
    } else {
      await handleStartDiscussion(message);
    }
  };

  const processStream = async (response: Response) => {
    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");

      // 最后一行可能是不完整的 SSE 数据，保留到下次处理
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const parsed = JSON.parse(line.slice(6)); const event = parseSseEvent(parsed) || (parsed as ExtendedEvent); handleEvent(event);
          } catch { /* JSON 解析失败，静默跳过 */ }
        }
      }
    }

    // 处理流结束后 buffer 中的最后一行
    if (buffer.startsWith("data: ")) {
      try {
        handleEvent(JSON.parse(buffer.slice(6)) as ExtendedEvent);
      } catch { /* ignore */ }
    }

    if (shouldRefreshAwaitingReviewArtifact({
      eventType: "done",
      hasTaskId: Boolean(taskIdRef.current ?? taskId),
      visibleArtifactStatus: activeReviewArtifactRef.current?.status ?? null,
    })) {
      await refreshAwaitingReviewArtifact("stream_end");
    }
  };

  const handleAcceptContent = () => {
    if (!taskId) return;

    startTransition(async () => {
      try {
        const result = await acceptGeneratedContentAction({ taskId, chapterId });

        if (result.success) {
          addMessage({ role: "system", content: `内容已采纳，新增 ${result.newWordCount} 字` });
          onComplete?.();
          setPhase("completed");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "采纳内容失败");
      }
    });
  };

  const handleChapterTargetDecision = async (decision: "current_chapter" | "next_chapter") => {
    const currentTaskId = taskIdRef.current ?? taskId;
    if (!currentTaskId) return;
    setChapterTargetPrompt(null);
    setIsSending(true);
    try {
      const response = await fetch("/api/writing/resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          taskId: currentTaskId,
          writingSessionId: currentSessionId ?? undefined,
          userDecision: {
            type: "chapter_target_confirmation",
            decision,
          },
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || "恢复写作目标确认失败");
      }

      await processStream(response);
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

  const ArtifactReviewCard = ({ artifact }: { artifact: ReviewArtifactData }) => {
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
            <div className="review-artifact-title">待审核草案</div>
            {artifact.summary ? <div className="review-artifact-summary">{artifact.summary}</div> : null}
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
              <span className="review-evaluation-summary">草案正在复审，复审通过后再由你确认是否应用。</span>
            </div>
          ) : null}
          {artifactContent ? (
            <div className="review-artifact-preview">
              <div className="review-artifact-preview-title">草案预览</div>
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
                {getReviewArtifactActionButtonLabel(action, "discard") ?? (artifact.optimisticStatus === "discarding" ? "丢弃中..." : "丢弃草案")}
              </button>
              </>
            ) : (
              <button
                className="button ghost sm"
                type="button"
                onClick={() => openReviewArtifactModal(artifact)}
              >
                查看草案
              </button>
            )}
          </div>
        </div>
      </div>
    );
  };

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

    return (
      <div className={`review-dialog ${actionLocked ? "is-busy" : ""}`} aria-busy={actionLocked}>
        <div className="review-dialog-meta">
          <div>
            <div className="review-dialog-title">待审核草案</div>
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
            <div className="review-dialog-section-title">{canEditText ? "草案正文" : "结构化变更"}</div>
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
                <div className="review-dialog-note">这个草案还没有进入等待确认状态，只能查看，不能直接应用。</div>
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
                onClick={focusChatForArtifactRevision}
              >
                {getReviewArtifactActionButtonLabel(action, "revise") ?? (artifact.optimisticStatus === "revising" ? "准备返工..." : "继续修改")}
              </button>
              <button
                className="button ghost"
                type="button"
                disabled={isSending || isActing || actionLocked}
                onClick={() => handleArtifactDecision(artifact, "discard")}
              >
                {getReviewArtifactActionButtonLabel(action, "discard") ?? (artifact.optimisticStatus === "discarding" ? "丢弃中..." : "丢弃草案")}
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

  const handleArtifactDecision = async (
    artifact: ReviewArtifactData,
    decision: ReviewArtifactDecision,
    userMessage?: string,
    editedContent?: string,
    selectedUpdateRefs?: AgentUpdateSelectionRef[]
  ) => {
    const guarded = runSendAction(async () => {
      const currentUiTaskId = taskIdRef.current ?? taskId;
      const currentTaskId = resolveReviewArtifactActionTaskId(
        taskIdRef.current ?? taskId,
        artifact
      );
      if (!currentTaskId) {
        updateReviewArtifactAction({
          artifactId: artifact.id,
          decision,
          status: "failed",
          message: "找不到当前写作任务，无法处理待审核草案。请刷新页面后重试。",
        });
        setError("找不到当前写作任务，无法处理待审核草案。请刷新页面后重试。");
        setPhase("error");
        return;
      }
      const shouldBindTaskToUi = activeReviewArtifactRef.current?.id === artifact.id || !currentUiTaskId;
      if (shouldBindTaskToUi && currentTaskId !== taskIdRef.current) {
        taskIdRef.current = currentTaskId;
        setTaskId(currentTaskId);
      }

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
        const response = await fetch("/api/writing/resume", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            taskId: currentTaskId,
            writingSessionId: currentTaskId === currentUiTaskId ? currentSessionId ?? undefined : undefined,
            userDecision: {
              type: "artifact_review",
              artifactId: artifact.id,
              decision,
              userMessage: userMessage ?? (decision === "revise" ? "继续修改待审核草案" : undefined),
              editedContent: decision === "approve" ? editedContent : undefined,
              selectedUpdateRefs: decision === "approve" ? selectedUpdateRefs : undefined,
            },
          }),
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.error || "处理待审核草案失败");
        }

        await processStream(response);
      } catch (err) {
        const message = err instanceof Error ? err.message : "处理待审核草案失败";
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
        setCurrentStreamingAgent(null);
        setStreamingContent("");
        setPendingAgentHandoff(null);
        streamingRef.current = { agentId: "", content: "" };
      }
    });
    await guarded;
  };

  const getActivityRoundTitle = (round: ToolActivityRound) => {
    const queryCount = round.entries.filter((entry) => entry.status === "querying" && entry.toolName && !entry.resultSummary).length;
    const latest = round.entries[round.entries.length - 1];
    const stateLabel = round.running ? latest?.label ?? "处理中" : "已完成";
    return `${stateLabel}${queryCount > 0 ? ` · 查询 ${queryCount} 次` : ""}`;
  };

  const getActivityGroups = (round: ToolActivityRound) => {
    const groups = [
      { key: "thinking", label: "思考", entries: round.entries.filter((entry) => entry.status !== "querying" && entry.status !== "responding" && entry.status !== "parsing") },
      { key: "querying", label: "查询", entries: round.entries.filter((entry) => entry.status === "querying") },
      { key: "responding", label: "生成", entries: round.entries.filter((entry) => entry.status === "responding") },
      { key: "parsing", label: "整理", entries: round.entries.filter((entry) => entry.status === "parsing") },
    ];
    return groups.filter((group) => group.entries.length > 0);
  };

  const renderActivityRound = (round: ToolActivityRound) => {
    if (round.entries.length === 0) return null;
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

  const renderQuickReviewActions = (artifact: ReviewArtifactData) => {
    const localDraftForApply = getLocalReviewDraftForApply(artifact);
    const action = getReviewArtifactAction(artifact.id);
    const actionLocked = isReviewArtifactActionLocked(action);
    const isApplyDisabled = isSending ||
      actionLocked ||
      Boolean(artifact.optimisticStatus) ||
      (localDraftForApply !== undefined && !localDraftForApply.trim());

    return (
      <>
        <button
          disabled={isApplyDisabled}
          onClick={() => handleArtifactDecision(
            artifact,
            "approve",
            undefined,
            localDraftForApply
          )}
        >
          {getReviewArtifactActionButtonLabel(action, "approve") ?? (artifact.optimisticStatus === "applying" ? "应用中..." : "应用到项目")}
        </button>
        <button
          disabled={isSending || actionLocked || Boolean(artifact.optimisticStatus)}
          onClick={focusChatForArtifactRevision}
        >
          {getReviewArtifactActionButtonLabel(action, "revise") ?? (artifact.optimisticStatus === "revising" ? "准备返工..." : "继续修改")}
        </button>
        <button
          disabled={isSending || actionLocked || Boolean(artifact.optimisticStatus)}
          onClick={() => handleArtifactDecision(artifact, "discard")}
        >
          {getReviewArtifactActionButtonLabel(action, "discard") ?? (artifact.optimisticStatus === "discarding" ? "丢弃中..." : "丢弃草案")}
        </button>
      </>
    );
  };

  const pendingActivityRounds = activityRounds.filter((round) => !round.anchorMessageId);
  const streamingDisplayAgent = currentStreamingAgent ?? "system";
  const shouldShowStreamingMessage = Boolean(pendingActivityRounds.length > 0 || (currentStreamingAgent && streamingContent));

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
            onClick={() => {
              void loadReviewArtifacts();
              setShowArtifactTray(true);
            }}
          >
            草案 {reviewArtifacts.length}
            {awaitingArtifactCount > 0 ? <span className="artifact-count-hot">{awaitingArtifactCount}</span> : null}
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

      {/* 消息区域 */}
      <div className="chat-messages" ref={chatRef}>
        {messages.length === 0 && phase === "idle" && !currentStreamingAgent && (
          <div className="welcome-state">
            <div className="welcome-icon">💬</div>
            <div className="welcome-text">开始一段新的讨论吧</div>
            <div className="agent-quick-btns">
              <div className="agent-quick-section">
                <div className="agent-quick-label">常用操作</div>
                <div className="agent-quick-row">
                  <button
                    className="agent-quick-btn"
                    onClick={handleSyncRecentLore}
                    disabled={isSending}
                  >
                    <span className="agent-icon tone-blue">设</span>
                    <span className="agent-name">同步设定</span>
                  </button>
                  <button
                    className="agent-quick-btn"
                    onClick={handleStartWriting}
                    disabled={isSending}
                  >
                    <span className="agent-icon tone-green">写</span>
                    <span className="agent-name">开始写作</span>
                  </button>
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
                    {anchoredRounds.map(renderActivityRound)}
                    <ParagraphText text={renderParagraphMessageContent(msg)} />
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
                    <ArtifactReviewCard artifact={resolveMessageReviewArtifact(msg.reviewArtifact)} />
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

        {pendingAgentHandoff ? (
          <div className="assignment-status" aria-live="polite">
            {getAgentName(pendingAgentHandoff)} 正在接手
          </div>
        ) : null}

        {shouldShowStreamingMessage && currentStreamingAgent && (
          <div className="message message-agent">
            <div className={`message-avatar tone-${getAgentInfo(streamingDisplayAgent).tone}`}>
              {getAgentInfo(streamingDisplayAgent).emoji}
            </div>
            <div className="message-body">
              <div className="message-header">{getAgentName(streamingDisplayAgent)}</div>
              <div className="message-content streaming">
                {pendingActivityRounds.map(renderActivityRound)}
                {streamingContent ? <ParagraphText text={streamingContent} /> : null}
                {streamingContent ? <span className="cursor">●</span> : null}
              </div>
            </div>
          </div>
        )}

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
                {currentOperation.requiresArtifact ? <span>待审核草案</span> : null}
                {currentOperation.requiresUserApproval ? <span>用户确认</span> : null}
              </div>
            )}
          </div>
        )}

        {generatedContent && (
          <div className="preview-section">
            <div className="preview-header">
              <span>📝 正文预览</span>
              <span className="word-count">{generatedContent.length} 字</span>
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
          <ArtifactReviewCard artifact={workflowReviewArtifact} />
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
              renderQuickReviewActions(workflowReviewArtifact)
            ) : phase === "reviewing" ? (
              <>
                <button onClick={() => handleSendMessage("确认保存")}>确认保存</button>
                <button onClick={() => handleSendMessage("取消")}>取消</button>
              </>
            ) : (
              <>
                {hasWriter && <button onClick={() => handleSendMessage("开始生成正文")}>开始写作</button>}
                <button onClick={() => handleSendMessage("保存讨论结果")}>保存设定</button>
                <button onClick={handleSyncRecentLore}>同步设定</button>
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

      {/* 草案查看/审核弹窗 */}
      {showReviewArtifactModal && modalReviewArtifact && (
        <div className="modal-overlay" onClick={() => closeReviewArtifactModal()}>
          <div className="modal-content review-artifact-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span>{modalReviewArtifact.status === "awaiting_user" ? "待你审核" : "查看草案"}</span>
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
              <span>小说草案箱</span>
              <button className="modal-close" onClick={() => setShowArtifactTray(false)}>×</button>
            </div>
            <div className="modal-body artifact-tray-body">
              {reviewArtifacts.length === 0 ? (
                <div className="artifact-empty">暂无未处理草案</div>
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
                      {getReviewArtifactKindLabel(artifact.kind)} · v{artifact.revision}
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

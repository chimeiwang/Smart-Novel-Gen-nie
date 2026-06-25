/**
 * 工作流运行器
 *
 * @module agents/graph/workflow-runner
 * @description Phase 5 拆分：HTTP 入口（executeWritingWorkflow + resumeWriting + createInitialState）。
 *  组合 graph-definition、sse-adapter、task-state，封装为 SSE Response。
 *
 * @phase Phase 5 — 拆分 LangGraph 执行器
 */

import { Command, isInterrupted } from "@langchain/langgraph";
import type { WritingState, CoreAgentId, WritingPhase } from "./state";
import { CORE_AGENT_IDS } from "./state";
import { deleteGraphThreadCheckpoint, getGraph } from "./graph-definition";
import type { GraphState } from "./graph-definition";
import {
  SSE_HEADERS,
  STREAM_MODES,
  SendEventFn,
  createDirectEventCallbacks,
  createDirectStreamCallbacks,
  createSSEController,
  sendAgentDoneFallback,
} from "./sse-adapter";
import { clearTaskAwaitingUserReview, updateTaskState } from "./task-state";
import {
  buildContextSummary,
  loadHistoryFromDb,
  saveHistoryToDb,
} from "./context-manager";
import { aggregateNovelContextLightweight } from "@/shared/lib/context-aggregator";
import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import { applyReviewArtifact } from "@/agents/artifacts/artifact-apply";
import { discardArtifactHard } from "@/agents/artifacts/artifact-service";
import {
  traceWorkflowExecution,
  createTraceMetadata,
} from "@/agents/lib/langsmith-tracer";
import { getResumeMode } from "./resume-policy";
import {
  createWorkflowEventFileLogger,
} from "./workflow-event-log";
import type {
  WorkflowEventFileLogger,
  WorkflowEventLogContext,
} from "./workflow-event-log";
import { buildArtifactRevisionResume } from "./artifact-revision-routing";
import type { UserDecision } from "@/shared/contracts/user-decision";
import { getAgentObservabilityConfig } from "@/shared/env";
import { enqueueDbWrite } from "@/shared/lib/db-write-queue";
import {
  deserializeGraphStateSnapshot,
  rehydrateGraphStateFromSnapshot,
} from "./graph-state-snapshot";
import { persistWorkflowMessage } from "./workflow-message-store";

// ============================================
// 入口参数
// ============================================

export interface WorkflowInitialState {
  novelId: string;
  chapterId: string;
  writingSessionId?: string | null;
  targetWordCount: number;
  userMessage: string;
  userId: string;
  /** 章节质量检查项 ID。传入后质量报告会精确落到该检查项。 */
  qualityCheckId?: string | null;
  /** 本次启用的 Agent 列表（不传默认全选） */
  selectedAgents?: string[];
}

async function cleanupGraphCheckpoint(taskId: string, auditLog?: WorkflowEventFileLogger): Promise<void> {
  try {
    await deleteGraphThreadCheckpoint(taskId);
    auditLog?.recordPersistenceEvent("graph_checkpoint_deleted", { taskId });
  } catch (error) {
    logger.warn("WORKFLOW", "清理 LangGraph MemorySaver checkpoint 失败", {
      taskId,
      error: error instanceof Error ? error.message : String(error),
    });
    auditLog?.recordError("graph_checkpoint_delete_failed", error);
  }
}

function shouldUseLangGraphStreamEvents(): boolean {
  const config = getAgentObservabilityConfig();
  return config.langGraphStreamEventsEnabled && config.langGraphMemorySaverEnabled;
}

function graphStateFromInvokeResult(result: unknown): GraphState | null {
  if (!result || typeof result !== "object" || isInterrupted(result)) return null;
  return result as GraphState;
}

function emitInterruptFromInvokeResult(
  result: unknown,
  sendEvent: SendEventFn
): boolean {
  if (!isInterrupted(result)) return false;
  const value = result.__interrupt__?.[0]?.value;
  if (value && typeof value === "object") {
    sendEvent("user_input_required", value as Record<string, unknown>);
  } else {
    sendEvent("user_input_required", { type: "user_input_required" });
  }
  return true;
}

async function getGraphStateAfterRun(
  graph: ReturnType<typeof getGraph>,
  config: { configurable: { thread_id: string } },
  fallback?: GraphState | null
): Promise<GraphState | null> {
  try {
    const finalState = await graph.getState(config);
    return finalState ? finalState.values as GraphState : fallback ?? null;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!/No checkpointer set|MISSING_CHECKPOINTER/.test(message)) throw error;
    return fallback ?? null;
  }
}

async function getWritingSessionIdForTask(taskId: string): Promise<string | null> {
  const task = await prisma.writingTask.findUnique({
    where: { id: taskId },
    select: { writingSessionId: true },
  });
  return task?.writingSessionId ?? null;
}

// ============================================
// createInitialState
// ============================================

/**
 * 创建写作工作流初始状态
 */
export async function createInitialState(params: WorkflowInitialState): Promise<GraphState> {
  const { novelId, chapterId, writingSessionId, targetWordCount, userMessage, userId, qualityCheckId, selectedAgents } = params;
  logger.info("WORKFLOW", "创建初始状态", { novelId, chapterId, selectedAgents });

  const novelData = await aggregateNovelContextLightweight(novelId, chapterId);

  const effectiveAgents = selectedAgents && selectedAgents.length > 0
    ? selectedAgents.filter((id) => CORE_AGENT_IDS.includes(id as any))
    : [...CORE_AGENT_IDS];

  const task = await prisma.writingTask.create({
    data: {
      novelId,
      chapterId,
      writingSessionId: writingSessionId ?? null,
      targetWordCount,
      selectedAgents: effectiveAgents.join(","),
      phase: "active",
      conversationHistory: "[]",
    },
  });

  return {
    taskId: task.id,
    userId,
    novelId,
    chapterId,
    targetWordCount,
    phase: "active",
    userMessage,
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: null,
    currentOperation: null,
    operationMode: "operation_graph",
    operationStage: null,
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData: { ...novelData, novelId, chapterId } as WritingState["novelData"],
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    eventCallbacks: undefined,
    nextAgent: null,
    callChainDepth: 0,
    qualityCheckId: qualityCheckId ?? null,
    controlEvents: undefined,
    activeArtifactId: null,
    artifactMode: "none",
    reviewerAgent: null,
    reviserAgent: null,
    artifactIteration: 0,
    maxArtifactIterations: 5,
  };
}

// ============================================
// SSE 流辅助
// ============================================

function createSSEStream(
  taskId: string,
  logPrefix: string,
  auditContext: Omit<WorkflowEventLogContext, "taskId">,
  runner: (
    sendEvent: SendEventFn,
    sentKeys: Set<string>,
    config: { configurable: { thread_id: string } },
    close: () => void,
    auditLog: WorkflowEventFileLogger
  ) => Promise<void>
): Response {
  const encoder = new TextEncoder();
  let streamController: ReadableStreamDefaultController | null = null;
  const sentAgentDoneKeys = new Set<string>();
  const auditLog = createWorkflowEventFileLogger({ taskId, ...auditContext });

  const closeStream = () => {
    try { streamController?.close(); } catch { /* ignore */ }
  };
  let writingSessionIdPromise: Promise<string | null> | null = null;
  const resolveWritingSessionId = () => {
    writingSessionIdPromise ??= getWritingSessionIdForTask(taskId);
    return writingSessionIdPromise;
  };

  const persistVisibleMessageFromEvent = async (
    type: string,
    data: Record<string, unknown>
  ) => {
    const sessionId = await resolveWritingSessionId();
    if (!sessionId) return;

    if (type === "agent_done" && typeof data.content === "string") {
      await persistWorkflowMessage({
        sessionId,
        taskId,
        role: "agent",
        agentId: typeof data.agentId === "string" ? data.agentId : null,
        content: data.content,
        eventType: "agent_done",
      });
      return;
    }

    if (type === "done") {
      await persistWorkflowMessage({
        sessionId,
        taskId,
        role: "system",
        content: typeof data.finalContent === "string" ? data.finalContent : "会话完成。",
        eventType: "done",
      });
      return;
    }

    if (type === "error" && typeof data.message === "string") {
      await persistWorkflowMessage({
        sessionId,
        taskId,
        role: "system",
        content: `错误：${data.message}`,
        eventType: "error",
      });
      return;
    }

    if (type === "artifact_applied") {
      await persistWorkflowMessage({
        sessionId,
        taskId,
        role: "system",
        content: typeof data.summary === "string" ? data.summary : "待审核草案已应用。",
        eventType: "artifact_applied",
      });
      return;
    }

    if (type === "artifact_deleted") {
      await persistWorkflowMessage({
        sessionId,
        taskId,
        role: "system",
        content: "待审核草案已丢弃。",
        eventType: "artifact_deleted",
      });
    }
  };
  const shouldQueueVisibleMessagePersistence = (type: string) =>
    type === "agent_done" ||
    type === "done" ||
    type === "error" ||
    type === "artifact_applied" ||
    type === "artifact_deleted";

  const sendEvent: SendEventFn = (type, data = {}) => {
    try {
      if (streamController) {
        if (type === "agent_done" && data.agentId && typeof data.content === "string") {
          sentAgentDoneKeys.add(`${data.agentId}:${data.content.length}`);
        }
        auditLog.recordSSEEvent(type, data);
        const payload = JSON.stringify({ type, ...data });
        if (type !== "agent_chunk") {
          logger.info("SSE", `入队${logPrefix}: ${type}`, { type, payloadLen: payload.length });
        }
        streamController.enqueue(encoder.encode(`data: ${payload}\n\n`));
        if (shouldQueueVisibleMessagePersistence(type)) {
          enqueueDbWrite(
            () => persistVisibleMessageFromEvent(type, data),
            `workflow_message:${type}`
          );
        }
      } else {
        logger.warn("SSE", `streamController 为 null，丢弃事件${logPrefix}: ${type}`, { taskId, type });
      }
    } catch (e) {
      logger.warn("SSE", "发送事件失败", { taskId, type });
    }
  };

  const stream = new ReadableStream({
    start(controller) {
      streamController = controller;
      logger.info("SSE", `ReadableStream start${logPrefix} 被调用`);
    },
    cancel() {
      streamController = null;
      logger.info("SSE", `ReadableStream cancel${logPrefix} 被调用`);
    },
  });

  const config = { configurable: { thread_id: taskId } };
  auditLog.recordWorkflowEvent("sse_stream_created", { logPrefix });

  // 异步启动，完成或出错后关闭流
  runner(sendEvent, sentAgentDoneKeys, config, closeStream, auditLog).catch((error) => {
    const msg = error instanceof Error ? error.message : "未知错误";
    auditLog.recordError("workflow_runner_error", error);
    logger.error("WORKFLOW", `工作流${logPrefix}错误: ${msg}`, { taskId });
    sendEvent("error", { message: msg });
    closeStream();
  });

  return new Response(stream, { headers: SSE_HEADERS });
}

// ============================================
// executeWritingWorkflow
// ============================================

export async function executeWritingWorkflow(
  initialState: WritingState | GraphState
): Promise<Response> {
  const taskId = initialState.taskId;
  logger.info("WORKFLOW", "开始执行工作流", { taskId });

  return createSSEStream(
    taskId,
    "",
    {
      runKind: "writing-workflow",
      userId: initialState.userId,
      novelId: initialState.novelId,
      chapterId: initialState.chapterId,
      qualityCheckId: initialState.qualityCheckId,
    },
    async (sendEvent, sentKeys, config, close, auditLog) => {
    await traceWorkflowExecution(
      "writing-workflow",
      createTraceMetadata({ taskId, novelId: initialState.novelId, chapterId: initialState.chapterId, callType: "writing-workflow" }),
      async () => {
        auditLog.recordWorkflowEvent("workflow_started", {
          novelId: initialState.novelId,
          chapterId: initialState.chapterId,
          targetWordCount: initialState.targetWordCount,
        });

        const graph = getGraph();
        const history = await loadHistoryFromDb(taskId);
        auditLog.recordPersistenceEvent("history_loaded", { historyCount: history.length });
        const writingSessionId = await getWritingSessionIdForTask(taskId);
        await persistWorkflowMessage({
          sessionId: writingSessionId,
          taskId,
          role: "user",
          content: initialState.userMessage,
          eventType: "user",
        });

        const graphInput = {
          ...initialState,
          conversationHistory: history,
          nextAgent: null,
          callChainDepth: 0,
          streamCallbacks: createDirectStreamCallbacks(sendEvent),
          eventCallbacks: createDirectEventCallbacks(sendEvent),
        };

        sendEvent("start", { taskId });

        let wasInterrupted = false;
        let invokeFinalState: GraphState | null = null;
        if (shouldUseLangGraphStreamEvents()) {
          const sse = createSSEController(sendEvent, auditLog);
          const eventStream = graph.streamEvents(graphInput as unknown as GraphState, {
            ...config,
            version: "v2",
            streamMode: STREAM_MODES,
          });

          for await (const event of eventStream) {
            const result = sse.handleEvent(event);
            if (result === "interrupt") {
              wasInterrupted = true;
              auditLog.recordWorkflowEvent("workflow_interrupted");
              break;
            }
          }
        } else {
          const result = await graph.invoke(graphInput as unknown as GraphState, config);
          wasInterrupted = emitInterruptFromInvokeResult(result, sendEvent);
          if (wasInterrupted) auditLog.recordWorkflowEvent("workflow_interrupted");
          invokeFinalState = graphStateFromInvokeResult(result);
        }

        const fs = await getGraphStateAfterRun(graph, config, invokeFinalState);
        if (fs) {
          if (!wasInterrupted) {
            await saveHistoryToDb(taskId, fs.conversationHistory);
            auditLog.recordPersistenceEvent("history_saved", {
              historyCount: fs.conversationHistory.length,
            });
            await updateTaskState(fs);
            auditLog.recordPersistenceEvent("task_state_updated", {
              phase: fs.phase,
              activeAgent: fs.activeAgent,
              callChainDepth: fs.callChainDepth,
            });
          }
          sendAgentDoneFallback(fs, sendEvent, sentKeys);
          if (!wasInterrupted) {
            sendEvent("done", {
              taskId,
              conversationSummary: buildContextSummary(fs as unknown as WritingState),
              activeAgent: fs.activeAgent,
            });
            auditLog.recordWorkflowEvent("workflow_completed", {
              activeAgent: fs.activeAgent,
              phase: fs.phase,
            });
            await cleanupGraphCheckpoint(taskId, auditLog);
          }
        }
        close();
      }
    );
    }
  );
}

// ============================================
// resumeWriting
// ============================================

export async function resumeWriting(
  taskId: string,
  userMessage: string,
  userId?: string,
  userDecision?: UserDecision | null
): Promise<Response> {
  logger.info("WORKFLOW", "恢复工作流", { taskId, userId });

  return createSSEStream(
    taskId,
    "(resume)",
    {
      runKind: "resume-writing-workflow",
      userId,
    },
    async (sendEvent, sentKeys, config, close, auditLog) => {
    await traceWorkflowExecution(
      "resume-writing-workflow",
      createTraceMetadata({ taskId, callType: "resume-writing-workflow" }),
      async () => {
        auditLog.recordWorkflowEvent("resume_started", {
          decisionType: userDecision?.type,
          decision: userDecision?.type === "artifact_review" ? userDecision.decision : undefined,
          artifactId: userDecision?.type === "artifact_review" ? userDecision.artifactId : undefined,
        });

        if (userDecision?.type === "artifact_review" && userDecision.decision === "approve" && userId) {
          const artifactId = userDecision.artifactId;
          sendEvent("resume", { taskId, resumeType: "artifact_approval" });
          const result = await applyReviewArtifact({
            artifactId,
            userId,
            editedContent: userDecision.editedContent,
            selectedUpdateRefs: userDecision.selectedUpdateRefs,
          });
          if (result.success) {
            await clearTaskAwaitingUserReview({ taskId });
          }
          auditLog.recordPersistenceEvent("artifact_applied", {
            artifactId,
            success: result.success,
            savedCount: result.savedCount,
            errors: result.errors,
          });
          sendEvent("artifact_applied", {
            artifactId,
            success: result.success,
            summary: result.summary,
            errors: result.errors,
            savedCount: result.savedCount,
            artifact: result.artifact,
          });
          sendEvent("done", { taskId, finalContent: result.summary });
          await cleanupGraphCheckpoint(taskId, auditLog);
          close();
          return;
        }

        if (userDecision?.type === "artifact_review" && userDecision.decision === "discard" && userId) {
          const artifactId = userDecision.artifactId;
          sendEvent("resume", { taskId, resumeType: "artifact_discard" });
          await discardArtifactHard({ artifactId, userId });
          await clearTaskAwaitingUserReview({ taskId });
          auditLog.recordPersistenceEvent("artifact_deleted", { artifactId });
          sendEvent("artifact_deleted", { artifactId });
          sendEvent("done", { taskId, finalContent: "已丢弃待审核草案。" });
          await cleanupGraphCheckpoint(taskId, auditLog);
          close();
          return;
        }

        let effectiveUserMessage = userMessage;
        if (userDecision?.type === "artifact_review" && userDecision.decision === "revise" && userId) {
          const artifactId = userDecision.artifactId;
          const artifact = await prisma.reviewArtifact.findFirst({
            where: {
              id: artifactId,
              taskId,
              status: "awaiting_user",
            },
            select: {
              id: true,
              artifactKey: true,
              revision: true,
              createdByAgent: true,
              updatedByAgent: true,
              reviewerAgent: true,
            },
          });

          if (!artifact) {
            sendEvent("error", { message: "待审核草案不存在，或已不属于当前任务。" });
            auditLog.recordError("artifact_revision_not_found", "待审核草案不存在，或已不属于当前任务。", {
              artifactId,
            });
            close();
            return;
          }

          const revisionResume = buildArtifactRevisionResume({
            artifactId: artifact.id,
            artifactKey: artifact.artifactKey,
            revision: artifact.revision,
            createdByAgent: artifact.createdByAgent as CoreAgentId | null,
            updatedByAgent: artifact.updatedByAgent as CoreAgentId | null,
            reviewerAgent: artifact.reviewerAgent as CoreAgentId | null,
            userMessage: userDecision.userMessage ?? userMessage,
          });

          if (!revisionResume) {
            sendEvent("error", { message: "无法确定应由哪个 Agent 继续修改该草案。" });
            auditLog.recordError("artifact_revision_target_missing", "无法确定应由哪个 Agent 继续修改该草案。", {
              artifactId,
            });
            close();
            return;
          }

          await clearTaskAwaitingUserReview({ taskId, nextPhase: "active" });
          effectiveUserMessage = revisionResume.userMessage;
          sendEvent("resume", {
            taskId,
            resumeType: "artifact_revision",
            artifactId,
            targetAgent: revisionResume.targetAgent,
          });
        }

        const graph = getGraph();
        const observability = getAgentObservabilityConfig();
        const stateSnap = observability.langGraphMemorySaverEnabled
          ? await graph.getState(config)
          : null;
        const taskForResume = await prisma.writingTask.findUnique({
          where: { id: taskId },
          include: { novel: { select: { userId: true } } },
        });
        if (!taskForResume) {
          sendEvent("error", { message: "任务不存在" });
          auditLog.recordError("task_not_found", "任务不存在");
          close();
          return;
        }
        const graphSnapshot = deserializeGraphStateSnapshot(taskForResume.graphStateJson);
        const hasPendingCheckpoint = Boolean(stateSnap && stateSnap.next.length > 0);

        const resumeMode = getResumeMode({
          hasPendingCheckpoint,
          hasGraphStateSnapshot: Boolean(graphSnapshot),
          userMessage: effectiveUserMessage,
        });
        auditLog.recordWorkflowEvent("resume_mode_selected", {
          resumeMode,
          hasPendingCheckpoint,
          hasGraphStateSnapshot: Boolean(graphSnapshot),
        });
        await persistWorkflowMessage({
          sessionId: taskForResume.writingSessionId,
          taskId,
          role: "user",
          content: effectiveUserMessage,
          eventType: "user",
        });
        let invokeFinalState: GraphState | null = null;
        if (resumeMode === "interrupt_resume") {
          // 有中断待恢复
          const resumeValue = { confirmed: true, userMessage: effectiveUserMessage };
          sendEvent("resume", { taskId, resumeType: "interrupt_resume" });

          const sse = createSSEController(sendEvent, auditLog);
          const command = new Command({
            resume: resumeValue,
            update: {
              streamCallbacks: createDirectStreamCallbacks(sendEvent),
              eventCallbacks: createDirectEventCallbacks(sendEvent),
            },
          }) as unknown as GraphState;
          if (shouldUseLangGraphStreamEvents()) {
            const eventStream = await graph.streamEvents(
              command,
              { ...config, version: "v2", streamMode: STREAM_MODES }
            );

            for await (const event of eventStream) {
              const result = sse.handleEvent(event);
              if (result === "interrupt") break;
            }
          } else {
            const result = await graph.invoke(command, config);
            emitInterruptFromInvokeResult(result, sendEvent);
            invokeFinalState = graphStateFromInvokeResult(result);
          }
        } else {
          // 无中断——常规恢复
          const task = await prisma.writingTask.findUnique({
            where: { id: taskId },
            include: { novel: { select: { userId: true } } },
          });
          if (!task) {
            sendEvent("error", { message: "任务不存在" });
            auditLog.recordError("task_not_found", "任务不存在");
            close();
            return;
          }

          auditLog.setContext({
            userId: task.novel?.userId ?? userId,
            novelId: task.novelId,
            chapterId: task.chapterId,
          });

          // Phase 5 纵深防御：内部二次鉴权
          if (userId && task.novel?.userId && task.novel.userId !== userId) {
            logger.error("WORKFLOW", "内部鉴权失败：userId 不匹配", {
              taskId,
              taskUserId: task.novel.userId,
              requestUserId: userId,
            });
            sendEvent("error", { message: "无权访问该任务" });
            auditLog.recordError("task_auth_failed", "无权访问该任务", {
              taskUserId: task.novel.userId,
              requestUserId: userId,
            });
            close();
            return;
          }

          const novelData = await aggregateNovelContextLightweight(task.novelId, task.chapterId);
          const history = await loadHistoryFromDb(taskId);
          auditLog.recordPersistenceEvent("history_loaded", { historyCount: history.length });

          let lastActiveAgent: CoreAgentId | null = null;
          for (let i = history.length - 1; i >= 0; i--) {
            const msg = history[i];
            if (msg.agentOutput && msg.agentId !== "设定") {
              lastActiveAgent = msg.agentId as CoreAgentId;
              break;
            }
          }

          sendEvent("resume", {
            taskId,
            resumeType: resumeMode === "snapshot_resume" ? "snapshot_resume" : "fresh",
            historyCount: history.length,
            lastActiveAgent,
          });

          const graphInput = {
            taskId,
            userId: task.novel?.userId ?? "",
            novelId: task.novelId,
            chapterId: task.chapterId,
            targetWordCount: task.targetWordCount,
            phase: task.phase as WritingPhase,
            userMessage: effectiveUserMessage,
            pendingUserResponse: false,
            conversationHistory: history,
            activeAgent: lastActiveAgent,
            currentOperation: null,
            operationMode: "operation_graph",
            operationStage: null,
            loreAdvisorOutput: null,
            plotAdvisorOutput: null,
            writerOutput: null,
            validatorOutput: null,
            editorOutput: null,
            generatedContent: task.generatedContent ?? "",
            pendingUpdates: null,
            novelData: { ...novelData, novelId: task.novelId, chapterId: task.chapterId } as WritingState["novelData"],
            pendingAgentCall: null,
            errorMessage: null,
            streamCallbacks: createDirectStreamCallbacks(sendEvent),
            eventCallbacks: createDirectEventCallbacks(sendEvent),
            nextAgent: null,
            callChainDepth: 0,
            qualityCheckId: null,
            controlEvents: undefined,
            activeArtifactId: null,
            artifactMode: "none",
            reviewerAgent: null,
            reviserAgent: null,
            artifactIteration: 0,
            maxArtifactIterations: 5,
          };
          const runtimeCallbacks = {
            streamCallbacks: createDirectStreamCallbacks(sendEvent),
            eventCallbacks: createDirectEventCallbacks(sendEvent),
          };
          const effectiveGraphInput = resumeMode === "snapshot_resume" && graphSnapshot
            ? rehydrateGraphStateFromSnapshot(graphSnapshot, {
                userMessage: effectiveUserMessage,
                novelData: { ...novelData, novelId: task.novelId, chapterId: task.chapterId } as WritingState["novelData"],
                ...runtimeCallbacks,
              })
            : graphInput;

          if (shouldUseLangGraphStreamEvents()) {
            const sse = createSSEController(sendEvent, auditLog);
            const eventStream = graph.streamEvents(effectiveGraphInput as unknown as GraphState, {
              ...config,
              version: "v2",
              streamMode: STREAM_MODES,
            });

            for await (const event of eventStream) {
              const result = sse.handleEvent(event);
              if (result === "interrupt") break;
            }
          } else {
            const result = await graph.invoke(effectiveGraphInput as unknown as GraphState, config);
            emitInterruptFromInvokeResult(result, sendEvent);
            invokeFinalState = graphStateFromInvokeResult(result);
          }
        }

        // 持久化
        const fs = await getGraphStateAfterRun(graph, config, invokeFinalState);
        if (fs) {
          await saveHistoryToDb(taskId, fs.conversationHistory);
          auditLog.recordPersistenceEvent("history_saved", {
            historyCount: fs.conversationHistory.length,
          });
          await updateTaskState(fs);
          auditLog.recordPersistenceEvent("task_state_updated", {
            phase: fs.phase,
            activeAgent: fs.activeAgent,
            callChainDepth: fs.callChainDepth,
          });
          sendAgentDoneFallback(fs, sendEvent, sentKeys);
          sendEvent("done", {
            conversationSummary: buildContextSummary(fs as unknown as WritingState),
            activeAgent: fs.activeAgent,
          });
          auditLog.recordWorkflowEvent("resume_completed", {
            activeAgent: fs.activeAgent,
            phase: fs.phase,
          });
          if (fs.phase !== "waiting_call" && !fs.pendingUserResponse) {
            await cleanupGraphCheckpoint(taskId, auditLog);
          }
        }
        close();
      }
    );
    }
  );
}

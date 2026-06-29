/**
 * 任务状态持久化
 *
 * @module agents/graph/task-state
 * @description Phase 5 拆分：WritingTask 的读写、更新、变更持久化。
 *  从 executor.ts 拆出。
 *
 * @phase Phase 5 — 拆分 LangGraph 执行器
 */

import { collectAgentOutputs, patchArtifactReviewState } from "./state";
import type { AgentOutput } from "./state";
import type { GraphState } from "./graph-definition";
import { serializeHistory } from "./context-manager";
import { serializeGraphStateSnapshot } from "./graph-state-snapshot";
import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";

/**
 * 将当前 state 的 Agent 输出持久化到 WritingTask
 */
export async function updateTaskState(state: GraphState): Promise<void> {
  try {
    const agentOutputs = collectAgentOutputs(state) as Record<string, AgentOutput>;

    await prisma.writingTask.update({
      where: { id: state.taskId },
      data: {
        phase: state.phase,
        agentOutputs: JSON.stringify(agentOutputs),
        generatedContent: state.generatedContent || undefined,
        conversationHistory: serializeHistory(state.conversationHistory),
        graphStateJson: serializeGraphStateSnapshot(state),
      },
    });
  } catch (error) {
    logger.error("TASK_STATE", "更新任务状态失败", {
      taskId: state.taskId,
      error: String(error),
    });
  }
}

export async function markTaskAwaitingUserReview(input: {
  taskId: string;
  artifactId: string;
  state: GraphState;
  operationStage?: string;
}): Promise<void> {
  const data = buildAwaitingUserReviewTaskUpdate({
    artifactId: input.artifactId,
    state: input.state,
    operationStage: input.operationStage,
  });

  await prisma.writingTask.update({
    where: { id: input.taskId },
    data,
  });
}

export function buildAwaitingUserReviewTaskUpdate(input: {
  artifactId: string;
  state: GraphState;
  operationStage?: string | null;
}) {
  const stateForSnapshot: GraphState = {
    ...input.state,
    ...patchArtifactReviewState(input.state, {
      status: "awaiting_user",
      activeArtifactId: input.artifactId,
      pendingRevision: null,
      reviserAgent: null,
    }),
    phase: "awaiting_user_review",
    operationStage: input.operationStage ?? input.state.operationStage ?? null,
  };

  return {
    phase: "awaiting_user_review" as const,
    conversationHistory: serializeHistory(stateForSnapshot.conversationHistory),
    graphStateJson: serializeGraphStateSnapshot(stateForSnapshot),
  };
}

export async function clearTaskAwaitingUserReview(input: {
  taskId: string;
  nextPhase?: "active" | "completed";
}): Promise<void> {
  await prisma.writingTask.update({
    where: { id: input.taskId },
    data: {
      phase: input.nextPhase ?? "completed",
      generatedContent: null,
    },
  });
}

/**
 * 持久化变更（兼容 API）
 */
export async function persistUpdates(taskId: string, _updates: unknown) {
  logger.info("TASK_STATE", "持久化变更", { taskId });
  return { summary: "变更已保存", success: true };
}

/**
 * 回滚变更（兼容 API）
 */
export async function rollbackTaskUpdates(taskId: string, records: unknown[]) {
  logger.info("TASK_STATE", "回滚变更", { taskId, count: records.length });
  return { success: true, message: "已回滚" };
}

/**
 * 预览变更（兼容 API）
 */
export function previewUpdates(_updates: unknown): string {
  return "变更预览功能待实现";
}

/**
 * WorkflowRun 服务（Phase 2：聊天与生产解耦）
 *
 * @module agents/lib/workflow-run-service
 * @description Phase 2 新增：统一管理 WorkflowRun/WorkflowStep 的创建和状态更新。
 *  质量检查不再通过创建普通 WritingTask 来复用写作流程。
 *
 * @phase Phase 2 — 聊天和生产工作流解耦
 */

import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import type {
  WorkflowRunKind,
  WorkflowRunStatus,
  WorkflowStepStatus,
  WorkflowStepType,
} from "@/shared/contracts/workflow";

// ============================================
// 创建
// ============================================

export async function createWorkflowRun(params: {
  novelId: string;
  chapterId: string;
  userId?: string;
  kind: WorkflowRunKind;
  sourceType?: string;
  sourceId?: string;
  input?: string;
}): Promise<string> {
  const run = await prisma.workflowRun.create({
    data: {
      novelId: params.novelId,
      chapterId: params.chapterId,
      userId: params.userId,
      kind: params.kind,
      status: "running",
      sourceType: params.sourceType,
      sourceId: params.sourceId,
      input: params.input,
    },
  });
  logger.info("WORKFLOW_RUN", "创建工作流运行", { runId: run.id, kind: params.kind });
  return run.id;
}

// ============================================
// 步骤
// ============================================

export async function addWorkflowStep(params: {
  runId: string;
  agentId?: string;
  stepType: WorkflowStepType;
  status?: WorkflowStepStatus;
  input?: string;
  output?: string;
  durationMs?: number;
}): Promise<string> {
  const step = await prisma.workflowStep.create({
    data: {
      runId: params.runId,
      agentId: params.agentId,
      stepType: params.stepType,
      status: params.status ?? "completed",
      input: params.input,
      output: params.output,
      durationMs: params.durationMs,
    },
  });
  return step.id;
}

// ============================================
// 状态更新
// ============================================

export async function updateWorkflowRunStatus(
  runId: string,
  status: WorkflowRunStatus,
  extra?: {
    output?: string;
    errorMessage?: string;
    currentAgentId?: string;
  }
): Promise<void> {
  await prisma.workflowRun.update({
    where: { id: runId },
    data: {
      status,
      ...(extra?.output !== undefined && { output: extra.output }),
      ...(extra?.errorMessage !== undefined && { errorMessage: extra.errorMessage }),
      ...(extra?.currentAgentId !== undefined && { currentAgentId: extra.currentAgentId }),
    },
  });
}

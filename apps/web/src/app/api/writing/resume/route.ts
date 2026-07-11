/**
 * 智能写作继续 API（基于 LangGraph）
 *
 * @module app/api/writing/resume/route
 * @description 继续被中断的智能写作会话
 *
 * ## 迁移说明
 * 此文件替代原来的 continue/route.ts
 * 使用 LangGraph 工作流进行 Agent 编排
 */

import { NextRequest } from "next/server";
import { resumeWriting } from "@/agents/graph";

export const dynamic = "force-dynamic";
import { logger } from "@/shared/lib/logger";
import { printMemorySnapshot } from "@/shared/lib/monitoring";
import { getSession } from "@/shared/lib/auth";
import { prisma } from "@/shared/db/prisma";
import { authorizeWritingTask, authErrorResponse } from "@/agents/lib/task-auth";
import { createApiErrorResponse, createZodErrorResponse } from "@/shared/contracts/api-error";
import { normalizeResumeDecision, ResumeWritingRequestSchema } from "@/shared/contracts/user-decision";
import { validateResumeSessionBinding } from "./session-binding";

/**
 * POST /api/writing/resume
 *
 * 继续被中断的智能写作会话
 *
 * Body:
 * - taskId: 写作任务 ID（必需）
 * - userMessage: 用户消息（必需）
 *
 * ## Phase 1.1 安全加固
 * - 新增 getSession() 登录校验 → 未登录返回 401
 * - 新增 authorizeWritingTask() 任务归属校验 → 越权返回 403
 * - 历史 userId 为空的数据渐进式兼容（允许访问 + 记录警告）
 */
export async function POST(request: NextRequest) {
  const requestId = `resume-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  try {
    const rawBody = await request.json();
    const parsedBody = ResumeWritingRequestSchema.safeParse(rawBody);
    if (!parsedBody.success) {
      return createZodErrorResponse(parsedBody.error);
    }

    const body = parsedBody.data;
    const { taskId, writingSessionId, userMessage, decision, artifactId, userDecision } = body;
    const normalizedDecision = normalizeResumeDecision({
      userDecision,
      decision,
      artifactId,
      userMessage,
    });

    logger.info("API", "收到继续写作请求", { requestId, taskId });
    printMemorySnapshot(`[API] 继续写作请求 ${requestId}`);

    if (!taskId || !normalizedDecision) {
      logger.warn("API", "缺少必需参数", { requestId });
      return createApiErrorResponse("缺少写作任务或有效用户决策", { status: 400 });
    }

    // Phase 1.1: 登录校验
    const session = await getSession();
    if (!session) {
      logger.warn("API", "未登录用户尝试继续写作", { requestId, taskId });
      return authErrorResponse("未登录", 401);
    }

    // Phase 1.1: 任务归属校验
    const auth = await authorizeWritingTask(taskId, session.userId);
    if (!auth.authorized) {
      return authErrorResponse(auth.reason ?? "无权访问该任务", 403);
    }

    if (writingSessionId) {
      const task = await prisma.writingTask.findUnique({
        where: { id: taskId },
        select: {
          writingSessionId: true,
        },
      });
      if (!task) return authErrorResponse("任务不存在", 403);

      const bindingError = validateResumeSessionBinding({
        requestedWritingSessionId: writingSessionId,
        taskWritingSessionId: task.writingSessionId,
      });
      if (bindingError) return authErrorResponse(bindingError, 403);
    }

    return await resumeWriting(
      taskId,
      normalizedDecision.type === "continue_chat" ? normalizedDecision.userMessage : "",
      session.userId,
      normalizedDecision
    );
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : "服务器内部错误";
    logger.error("API", `继续写作请求错误: ${errorMsg}`, {
      requestId,
      stack: error instanceof Error ? error.stack : undefined,
    });
    printMemorySnapshot(`[API] 继续写作错误 ${requestId}`);
    return createApiErrorResponse(errorMsg, { status: 500 });
  }
}

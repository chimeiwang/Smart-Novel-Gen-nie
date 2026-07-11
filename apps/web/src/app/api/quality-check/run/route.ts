/**
 * 质量检查运行 API（Phase 7：服务端驱动）
 *
 * @module app/api/quality-check/run/route
 * @description 服务端触发质量检查，不依赖前端 SSE。
 *
 * ## P0 安全加固
 * - 无 taskId 时：校验 check.chapter.novel.userId 归属
 * - 有 taskId 时：校验 task 归属 + task.chapterId === check.chapterId（防跨章越权）
 *
 * @phase Phase 7 — 质量检查独立 API
 */

import { NextRequest } from "next/server";
import { getSession } from "@/shared/lib/auth";
import { authorizeWritingTask, authErrorResponse } from "@/agents/lib/task-auth";
import { markCheckFailed, markCheckRunning, saveQualityCheckReport } from "@/agents/lib/quality-check-service";
import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import { createBaseGraphState, createWorkflowTask } from "@/agents/graph";
import { QUALITY_CHECK_MESSAGE_MAP, RunQualityCheckSchema } from "@/shared/contracts/quality-check";
import { aggregateNovelContextLightweight } from "@/shared/lib/context-aggregator";
import { validatorNode } from "@/agents/graph/nodes/validator-node";
import type { WritingState } from "@/agents/graph/state";

export const dynamic = "force-dynamic";

async function markTaskError(taskId: string | null, error: string) {
  if (!taskId) return;
  await prisma.writingTask.update({
    where: { id: taskId },
    data: { phase: "error", agentOutputs: JSON.stringify({ error }) },
  }).catch((e) => logger.warn("QUALITY_CHECK_API", "标记质量检查任务失败状态失败", { error: String(e), taskId }));
}

export async function POST(request: NextRequest) {
  const requestId = `qc-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  try {
    const body = await request.json();

    // P1-4：Zod 入口校验
    const parsed = RunQualityCheckSchema.safeParse(body);
    if (!parsed.success) {
      return new Response(JSON.stringify({ error: "参数校验失败", details: parsed.error.issues }), { status: 400 });
    }
    const { checkId, taskId, message: customMessage } = parsed.data;

    // 1. 鉴权
    const session = await getSession();
    if (!session) return authErrorResponse("未登录", 401);

    // 2. 查询检查项（含归属链路）
    const check = await prisma.chapterQualityCheck.findUnique({
      where: { id: checkId },
      include: {
        chapter: {
          select: {
            id: true,
            novelId: true,
            content: true,
            novel: { select: { userId: true } },
          },
        },
      },
    });
    if (!check) {
      return new Response(JSON.stringify({ error: "检查项不存在" }), { status: 404 });
    }

    if (check.type !== "consistency") {
      return new Response(JSON.stringify({ error: "当前只支持一致性终检；设定同步、商业性和技法评审请在写作草案流程中处理。" }), { status: 400 });
    }

    // 3. P0：校验 check 归属 — 始终比对 novel.userId
    const novelUserId = check.chapter.novel.userId;
    if (novelUserId && novelUserId !== session.userId) {
      logger.warn("QUALITY_CHECK_API", "越权：检查项不属于当前用户", {
        checkId, checkNovelId: check.chapter.novelId, novelUserId, requestUserId: session.userId,
      });
      return authErrorResponse("无权访问该检查项", 403);
    }

    // 4. 有 taskId → 额外校验 task 归属 + task.chapterId === check.chapterId
    if (taskId) {
      const auth = await authorizeWritingTask(taskId, session.userId);
      if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问", 403);

      // P0：防止用自己 taskId + 别人 checkId 跨章越权
      if (auth.task && auth.task.chapterId !== check.chapterId) {
        logger.warn("QUALITY_CHECK_API", "越权：task.chapterId 与 check.chapterId 不一致", {
          checkId, taskId, taskChapterId: auth.task.chapterId, checkChapterId: check.chapterId,
        });
        return authErrorResponse("任务与检查项不匹配", 403);
      }
    }

    // 5. 消息
    const message = customMessage || QUALITY_CHECK_MESSAGE_MAP[check.type as keyof typeof QUALITY_CHECK_MESSAGE_MAP];
    if (!message) {
      return new Response(JSON.stringify({ error: `不支持的检查类型: ${check.type}` }), { status: 400 });
    }

    // 6. 标记 running
    await markCheckRunning(checkId);
    logger.info("QUALITY_CHECK_API", "启动质量检查", { requestId, checkId, checkType: check.type });

    let taskIdForRun: string | null = null;
    try {
      taskIdForRun = await createWorkflowTask({
        novelId: check.chapter.novelId,
        chapterId: check.chapterId,
        targetWordCount: 0,
        userMessage: message,
        userId: session.userId,
        qualityCheckId: checkId,
        selectedAgents: ["校验"],
      });

      const novelData = await aggregateNovelContextLightweight(check.chapter.novelId, check.chapterId);
      const state = createBaseGraphState({
        taskId: taskIdForRun,
        userId: session.userId,
        novelId: check.chapter.novelId,
        chapterId: check.chapterId,
        targetWordCount: 0,
        phase: "active",
        userMessage: message,
        activeAgent: "校验",
        novelData: { ...novelData, novelId: check.chapter.novelId, chapterId: check.chapterId } as WritingState["novelData"],
        qualityCheckId: checkId,
      });

      const result = await validatorNode(state);
      const report = result.validatorOutput?.content.trim();
      if (result.errorMessage || !report) {
        throw new Error(result.errorMessage || "校验 Agent 未返回报告");
      }

      const saved = await saveQualityCheckReport({ checkId, result: report });
      if (!saved.success) {
        throw new Error(saved.error || "一致性终检报告保存失败");
      }

      await prisma.writingTask.update({
        where: { id: taskIdForRun },
        data: {
          phase: "completed",
          agentOutputs: JSON.stringify({ 校验: result.validatorOutput }),
          conversationHistory: JSON.stringify([
            { role: "user", content: message },
            { role: "assistant", agentId: "校验", agentOutput: result.validatorOutput },
          ]),
        },
      });

      return Response.json({ ok: true, checkId, taskId: taskIdForRun });
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      await markCheckFailed(checkId, messageText);
      await markTaskError(taskIdForRun, messageText);
      return new Response(JSON.stringify({ error: messageText }), { status: 500 });
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : "服务器内部错误";
    logger.error("QUALITY_CHECK_API", `质量检查请求错误: ${errorMsg}`, { requestId });
    return new Response(JSON.stringify({ error: errorMsg }), { status: 500 });
  }
}

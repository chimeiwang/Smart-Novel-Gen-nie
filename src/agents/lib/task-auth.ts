/**
 * 任务鉴权服务
 *
 * @module agents/lib/task-auth
 * @description 统一校验 WritingTask 和 Novel 的用户归属，防止越权访问。
 *
 * ## 安全策略（v6.1 P0 修复）
 * - 有 userId 的数据严格校验归属
 * - novel.userId 为空时默认拒绝（除本地迁移模式外）
 * - 本地开发可通过 ALLOW_LEGACY_NULL_USERID=true 临时放行，用于跑 backfill 前的过渡期
 *
 * @phase Phase 1.1 — 安全边界止血
 */

import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";

/** 本地迁移兼容开关：仅在跑 backfill 脚本前临时使用 */
const ALLOW_LEGACY =
  process.env.ALLOW_LEGACY_NULL_USERID === "true" &&
  process.env.NODE_ENV !== "production";

export interface AuthResult {
  authorized: boolean;
  task?: {
    id: string;
    novelId: string;
    chapterId: string;
    phase: string;
    novel: { userId: string | null };
  };
  reason?: string;
  isLegacyData?: boolean;
}

export interface SessionAuthResult {
  authorized: boolean;
  session?: {
    id: string;
    novelId: string;
    chapterId: string;
    novel: { userId: string | null };
  };
  reason?: string;
  isLegacyData?: boolean;
}

/**
 * 校验 WritingTask 是否属于当前用户。
 *
 * P0 修复：novel.userId 为空时默认拒绝。
 * 生产环境严禁放行；本地开发可通过 ALLOW_LEGACY_NULL_USERID=true 临时兼容。
 */
export async function authorizeWritingTask(
  taskId: string,
  userId: string
): Promise<AuthResult> {
  const task = await prisma.writingTask.findUnique({
    where: { id: taskId },
    include: { novel: { select: { userId: true } } },
  });

  if (!task) {
    logger.warn("TASK_AUTH", "任务不存在", { taskId, userId });
    return { authorized: false, reason: "任务不存在" };
  }

  // P0：novel.userId 为空 → 拒绝，引导跑 backfill
  if (task.novel.userId === null || task.novel.userId === undefined) {
    if (ALLOW_LEGACY) {
      logger.warn("TASK_AUTH", "历史数据无 userId，本地兼容模式放行", { taskId, novelId: task.novelId, userId });
      return { authorized: true, task, isLegacyData: true };
    }
    logger.error("TASK_AUTH", "novel.userId 为空，拒绝访问。请执行 scripts/backfill-novel-userid.ts", {
      taskId, novelId: task.novelId, userId,
    });
    return { authorized: false, reason: "数据异常：小说缺少归属信息，请联系管理员执行数据回填" };
  }

  if (task.novel.userId !== userId) {
    logger.warn("TASK_AUTH", "越权访问被拒绝", { taskId, novelId: task.novelId, taskUserId: task.novel.userId, requestUserId: userId });
    return { authorized: false, reason: "无权访问该任务" };
  }

  return { authorized: true, task };
}

/**
 * 校验 Novel 是否属于当前用户。
 *
 * P0 修复：novel.userId 为空时默认拒绝。
 */
export async function authorizeNovel(
  novelId: string,
  userId: string
): Promise<AuthResult> {
  const novel = await prisma.novel.findUnique({
    where: { id: novelId },
    select: { userId: true },
  });

  if (!novel) {
    logger.warn("TASK_AUTH", "小说不存在", { novelId, userId });
    return { authorized: false, reason: "小说不存在" };
  }

  // P0：userId 为空 → 拒绝
  if (novel.userId === null || novel.userId === undefined) {
    if (ALLOW_LEGACY) {
      logger.warn("TASK_AUTH", "历史小说无 userId，本地兼容模式放行", { novelId, userId });
      return { authorized: true, isLegacyData: true };
    }
    logger.error("TASK_AUTH", "novel.userId 为空，拒绝访问", { novelId, userId });
    return { authorized: false, reason: "数据异常：小说缺少归属信息" };
  }

  if (novel.userId !== userId) {
    logger.warn("TASK_AUTH", "越权访问小说被拒绝", { novelId, novelUserId: novel.userId, requestUserId: userId });
    return { authorized: false, reason: "无权访问该小说" };
  }

  return { authorized: true };
}

/**
 * 校验 WritingSession 是否属于当前用户。
 */
export async function authorizeWritingSession(
  sessionId: string,
  userId: string
): Promise<SessionAuthResult> {
  const session = await prisma.writingSession.findUnique({
    where: { id: sessionId },
    include: { novel: { select: { userId: true } } },
  });

  if (!session) {
    logger.warn("TASK_AUTH", "写作会话不存在", { sessionId, userId });
    return { authorized: false, reason: "会话不存在" };
  }

  if (session.novel.userId === null || session.novel.userId === undefined) {
    if (ALLOW_LEGACY) {
      logger.warn("TASK_AUTH", "历史会话所属小说无 userId，本地兼容模式放行", {
        sessionId,
        novelId: session.novelId,
        userId,
      });
      return { authorized: true, session, isLegacyData: true };
    }
    logger.error("TASK_AUTH", "写作会话所属 novel.userId 为空，拒绝访问", {
      sessionId,
      novelId: session.novelId,
      userId,
    });
    return { authorized: false, reason: "数据异常：小说缺少归属信息" };
  }

  if (session.novel.userId !== userId) {
    logger.warn("TASK_AUTH", "越权访问写作会话被拒绝", {
      sessionId,
      novelId: session.novelId,
      sessionUserId: session.novel.userId,
      requestUserId: userId,
    });
    return { authorized: false, reason: "无权访问该会话" };
  }

  return { authorized: true, session };
}

export function authErrorResponse(reason: string, status: 401 | 403 = 403): Response {
  return new Response(JSON.stringify({ error: reason }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

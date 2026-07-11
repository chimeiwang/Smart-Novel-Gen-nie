/**
 * 智能写作会话 API（基于 LangGraph）
 *
 * @module app/api/writing/session/route
 * @description 启动新的智能写作 workflow，并可绑定到一个 WritingSession。
 */

import { NextRequest } from "next/server";

import {
  startWritingWorkflow,
} from "@/agents/graph";
import { prisma } from "@/shared/db/prisma";
import { getSession } from "@/shared/lib/auth";
import { logger } from "@/shared/lib/logger";
import { printMemorySnapshot } from "@/shared/lib/monitoring";
import { initServer } from "@/shared/lib/server-init";

export const dynamic = "force-dynamic";

initServer();

export async function POST(request: NextRequest) {
  const requestId = `session-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

  try {
    const body = await request.json();
    const {
      novelId,
      chapterId,
      writingSessionId,
      targetWordCount,
      selectedAgents,
      userMessage,
    } = body;

    logger.info("API", "收到写作 workflow 请求", {
      requestId,
      novelId,
      chapterId,
      writingSessionId,
    });
    printMemorySnapshot(`[API] 写作 workflow 请求开始 ${requestId}`);

    if (!novelId || !chapterId) {
      return new Response(
        JSON.stringify({ error: "缺少 novelId 或 chapterId" }),
        { status: 400 }
      );
    }

    const session = await getSession();
    if (!session) {
      return new Response(JSON.stringify({ error: "未登录" }), { status: 401 });
    }

    const novelOwner = await prisma.novel.findFirst({
      where: { id: novelId, userId: session.userId },
      select: { id: true },
    });
    if (!novelOwner) {
      return new Response(
        JSON.stringify({ error: "无权访问该小说" }),
        { status: 403 }
      );
    }

    if (writingSessionId) {
      const writingSession = await prisma.writingSession.findFirst({
        where: {
          id: writingSessionId,
          novelId,
          chapterId,
          novel: { userId: session.userId },
        },
        select: { id: true },
      });

      if (!writingSession) {
        return new Response(
          JSON.stringify({ error: "写作会话不存在，或不属于当前章节" }),
          { status: 403 }
        );
      }
    }

    return await startWritingWorkflow({
      novelId,
      chapterId,
      writingSessionId: writingSessionId ?? null,
      targetWordCount: targetWordCount ?? 4000,
      userMessage: userMessage ?? "",
      userId: session.userId,
      selectedAgents: selectedAgents ?? undefined,
    });
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : "服务器内部错误";
    logger.error("API", `写作 workflow 请求错误: ${errorMsg}`, {
      requestId,
      stack: error instanceof Error ? error.stack : undefined,
    });
    printMemorySnapshot(`[API] 写作 workflow 请求错误 ${requestId}`);
    return new Response(JSON.stringify({ error: errorMsg }), { status: 500 });
  }
}

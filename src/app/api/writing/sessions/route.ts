/**
 * 写作会话列表 API
 *
 * @module app/api/writing/sessions/route
 * @description 获取/创建/删除写作会话
 */

import { NextRequest } from "next/server";
import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import { getSession } from "@/shared/lib/auth";
import { authorizeNovel, authErrorResponse } from "@/agents/lib/task-auth";

// 获取会话列表
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const novelId = searchParams.get("novelId");
  const chapterId = searchParams.get("chapterId");

  if (!novelId) {
    return new Response(JSON.stringify({ error: "缺少 novelId" }), { status: 400 });
  }

  try {
    const session = await getSession();
    if (!session) return authErrorResponse("未登录", 401);

    const auth = await authorizeNovel(novelId, session.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该小说", 403);

    const where: Record<string, string> = { novelId };
    if (chapterId) {
      where.chapterId = chapterId;
    }

    const sessions = await prisma.writingSession.findMany({
      where,
      orderBy: { updatedAt: "desc" },
      include: {
        _count: {
          select: { messages: true },
        },
        messages: {
          orderBy: { createdAt: "desc" },
          take: 1,
          select: {
            content: true,
            role: true,
            agentId: true,
          },
        },
      },
    });

    // 格式化返回数据
    const result = sessions.map((s) => ({
      id: s.id,
      novelId: s.novelId,
      chapterId: s.chapterId,
      title: s.title,
      phase: s.phase,
      messageCount: s._count.messages,
      lastMessage: s.messages[0] || null,
      createdAt: s.createdAt,
      updatedAt: s.updatedAt,
    }));

    return Response.json(result);
  } catch (error) {
    logger.error("API", "获取会话列表失败", { error });
    return new Response(JSON.stringify({ error: "获取会话列表失败" }), { status: 500 });
  }
}

// 创建新会话
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { novelId, chapterId, title } = body;

    if (!novelId || !chapterId) {
      return new Response(JSON.stringify({ error: "缺少 novelId 或 chapterId" }), { status: 400 });
    }

    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    const auth = await authorizeNovel(novelId, currentSession.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该小说", 403);

    const chapter = await prisma.chapter.findFirst({
      where: { id: chapterId, novelId },
      select: { id: true },
    });
    if (!chapter) {
      return new Response(JSON.stringify({ error: "章节不存在或不属于该小说" }), { status: 404 });
    }

    // 生成默认标题
    const defaultTitle = title || `讨论 ${new Date().toLocaleString("zh-CN")}`;

    const session = await prisma.writingSession.create({
      data: {
        novelId,
        chapterId,
        title: defaultTitle,
        phase: "idle",
      },
    });

    logger.info("API", "创建会话成功", { sessionId: session.id, novelId, chapterId });
    return Response.json(session);
  } catch (error) {
    logger.error("API", "创建会话失败", { error });
    return new Response(JSON.stringify({ error: "创建会话失败" }), { status: 500 });
  }
}

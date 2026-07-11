/**
 * 单个会话操作 API
 *
 * @module app/api/writing/sessions/[id]/route
 * @description 获取/更新/删除单个写作会话
 */

import { NextRequest } from "next/server";
import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import { getSession } from "@/shared/lib/auth";
import { authorizeWritingSession, authErrorResponse } from "@/agents/lib/task-auth";
import { WritingSessionRecoveryStateSchema } from "@/shared/contracts/writing-session";
import {
  selectCurrentSessionTaskFromSession,
  selectLastSessionTask,
} from "../session-task";

// 获取会话详情（包括消息）
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    const auth = await authorizeWritingSession(id, currentSession.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该会话", 403);

    const session = await prisma.writingSession.findUnique({
      where: { id },
      include: {
        messages: {
          orderBy: { createdAt: "asc" },
        },
        tasks: {
          orderBy: { updatedAt: "desc" },
          select: {
            id: true,
            phase: true,
            updatedAt: true,
            generatedContent: true,
            graphStateJson: true,
          },
        },
      },
    });

    if (!session) {
      return new Response(JSON.stringify({ error: "会话不存在" }), { status: 404 });
    }

    const { tasks: _tasks, ...sessionPayload } = session;
    const recoveryState = WritingSessionRecoveryStateSchema.parse({
      currentTask: selectCurrentSessionTaskFromSession({
        tasks: session.tasks,
      }),
      lastTask: selectLastSessionTask(session.tasks),
    });

    return Response.json({
      ...sessionPayload,
      ...recoveryState,
    });
  } catch (error) {
    logger.error("API", "获取会话详情失败", { sessionId: id, error });
    return new Response(JSON.stringify({ error: "获取会话详情失败" }), { status: 500 });
  }
}

// 更新会话
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    const auth = await authorizeWritingSession(id, currentSession.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该会话", 403);

    const body = await request.json();
    const { title, phase } = body;

    const updateData: Record<string, string> = {};
    if (title !== undefined) updateData.title = title;
    if (phase !== undefined) updateData.phase = phase;

    const session = await prisma.writingSession.update({
      where: { id },
      data: updateData,
    });

    return Response.json(session);
  } catch (error) {
    logger.error("API", "更新会话失败", { sessionId: id, error });
    return new Response(JSON.stringify({ error: "更新会话失败" }), { status: 500 });
  }
}

// 删除会话
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  try {
    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    const auth = await authorizeWritingSession(id, currentSession.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该会话", 403);

    await prisma.writingSession.delete({
      where: { id },
    });

    logger.info("API", "删除会话成功", { sessionId: id });
    return Response.json({ success: true });
  } catch (error) {
    logger.error("API", "删除会话失败", { sessionId: id, error });
    return new Response(JSON.stringify({ error: "删除会话失败" }), { status: 500 });
  }
}

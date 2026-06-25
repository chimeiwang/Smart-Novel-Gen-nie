/**
 * 消息 API
 *
 * @module app/api/writing/messages/route
 * @description 添加消息到会话
 */

import { NextRequest } from "next/server";
import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import { getSession } from "@/shared/lib/auth";
import { authorizeWritingSession, authErrorResponse } from "@/agents/lib/task-auth";

// 添加消息
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { sessionId, role, agentId, content, intent, metadata, parentId } = body;

    if (!sessionId || !role || !content) {
      return new Response(
        JSON.stringify({ error: "缺少必需参数 sessionId, role, content" }),
        { status: 400 }
      );
    }

    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    const auth = await authorizeWritingSession(sessionId, currentSession.userId);
    if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该会话", 403);

    // 验证会话存在
    const session = await prisma.writingSession.findUnique({
      where: { id: sessionId },
    });

    if (!session) {
      return new Response(JSON.stringify({ error: "会话不存在" }), { status: 404 });
    }

    const message = await prisma.writingMessage.create({
      data: {
        sessionId,
        role,
        agentId: agentId || null,
        content,
        intent: intent || null,
        metadata: metadata ? JSON.stringify(metadata) : null,
        parentId: parentId || null,
      },
    });

    // 更新会话的 updatedAt
    await prisma.writingSession.update({
      where: { id: sessionId },
      data: { updatedAt: new Date() },
    });

    logger.info("API", "添加消息成功", { sessionId, messageId: message.id, role, agentId });
    return Response.json(message);
  } catch (error) {
    logger.error("API", "添加消息失败", { error });
    return new Response(JSON.stringify({ error: "添加消息失败" }), { status: 500 });
  }
}

// 批量添加消息
export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const { messages } = body;

    if (!Array.isArray(messages) || messages.length === 0) {
      return new Response(JSON.stringify({ error: "缺少 messages 数组" }), { status: 400 });
    }

    const currentSession = await getSession();
    if (!currentSession) return authErrorResponse("未登录", 401);

    const sessionIds = [...new Set(messages.map((m) => String(m.sessionId || "")).filter(Boolean))];
    if (sessionIds.length === 0) {
      return new Response(JSON.stringify({ error: "消息缺少 sessionId" }), { status: 400 });
    }

    for (const sessionId of sessionIds) {
      const auth = await authorizeWritingSession(sessionId, currentSession.userId);
      if (!auth.authorized) return authErrorResponse(auth.reason ?? "无权访问该会话", 403);
    }

    const result = await prisma.$transaction(async (tx) => {
      const created = [];
      for (const msg of messages) {
        const createdMsg = await tx.writingMessage.create({
          data: {
            sessionId: msg.sessionId,
            role: msg.role,
            agentId: msg.agentId || null,
            content: msg.content,
            intent: msg.intent || null,
            metadata: msg.metadata ? JSON.stringify(msg.metadata) : null,
            parentId: msg.parentId || null,
          },
        });
        created.push(createdMsg);
      }

      // 更新会话的 updatedAt
      for (const sessionId of sessionIds) {
        await tx.writingSession.update({
          where: { id: sessionId },
          data: { updatedAt: new Date() },
        });
      }

      return created;
    });

    logger.info("API", "批量添加消息成功", { count: result.length });
    return Response.json(result);
  } catch (error) {
    logger.error("API", "批量添加消息失败", { error });
    return new Response(JSON.stringify({ error: "批量添加消息失败" }), { status: 500 });
  }
}

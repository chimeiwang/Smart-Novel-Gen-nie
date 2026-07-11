/**
 * 消息持久化服务
 *
 * @module agents/lib/message-service
 * @description 处理写作消息的持久化
 */

import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";

export type MessageRole = "user" | "agent" | "system";

export interface SaveMessageParams {
  sessionId: string;
  role: MessageRole;
  agentId?: string;
  content: string;
  intent?: string;
  metadata?: Record<string, unknown>;
  parentId?: string;
}

/**
 * 保存单条消息
 */
export async function saveMessage(params: SaveMessageParams) {
  const { sessionId, role, agentId, content, intent, metadata, parentId } = params;

  try {
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

    return message;
  } catch (error) {
    logger.error("MessageService", "保存消息失败", { sessionId, role, agentId, error });
    throw error;
  }
}

/**
 * 批量保存消息
 */
export async function saveMessagesBatch(messages: SaveMessageParams[]) {
  if (messages.length === 0) return [];

  try {
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
      const sessionIds = [...new Set(messages.map((m) => m.sessionId))];
      for (const sessionId of sessionIds) {
        await tx.writingSession.update({
          where: { id: sessionId },
          data: { updatedAt: new Date() },
        });
      }

      return created;
    });

    return result;
  } catch (error) {
    logger.error("MessageService", "批量保存消息失败", { count: messages.length, error });
    throw error;
  }
}

/**
 * 获取会话的所有消息
 */
export async function getSessionMessages(sessionId: string) {
  try {
    const messages = await prisma.writingMessage.findMany({
      where: { sessionId },
      orderBy: { createdAt: "asc" },
    });

    return messages.map((m) => ({
      id: m.id,
      role: m.role,
      agentId: m.agentId,
      content: m.content,
      intent: m.intent,
      metadata: m.metadata ? JSON.parse(m.metadata) : null,
      parentId: m.parentId,
      createdAt: m.createdAt,
    }));
  } catch (error) {
    logger.error("MessageService", "获取会话消息失败", { sessionId, error });
    throw error;
  }
}

/**
 * 获取会话的最新消息
 */
export async function getLatestMessage(sessionId: string) {
  try {
    const message = await prisma.writingMessage.findFirst({
      where: { sessionId },
      orderBy: { createdAt: "desc" },
    });

    if (!message) return null;

    return {
      id: message.id,
      role: message.role,
      agentId: message.agentId,
      content: message.content,
      intent: message.intent,
      metadata: message.metadata ? JSON.parse(message.metadata) : null,
      parentId: message.parentId,
      createdAt: message.createdAt,
    };
  } catch (error) {
    logger.error("MessageService", "获取最新消息失败", { sessionId, error });
    throw error;
  }
}

/**
 * 更新消息的意图字段
 */
export async function updateMessageIntent(messageId: string, intent: string) {
  try {
    const message = await prisma.writingMessage.update({
      where: { id: messageId },
      data: { intent },
    });
    return message;
  } catch (error) {
    logger.error("MessageService", "更新消息意图失败", { messageId, error });
    throw error;
  }
}

/**
 * 更新会话阶段
 */
export async function updateSessionPhase(sessionId: string, phase: string) {
  try {
    const session = await prisma.writingSession.update({
      where: { id: sessionId },
      data: { phase },
    });
    return session;
  } catch (error) {
    logger.error("MessageService", "更新会话阶段失败", { sessionId, phase, error });
    throw error;
  }
}

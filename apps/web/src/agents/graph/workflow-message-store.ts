import { createHash } from "node:crypto";

import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";

export type WorkflowMessageRole = "user" | "agent" | "system";

export type WorkflowMessageMetadata = {
  source: "workflow";
  taskId: string;
  eventType: string;
  agentId?: string;
  contentHash: string;
  dedupKey: string;
};

export function hashWorkflowMessageContent(content: string): string {
  return createHash("sha256").update(content).digest("hex").slice(0, 24);
}

export function createWorkflowMessageDedupKey(
  metadata: Omit<WorkflowMessageMetadata, "source" | "dedupKey"> | WorkflowMessageMetadata
): string {
  return [
    "workflow",
    metadata.taskId,
    metadata.eventType,
    metadata.agentId ?? "",
    metadata.contentHash,
  ].join(":");
}

export function buildWorkflowMessageMetadata(input: {
  taskId: string;
  eventType: string;
  content: string;
  agentId?: string | null;
}): WorkflowMessageMetadata {
  const base = {
    taskId: input.taskId,
    eventType: input.eventType,
    agentId: input.agentId ?? undefined,
    contentHash: hashWorkflowMessageContent(input.content),
  };

  return {
    source: "workflow",
    ...base,
    dedupKey: createWorkflowMessageDedupKey(base),
  };
}

function readDedupKey(metadata: string | null): string | null {
  if (!metadata) return null;
  try {
    const parsed = JSON.parse(metadata) as { source?: string; dedupKey?: string };
    if (parsed.source !== "workflow" || typeof parsed.dedupKey !== "string") return null;
    return parsed.dedupKey;
  } catch {
    return null;
  }
}

export function shouldPersistWorkflowMessage(
  existingMetadata: Array<string | null>,
  metadata: WorkflowMessageMetadata
): boolean {
  return !existingMetadata.some((item) => readDedupKey(item) === metadata.dedupKey);
}

export async function persistWorkflowMessage(input: {
  sessionId?: string | null;
  taskId: string;
  role: WorkflowMessageRole;
  content?: string | null;
  agentId?: string | null;
  eventType: string;
  intent?: string | null;
}): Promise<void> {
  const content = input.content?.trim();
  if (!input.sessionId || !content) return;

  const metadata = buildWorkflowMessageMetadata({
    taskId: input.taskId,
    eventType: input.eventType,
    agentId: input.agentId,
    content,
  });

  try {
    const existing = await prisma.writingMessage.findMany({
      where: {
        sessionId: input.sessionId,
        metadata: {
          contains: metadata.dedupKey,
        },
      },
      select: { metadata: true },
      take: 1,
    });

    if (!shouldPersistWorkflowMessage(existing.map((item) => item.metadata), metadata)) {
      return;
    }

    await prisma.$transaction([
      prisma.writingMessage.create({
        data: {
          sessionId: input.sessionId,
          role: input.role,
          agentId: input.agentId ?? null,
          content,
          intent: input.intent ?? null,
          metadata: JSON.stringify(metadata),
        },
      }),
      prisma.writingSession.update({
        where: { id: input.sessionId },
        data: { updatedAt: new Date() },
      }),
    ]);
  } catch (error) {
    logger.warn("WORKFLOW_MESSAGE", "保存 workflow 可见消息失败", {
      sessionId: input.sessionId,
      taskId: input.taskId,
      eventType: input.eventType,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

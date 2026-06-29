/**
 * 待审核 Artifact 只读工具。
 *
 * @module agents/tools/read/artifact-tools
 * @description 供评审/返工 Agent 读取当前待审核草案。返回内容必须明确标记为草案。
 */

import { z } from "zod";
import type { ToolDefinition, ToolExecutorFn } from "../registry";
import { registerTool } from "../registry";
import { readOnlyPermission } from "../permissions";
import { prisma } from "@/shared/db/prisma";
import { toReviewArtifactDtoWithFreshDiff } from "@/agents/artifacts/artifact-service";
import type { ReviewArtifactKind, ReviewArtifactStatus } from "@/shared/contracts/review-artifact";

const DRAFT_WARNING = "以下内容是待审核草案，不是正式设定。除非用户确认应用，否则不得把它当成已落库事实。";

async function serializeArtifact(artifact: Parameters<typeof toReviewArtifactDtoWithFreshDiff>[0]) {
  return JSON.stringify({
    warning: DRAFT_WARNING,
    artifact: await toReviewArtifactDtoWithFreshDiff(artifact),
  }, null, 2);
}

export const LIST_REVIEW_ARTIFACTS_DEF: ToolDefinition = {
  name: "list_review_artifacts",
  description: "列出当前小说/章节的待审核草案摘要。返回内容是草案，不是正式设定。",
  inputSchema: z.object({
    status: z.enum(["draft", "under_review", "awaiting_user", "applying", "applied"]).optional(),
    kind: z.enum([
      "agent_updates",
      "outline_draft",
      "chapter_draft",
      "lore_draft",
      "revision_brief",
      "beat_plan_draft",
      "chapter_content",
      "beat_plan",
      "freeform_markdown",
    ]).optional(),
  }),
  permission: readOnlyPermission("artifact.read"),
  toolKind: "read",
};

export const listReviewArtifactsExecutor: ToolExecutorFn = async (args, state) => {
  const novelId = state.novelId || String((state.novelData as Record<string, unknown>).novelId ?? "");
  if (!novelId) return "当前上下文缺少 novelId，无法查询待审核草案。";
  const artifacts = await prisma.reviewArtifact.findMany({
    where: {
      novelId,
      ...(state.chapterId ? { chapterId: state.chapterId } : {}),
      ...(args.status ? { status: args.status as ReviewArtifactStatus } : {}),
      ...(args.kind ? { kind: args.kind as ReviewArtifactKind } : {}),
    },
    orderBy: { updatedAt: "desc" },
    take: 10,
  });
  return JSON.stringify({
    warning: DRAFT_WARNING,
    artifacts: artifacts.map((artifact) => ({
      id: artifact.id,
      artifactKey: artifact.artifactKey,
      kind: artifact.kind,
      status: artifact.status,
      summary: artifact.summary,
      revision: artifact.revision,
      updatedByAgent: artifact.updatedByAgent,
      reviewerAgent: artifact.reviewerAgent,
      updatedAt: artifact.updatedAt.toISOString(),
    })),
  }, null, 2);
};

export const GET_REVIEW_ARTIFACT_DEF: ToolDefinition = {
  name: "get_review_artifact",
  description: "读取指定待审核草案详情。返回内容是草案，不是正式设定。",
  inputSchema: z.object({
    artifact_id: z.string().min(1),
  }),
  permission: readOnlyPermission("artifact.read"),
  toolKind: "read",
};

export const getReviewArtifactExecutor: ToolExecutorFn = async (args, state) => {
  const artifactId = String(args.artifact_id);
  const artifact = await prisma.reviewArtifact.findUnique({
    where: { id: artifactId },
    include: { evaluations: { orderBy: { createdAt: "desc" } } },
  });
  if (!artifact) return `未找到待审核草案 "${artifactId}"`;
  const novelId = state.novelId || String((state.novelData as Record<string, unknown>).novelId ?? "");
  if (novelId && artifact.novelId !== novelId) return "待审核草案不属于当前小说。";
  return serializeArtifact(artifact);
};

export const GET_ACTIVE_REVIEW_ARTIFACT_DEF: ToolDefinition = {
  name: "get_active_review_artifact",
  description: "读取当前工作流正在评审/返工的待审核草案。返回内容是草案，不是正式设定。",
  inputSchema: z.object({}),
  permission: readOnlyPermission("artifact.read"),
  toolKind: "read",
};

export const getActiveReviewArtifactExecutor: ToolExecutorFn = async (_, state) => {
  const activeArtifactId = state.artifactReview?.activeArtifactId ?? state.activeArtifactId ?? null;
  if (!activeArtifactId) return "当前工作流没有 activeArtifactId。";
  const artifact = await prisma.reviewArtifact.findUnique({
    where: { id: activeArtifactId },
    include: { evaluations: { orderBy: { createdAt: "desc" } } },
  });
  if (!artifact) return `未找到当前待审核草案 "${activeArtifactId}"`;
  return serializeArtifact(artifact);
};

registerTool(LIST_REVIEW_ARTIFACTS_DEF, listReviewArtifactsExecutor);
registerTool(GET_REVIEW_ARTIFACT_DEF, getReviewArtifactExecutor);
registerTool(GET_ACTIVE_REVIEW_ARTIFACT_DEF, getActiveReviewArtifactExecutor);

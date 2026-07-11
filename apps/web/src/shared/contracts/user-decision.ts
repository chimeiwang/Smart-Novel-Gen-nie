/**
 * 用户决策契约。
 *
 * @module shared/contracts/user-decision
 * @description 统一 LangGraph interrupt/resume 中的人类决策 payload。
 */

import { z } from "zod";
import { ReviewArtifactDecisionSchema } from "./review-artifact";
import { AgentUpdateSelectionRefSchema } from "./agent-updates";

export const UserDecisionSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("artifact_review"),
    artifactId: z.string().min(1),
    decision: ReviewArtifactDecisionSchema,
    userMessage: z.string().optional(),
    editedContent: z.string().optional(),
    selectedUpdateRefs: z.array(AgentUpdateSelectionRefSchema).optional(),
  }),
  z.object({
    type: z.literal("continue_chat"),
    userMessage: z.string().min(1),
  }),
  z.object({
    type: z.literal("chapter_target_confirmation"),
    decision: z.enum(["current_chapter", "next_chapter"]),
  }),
]);

export type UserDecision = z.infer<typeof UserDecisionSchema>;

export const ResumeWritingRequestSchema = z.object({
  taskId: z.string().min(1, "缺少写作任务"),
  writingSessionId: z.string().min(1).optional(),
  userMessage: z.string().optional(),
  decision: ReviewArtifactDecisionSchema.optional(),
  artifactId: z.string().optional(),
  userDecision: z.unknown().optional(),
});
export type ResumeWritingRequest = z.infer<typeof ResumeWritingRequestSchema>;

export const UserDecisionInterruptSchema = z.discriminatedUnion("decisionType", [
  z.object({
    type: z.literal("user_input_required"),
    decisionType: z.literal("artifact_review"),
    artifactId: z.string().min(1),
    summary: z.string().optional(),
    content: z.string().optional(),
    artifact: z.unknown().optional(),
    allowedDecisions: z.array(ReviewArtifactDecisionSchema),
  }),
  z.object({
    type: z.literal("user_input_required"),
    decisionType: z.literal("chapter_target_confirmation"),
    summary: z.string().optional(),
    content: z.string().optional(),
    options: z.array(z.enum(["current_chapter", "next_chapter"])),
  }),
]);

export type UserDecisionInterrupt = z.infer<typeof UserDecisionInterruptSchema>;

export function createArtifactReviewInterrupt(input: {
  artifactId: string;
  summary?: string;
  content?: string;
  artifact?: unknown;
}): UserDecisionInterrupt {
  return {
    type: "user_input_required",
    decisionType: "artifact_review",
    artifactId: input.artifactId,
    summary: input.summary,
    content: input.content,
    artifact: input.artifact,
    allowedDecisions: ["approve", "discard", "revise"],
  };
}

export function createChapterTargetInterrupt(input: {
  currentTitle: string;
  nextTitle: string;
}) {
  return {
    type: "user_input_required",
    decisionType: "chapter_target_confirmation",
    summary: "请选择正文写入目标",
    content: `当前章「${input.currentTitle}」已经不是草稿。要继续改当前章，还是写下一章「${input.nextTitle}」？`,
    options: ["current_chapter", "next_chapter"],
  };
}

export function normalizeResumeDecision(input: {
  userDecision?: unknown;
  decision?: unknown;
  artifactId?: unknown;
  userMessage?: unknown;
}): UserDecision | null {
  const parsed = UserDecisionSchema.safeParse(input.userDecision);
  if (parsed.success) return parsed.data;

  if (typeof input.decision === "string" && typeof input.artifactId === "string") {
    const legacy = UserDecisionSchema.safeParse({
      type: "artifact_review",
      artifactId: input.artifactId,
      decision: input.decision,
      userMessage: typeof input.userMessage === "string" ? input.userMessage : undefined,
    });
    if (legacy.success) return legacy.data;
  }

  if (typeof input.userMessage === "string" && input.userMessage.trim()) {
    return {
      type: "continue_chat",
      userMessage: input.userMessage,
    };
  }

  return null;
}

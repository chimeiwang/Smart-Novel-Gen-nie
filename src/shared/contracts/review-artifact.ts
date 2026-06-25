/**
 * ReviewArtifact 契约。
 *
 * @module shared/contracts/review-artifact
 * @description Agent 待审核中间层的唯一类型来源。Artifact 是正式落库前的
 *  持久草案，不等同于正式小说事实。
 */

import { z } from "zod";
import { CoreAgentIdSchema } from "./agent";
import { AgentUpdatesSchema } from "./agent-updates";
import { BeatPlanDraftSchema } from "./beat-plan";

export const ReviewArtifactStatusSchema = z.enum([
  "draft",
  "under_review",
  "awaiting_user",
  "applying",
  "applied",
]);
export type ReviewArtifactStatus = z.infer<typeof ReviewArtifactStatusSchema>;

export const REVIEW_ARTIFACT_STATUS_LABELS: Record<ReviewArtifactStatus, string> = {
  draft: "草稿",
  under_review: "复审中",
  awaiting_user: "等待用户确认",
  applying: "应用中",
  applied: "已应用",
};

export const ReviewArtifactKindSchema = z.enum([
  "agent_updates",
  "outline_draft",
  "chapter_draft",
  "lore_draft",
  "revision_brief",
  "beat_plan_draft",
  "chapter_content",
  "beat_plan",
  "freeform_markdown",
]);
export type ReviewArtifactKind = z.infer<typeof ReviewArtifactKindSchema>;
export const TextReviewArtifactKindSchema = z.enum([
  "outline_draft",
  "chapter_draft",
  "lore_draft",
  "revision_brief",
  "beat_plan_draft",
]);
export type TextReviewArtifactKind = z.infer<typeof TextReviewArtifactKindSchema>;

export const ReviewArtifactDecisionSchema = z.enum(["approve", "discard", "revise"]);
export type ReviewArtifactDecision = z.infer<typeof ReviewArtifactDecisionSchema>;

export const ReviewArtifactEvaluationVerdictSchema = z.enum(["pass", "revise", "block"]);
export type ReviewArtifactEvaluationVerdict = z.infer<typeof ReviewArtifactEvaluationVerdictSchema>;

export const ReviewArtifactPayloadSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("agent_updates"),
    updates: AgentUpdatesSchema,
  }),
  z.object({
    kind: TextReviewArtifactKindSchema,
    content: z.string().min(1),
  }),
  z.object({
    kind: z.literal("chapter_content"),
    content: z.string().min(1),
  }),
  z.object({
    kind: z.literal("beat_plan"),
    beatPlan: BeatPlanDraftSchema,
  }),
  z.object({
    kind: z.literal("freeform_markdown"),
    markdown: z.string().min(1),
  }),
]);
export type ReviewArtifactPayload = z.infer<typeof ReviewArtifactPayloadSchema>;

export const ReviewArtifactEvaluationDtoSchema = z.object({
  id: z.string(),
  artifactId: z.string(),
  revision: z.number().int().min(1),
  evaluatorAgent: CoreAgentIdSchema,
  verdict: ReviewArtifactEvaluationVerdictSchema,
  summary: z.string(),
  requiredChanges: z.string().nullable(),
  createdAt: z.string(),
});
export type ReviewArtifactEvaluationDto = z.infer<typeof ReviewArtifactEvaluationDtoSchema>;

export const ReviewArtifactDtoSchema = z.object({
  id: z.string(),
  novelId: z.string(),
  chapterId: z.string().nullable(),
  taskId: z.string().nullable(),
  workflowRunId: z.string().nullable(),
  artifactKey: z.string().nullable(),
  kind: ReviewArtifactKindSchema,
  status: ReviewArtifactStatusSchema,
  title: z.string().nullable(),
  summary: z.string().nullable(),
  payload: ReviewArtifactPayloadSchema,
  diff: z.unknown().nullable(),
  createdByAgent: CoreAgentIdSchema.nullable(),
  updatedByAgent: CoreAgentIdSchema.nullable(),
  reviewerAgent: CoreAgentIdSchema.nullable(),
  revision: z.number().int().min(1),
  evaluations: z.array(ReviewArtifactEvaluationDtoSchema).optional(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type ReviewArtifactDto = z.infer<typeof ReviewArtifactDtoSchema>;

export const ReviewArtifactDecisionRequestSchema = z.object({
  taskId: z.string().optional(),
  artifactId: z.string(),
  decision: ReviewArtifactDecisionSchema,
  userMessage: z.string().optional(),
});
export type ReviewArtifactDecisionRequest = z.infer<typeof ReviewArtifactDecisionRequestSchema>;

const REVIEW_ARTIFACT_STATUS_TRANSITIONS: Record<ReviewArtifactStatus, ReviewArtifactStatus[]> = {
  draft: ["under_review", "awaiting_user"],
  under_review: ["draft", "awaiting_user"],
  awaiting_user: ["draft", "under_review", "applying"],
  applying: ["awaiting_user", "applied"],
  applied: [],
};

export function canTransitionReviewArtifactStatus(
  from: ReviewArtifactStatus,
  to: ReviewArtifactStatus
): boolean {
  if (from === to) return true;
  return REVIEW_ARTIFACT_STATUS_TRANSITIONS[from].includes(to);
}

export function assertReviewArtifactStatusTransition(
  from: ReviewArtifactStatus,
  to: ReviewArtifactStatus
): void {
  if (canTransitionReviewArtifactStatus(from, to)) return;
  throw new Error(
    `待审核草案不能从「${REVIEW_ARTIFACT_STATUS_LABELS[from]}」流转到「${REVIEW_ARTIFACT_STATUS_LABELS[to]}」`
  );
}

export function getReviewArtifactStatusLabel(status: ReviewArtifactStatus): string {
  return REVIEW_ARTIFACT_STATUS_LABELS[status];
}

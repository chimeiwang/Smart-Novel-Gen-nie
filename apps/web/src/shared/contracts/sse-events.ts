/**
 * SSE 事件契约（Phase 4：唯一字段来源）
 *
 * @module shared/contracts/sse-events
 * @description 后端 SSE 事件和前端 processStream 使用同一 union。
 *  新增事件类型只需改此文件，前后端同步感知。
 *
 * @phase Phase 4 — SSE 事件契约统一
 */

import type { components } from "@inkforge/api-client";
import { z } from "zod";
import { CoreAgentIdSchema } from "./agent";
import { WritingTaskPhaseSchema } from "./workflow";
import { ReviewArtifactDecisionSchema } from "./review-artifact";
import { CreativeOperationSchema } from "./creative-operation";

// ============================================
// 基础事件
// ============================================

export const StartEventSchema = z.object({
  type: z.literal("start"),
  taskId: z.string(),
});

export const DoneEventSchema = z.object({
  type: z.literal("done"),
  taskId: z.string().optional(),
  finalContent: z.string().optional(),
  conversationSummary: z.string().optional(),
  activeAgent: CoreAgentIdSchema.nullable().optional(),
});

export const CompletedEventSchema = z.object({
  type: z.literal("completed"),
  taskId: z.string().optional(),
  finalContent: z.string().optional(),
  conversationSummary: z.string().optional(),
  activeAgent: z.string().optional(),
});

export const ErrorEventSchema = z.object({
  type: z.literal("error"),
  message: z.string(),
});

export const RunOutcomeEventSchema = z.object({
  type: z.literal("run_outcome"),
  state: z.enum([
    "queued",
    "running",
    "waiting_user",
    "succeeded",
    "failed",
    "cancelled",
    "inconsistent",
  ]),
  code: z.string().min(1),
  taskTerminal: z.boolean(),
  streamShouldClose: z.boolean(),
  reconciliationRequired: z.boolean(),
  currentCommand: z.object({
    id: z.string(),
    kind: z.string(),
    status: z.enum(["pending", "submitted", "processing", "succeeded", "failed"]),
    updatedAt: z.string(),
  }).nullable(),
  result: z.object({
    kind: z.enum([
      "none",
      "review_artifact",
      "short_candidate",
      "check_report",
      "final_message",
    ]),
    ready: z.boolean(),
    id: z.string().nullable().optional(),
  }),
  observedAt: z.string(),
});

export type RunOutcomeData = Omit<z.infer<typeof RunOutcomeEventSchema>, "type">;

// ============================================
// V2 Core 权威工作流事件
// ============================================

const WorkflowIdSchema = z.string().min(1).max(128).regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/);
const WorkflowProtocolCodeSchema = z.string().min(1).max(128).regex(/^[a-z][a-z0-9_.-]*$/);
const WorkflowErrorCodeSchema = z.string().min(1).max(128).regex(/^[A-Z][A-Z0-9_]*$/);
const WorkflowSha256Schema = z.string().regex(/^[0-9a-f]{64}$/);
const WorkflowLaneSchema = z.enum(["control", "interactive", "creative", "batch_media"]);
const WorkflowRunStatusSchema = z.enum([
  "pending",
  "running",
  "waiting_user",
  "completed",
  "failed",
  "cancelled",
]);
const WorkflowStepStatusSchema = z.enum(["pending", "running", "completed", "failed", "skipped"]);
const WorkflowUsageStatusSchema = z.enum(["complete", "partial", "unknown"]);
const WorkflowReviewAvailabilitySchema = z.enum(["complete", "partial", "unavailable"]);

type WorkflowPromptProfileRef = components["schemas"]["PromptProfileRef"];
type WorkflowModelProfileRef = components["schemas"]["ModelProfileRef"];
type WorkflowResolvedModelRef = components["schemas"]["ResolvedModelRef"];
export type WorkflowStepProgressSnapshot = {
  progressSequence: number;
  phase: "preparing" | "waiting_provider" | "validating" | "reporting";
  elapsedSeconds: number;
  waitingOnProvider: boolean;
  usageStatus: "complete" | "partial" | "unknown";
};
type WorkflowCurrentStepSnapshotContract = components["schemas"]["WorkflowCurrentStepSnapshot"] & {
  latestProgress: WorkflowStepProgressSnapshot | null;
};

const WorkflowPromptProfileRefSchema = z.object({
  name: WorkflowProtocolCodeSchema,
  version: z.number().int().positive(),
  sha256: WorkflowSha256Schema,
}).strict().superRefine((profile, context) => {
  if (!profile.name.endsWith(`.v${profile.version}`)) {
    context.addIssue({ code: "custom", message: "Prompt Profile name 与 version 不一致" });
  }
}) satisfies z.ZodType<WorkflowPromptProfileRef>;

export const WorkflowModelProfileRefSchema = z.object({
  profile: WorkflowProtocolCodeSchema,
  version: z.number().int().positive(),
  reasoningMode: z.enum(["disabled", "bounded"]),
  deploymentProfileKey: WorkflowProtocolCodeSchema,
  promptProfile: WorkflowPromptProfileRefSchema,
}).strict() satisfies z.ZodType<WorkflowModelProfileRef>;

export const WorkflowResolvedModelRefSchema = z.object({
  deploymentProfileKey: WorkflowProtocolCodeSchema,
  deploymentFingerprint: WorkflowSha256Schema,
  provider: WorkflowProtocolCodeSchema,
  model: z.string().trim().min(1).max(2_000),
  transportProfile: WorkflowProtocolCodeSchema,
  endpointProfile: WorkflowProtocolCodeSchema,
  structuredOutputRoute: z.enum([
    "responses_json_schema_v1",
    "chat_json_output_v1",
  ]),
  capabilityVersion: WorkflowProtocolCodeSchema,
  reasoningMode: z.enum(["disabled", "bounded"]),
  supportsRequestIdempotency: z.boolean(),
}).strict() satisfies z.ZodType<WorkflowResolvedModelRef>;

function workflowModelResolutionMatches(
  logical: WorkflowModelProfileRef,
  resolved: WorkflowResolvedModelRef,
): boolean {
  return logical.deploymentProfileKey === resolved.deploymentProfileKey
    && logical.reasoningMode === resolved.reasoningMode;
}

export const WorkflowStepProgressSnapshotSchema = z.object({
  progressSequence: z.number().int().positive(),
  phase: z.enum(["preparing", "waiting_provider", "validating", "reporting"]),
  elapsedSeconds: z.number().int().nonnegative(),
  waitingOnProvider: z.boolean(),
  usageStatus: WorkflowUsageStatusSchema,
}).strict().superRefine((progress, context) => {
  if (progress.waitingOnProvider !== (progress.phase === "waiting_provider")) {
    context.addIssue({ code: "custom", message: "waitingOnProvider 与 phase 不一致" });
  }
}) satisfies z.ZodType<WorkflowStepProgressSnapshot>;

export const WorkflowCurrentStepSnapshotSchema = z.object({
  stepId: WorkflowIdSchema,
  ordinal: z.number().int().positive(),
  purpose: WorkflowProtocolCodeSchema,
  lane: WorkflowLaneSchema,
  modelProfile: WorkflowModelProfileRefSchema.nullable(),
  resolvedModel: WorkflowResolvedModelRefSchema.nullable(),
  status: WorkflowStepStatusSchema,
  attemptCount: z.number().int().nonnegative(),
  fencingToken: z.number().int().nonnegative(),
  latestProgress: WorkflowStepProgressSnapshotSchema.nullable(),
  errorCode: WorkflowErrorCodeSchema.nullable().optional(),
}).strict().superRefine((step, context) => {
  if (step.lane === "control") {
    if (step.modelProfile || step.resolvedModel || step.latestProgress) {
      context.addIssue({ code: "custom", message: "control Step 不能携带模型身份或模型进度" });
    }
    return;
  }
  if (!step.modelProfile) {
    context.addIssue({ code: "custom", message: "模型 Step 必须携带 modelProfile" });
    return;
  }
  if (step.status === "pending" && step.latestProgress) {
    context.addIssue({ code: "custom", message: "pending 模型 Step 的 latestProgress 必须为空" });
  }
  if (step.status === "running" && !step.resolvedModel) {
    context.addIssue({ code: "custom", message: "running 模型 Step 必须携带 resolvedModel" });
    return;
  }
  if (step.resolvedModel && !workflowModelResolutionMatches(step.modelProfile, step.resolvedModel)) {
    context.addIssue({ code: "custom", message: "modelProfile 与 resolvedModel 不一致" });
  }
}) satisfies z.ZodType<WorkflowCurrentStepSnapshotContract>;

export const ReviewPendingStepSnapshotSchema = z.object({
  stepId: WorkflowIdSchema,
  ordinal: z.number().int().positive(),
  purpose: z.literal("review"),
  lane: WorkflowLaneSchema,
  modelProfile: WorkflowModelProfileRefSchema,
  status: z.literal("pending"),
  attemptCount: z.literal(0),
  fencingToken: z.literal(0),
}).strict();

export const WorkflowArtifactSnapshotSchema = z.object({
  artifactId: WorkflowIdSchema,
  artifactRevision: z.number().int().positive(),
  status: z.enum(["draft", "under_review", "awaiting_user", "applying", "applied"]),
  actionable: z.boolean(),
  reviewAvailability: WorkflowReviewAvailabilitySchema.nullable().optional(),
}).strict();

export const WorkflowErrorSnapshotSchema = z.object({
  errorCode: WorkflowErrorCodeSchema,
  failedStepId: WorkflowIdSchema.nullable().optional(),
  outcomeUnknown: z.boolean(),
}).strict();

export const WorkflowRunSnapshotSchema = z.object({
  workflow: WorkflowProtocolCodeSchema,
  operation: WorkflowProtocolCodeSchema.nullable().optional(),
  status: WorkflowRunStatusSchema,
  activeSteps: z.array(WorkflowCurrentStepSnapshotSchema).max(32),
  currentStep: WorkflowCurrentStepSnapshotSchema.nullable().optional(),
  cancelRequestedAt: z.string().min(1).nullable().optional(),
  lastEventSequence: z.number().int().nonnegative(),
  revision: z.number().int().positive(),
  artifact: WorkflowArtifactSnapshotSchema.nullable().optional(),
  error: WorkflowErrorSnapshotSchema.nullable().optional(),
}).strict().superRefine((snapshot, context) => {
  const sortedKeys = snapshot.activeSteps
    .map((step) => [step.ordinal, step.stepId] as const)
    .toSorted(([leftOrdinal, leftId], [rightOrdinal, rightId]) => (
      leftOrdinal - rightOrdinal || leftId.localeCompare(rightId)
    ));
  const actualKeys = snapshot.activeSteps.map((step) => [step.ordinal, step.stepId] as const);
  if (JSON.stringify(actualKeys) !== JSON.stringify(sortedKeys)) {
    context.addIssue({ code: "custom", message: "activeSteps 必须按 ordinal、stepId 稳定排序" });
  }
  if (new Set(snapshot.activeSteps.map((step) => step.stepId)).size !== snapshot.activeSteps.length) {
    context.addIssue({ code: "custom", message: "activeSteps 不能包含重复 stepId" });
  }
  if (new Set(snapshot.activeSteps.map((step) => step.ordinal)).size !== snapshot.activeSteps.length) {
    context.addIssue({ code: "custom", message: "activeSteps 不能包含重复 ordinal" });
  }
  if (snapshot.activeSteps.some((step) => step.status !== "pending" && step.status !== "running")) {
    context.addIssue({ code: "custom", message: "activeSteps 只能包含 pending/running Step" });
  }
  if (snapshot.activeSteps.length > 0) {
    if (snapshot.status !== "pending" && snapshot.status !== "running") {
      context.addIssue({ code: "custom", message: "只有执行中的 Run 可以包含 activeSteps" });
    }
    const currentStep = snapshot.currentStep;
    const highestPriorityStep = snapshot.activeSteps[0];
    if (!currentStep || !highestPriorityStep || !(
      highestPriorityStep.stepId === currentStep.stepId
      && highestPriorityStep.ordinal === currentStep.ordinal
      && highestPriorityStep.purpose === currentStep.purpose
      && highestPriorityStep.lane === currentStep.lane
      && highestPriorityStep.status === currentStep.status
      && highestPriorityStep.attemptCount === currentStep.attemptCount
      && highestPriorityStep.fencingToken === currentStep.fencingToken
      && highestPriorityStep.errorCode === currentStep.errorCode
      && JSON.stringify(highestPriorityStep.modelProfile) === JSON.stringify(currentStep.modelProfile)
      && JSON.stringify(highestPriorityStep.resolvedModel) === JSON.stringify(currentStep.resolvedModel)
      && JSON.stringify(highestPriorityStep.latestProgress) === JSON.stringify(currentStep.latestProgress)
    )) {
      context.addIssue({ code: "custom", message: "currentStep 必须等于 activeSteps 的最高优先级兼容摘要" });
    }
  } else if (snapshot.currentStep) {
    context.addIssue({ code: "custom", message: "没有 activeSteps 时 currentStep 必须为空" });
  }
  if (snapshot.status === "failed" && !snapshot.error) {
    context.addIssue({ code: "custom", message: "failed snapshot 必须包含 error" });
  }
  if (snapshot.status !== "failed" && snapshot.error) {
    context.addIssue({ code: "custom", message: "非 failed snapshot 禁止包含 error" });
  }
  if (snapshot.status === "cancelled" && !snapshot.cancelRequestedAt) {
    context.addIssue({ code: "custom", message: "cancelled snapshot 必须包含 cancelRequestedAt" });
  }
  if (snapshot.cancelRequestedAt && snapshot.status !== "running" && snapshot.status !== "cancelled") {
    context.addIssue({ code: "custom", message: "cancelRequestedAt 只允许出现在 running/cancelled" });
  }
  if (
    snapshot.artifact?.actionable
    && (
      snapshot.status !== "waiting_user"
      || Boolean(snapshot.cancelRequestedAt)
      || snapshot.artifact.status !== "awaiting_user"
    )
  ) {
    context.addIssue({ code: "custom", message: "Artifact 当前不可操作" });
  }
});

export const RunSnapshotEventSchema = z.object({
  type: z.literal("run_snapshot"),
  protocolVersion: z.literal("2.0"),
  engineVersion: z.literal(2),
  runId: WorkflowIdSchema,
  baseSequence: z.number().int().nonnegative(),
  snapshot: WorkflowRunSnapshotSchema,
}).strict().superRefine((frame, context) => {
  if (frame.baseSequence !== frame.snapshot.lastEventSequence) {
    context.addIssue({ code: "custom", message: "baseSequence 必须等于 lastEventSequence" });
  }
});

const WorkflowEnvelopeBase = {
  type: z.literal("workflow_event"),
  protocolVersion: z.literal("2.0"),
  engineVersion: z.literal(2),
  runId: WorkflowIdSchema,
  sequence: z.number().int().positive(),
  occurredAt: z.string().min(1),
};

function workflowEnvelope<TEventType extends string, TPayload extends z.ZodType>(
  eventType: TEventType,
  payload: TPayload,
) {
  return z.object({
    ...WorkflowEnvelopeBase,
    eventType: z.literal(eventType),
    payload,
  }).strict();
}

export const WorkflowEventEnvelopeSchema = z.discriminatedUnion("eventType", [
  workflowEnvelope("run_accepted", z.object({
    workflow: WorkflowProtocolCodeSchema,
    operation: WorkflowProtocolCodeSchema.nullable().optional(),
    targetType: WorkflowProtocolCodeSchema.nullable().optional(),
    targetId: WorkflowIdSchema.nullable().optional(),
    runRevision: z.number().int().positive(),
  }).strict().superRefine((payload, context) => {
    if (Boolean(payload.targetType) !== Boolean(payload.targetId)) {
      context.addIssue({ code: "custom", message: "targetType 与 targetId 必须同时提供" });
    }
  })),
  workflowEnvelope("intent_resolved", z.object({
    workflow: WorkflowProtocolCodeSchema,
    operation: WorkflowProtocolCodeSchema,
    targetType: WorkflowProtocolCodeSchema,
    targetId: WorkflowIdSchema,
    confidence: z.number().min(0).max(1),
  }).strict()),
  workflowEnvelope("clarification_required", z.object({
    clarificationCode: WorkflowProtocolCodeSchema,
    prompt: z.string().trim().min(1).max(2_000),
    decisionStepId: WorkflowIdSchema,
  }).strict()),
  workflowEnvelope("evidence_ready", z.object({
    bundleId: WorkflowIdSchema,
    bundleVersion: z.number().int().positive(),
    manifestSha256: WorkflowSha256Schema,
    totalBytes: z.number().int().nonnegative(),
  }).strict()),
  workflowEnvelope("step_queued", z.object({
    stepId: WorkflowIdSchema,
    ordinal: z.number().int().positive(),
    purpose: WorkflowProtocolCodeSchema,
    lane: WorkflowLaneSchema,
    modelProfile: WorkflowModelProfileRefSchema,
    attemptCount: z.number().int().positive(),
    fencingToken: z.number().int().positive(),
    reason: WorkflowProtocolCodeSchema,
  }).strict()),
  workflowEnvelope("step_started", z.object({
    stepId: WorkflowIdSchema,
    ordinal: z.number().int().positive(),
    purpose: WorkflowProtocolCodeSchema,
    modelProfile: WorkflowModelProfileRefSchema,
    attemptCount: z.number().int().positive(),
    fencingToken: z.number().int().positive(),
  }).strict()),
  workflowEnvelope("step_progress", z.object({
    stepId: WorkflowIdSchema,
    fencingToken: z.number().int().positive(),
    progressSequence: z.number().int().positive(),
    modelProfile: WorkflowModelProfileRefSchema,
    resolvedModel: WorkflowResolvedModelRefSchema,
    phase: z.enum(["preparing", "waiting_provider", "validating", "reporting"]),
    elapsedSeconds: z.number().int().nonnegative(),
    waitingOnProvider: z.boolean(),
    usageStatus: WorkflowUsageStatusSchema,
  }).strict().superRefine((payload, context) => {
    if (payload.waitingOnProvider !== (payload.phase === "waiting_provider")) {
      context.addIssue({ code: "custom", message: "waitingOnProvider 与 phase 不一致" });
    }
    if (!workflowModelResolutionMatches(payload.modelProfile, payload.resolvedModel)) {
      context.addIssue({ code: "custom", message: "modelProfile 与 resolvedModel 不一致" });
    }
  })),
  workflowEnvelope("step_finished", z.object({
    stepId: WorkflowIdSchema,
    fencingToken: z.number().int().positive(),
    status: z.enum(["completed", "failed", "skipped"]),
    errorCode: WorkflowErrorCodeSchema.nullable(),
  }).strict().superRefine((payload, context) => {
    if (payload.status === "failed" && !payload.errorCode) {
      context.addIssue({ code: "custom", message: "failed step_finished 必须包含 errorCode" });
    }
    if (payload.status !== "failed" && payload.errorCode) {
      context.addIssue({ code: "custom", message: "只有 failed step_finished 可以包含 errorCode" });
    }
  })),
  workflowEnvelope("candidate_ready", z.object({
    stepId: WorkflowIdSchema,
    artifactId: WorkflowIdSchema,
    artifactRevision: z.number().int().positive(),
  }).strict()),
  workflowEnvelope("review_started", z.object({
    artifactId: WorkflowIdSchema,
    artifactRevision: z.number().int().positive(),
    reviewerSteps: z.array(ReviewPendingStepSnapshotSchema).min(1).max(32),
  }).strict().superRefine((payload, context) => {
    const sorted = payload.reviewerSteps.toSorted((left, right) => (
      left.ordinal - right.ordinal || left.stepId.localeCompare(right.stepId)
    ));
    if (JSON.stringify(payload.reviewerSteps) !== JSON.stringify(sorted)) {
      context.addIssue({ code: "custom", message: "reviewerSteps 必须稳定排序" });
    }
    if (new Set(payload.reviewerSteps.map((step) => step.stepId)).size !== payload.reviewerSteps.length) {
      context.addIssue({ code: "custom", message: "reviewerSteps 不能包含重复 stepId" });
    }
    if (new Set(payload.reviewerSteps.map((step) => step.ordinal)).size !== payload.reviewerSteps.length) {
      context.addIssue({ code: "custom", message: "reviewerSteps 不能包含重复 ordinal" });
    }
  })),
  workflowEnvelope("review_completed", z.object({
    artifactId: WorkflowIdSchema,
    artifactRevision: z.number().int().positive(),
    evaluationIds: z.array(WorkflowIdSchema).min(1).max(32),
    mergedVerdict: z.enum(["pass", "issues_found", "cannot_assess"]),
    reviewAvailability: WorkflowReviewAvailabilitySchema,
  }).strict().superRefine((payload, context) => {
    if (new Set(payload.evaluationIds).size !== payload.evaluationIds.length) {
      context.addIssue({ code: "custom", message: "evaluationIds 不能重复" });
    }
    if (payload.reviewAvailability === "unavailable" && payload.mergedVerdict !== "cannot_assess") {
      context.addIssue({ code: "custom", message: "复审不可用时不得给出内容结论" });
    }
  })),
  workflowEnvelope("awaiting_user", z.object({
    artifactId: WorkflowIdSchema,
    artifactRevision: z.number().int().positive(),
    allowedDecisions: z.array(z.enum(["approve", "discard", "revise"])).min(1).max(3),
    reviewAvailability: WorkflowReviewAvailabilitySchema,
  }).strict().superRefine((payload, context) => {
    if (new Set(payload.allowedDecisions).size !== payload.allowedDecisions.length) {
      context.addIssue({ code: "custom", message: "allowedDecisions 不能重复" });
    }
  })),
  workflowEnvelope("applying", z.object({
    artifactId: WorkflowIdSchema,
    artifactRevision: z.number().int().positive(),
    decisionStepId: WorkflowIdSchema,
  }).strict()),
  workflowEnvelope("completed", z.object({
    outcomeType: WorkflowProtocolCodeSchema,
    artifactId: WorkflowIdSchema.nullable().optional(),
    artifactRevision: z.number().int().positive().nullable().optional(),
    resultId: WorkflowIdSchema.nullable().optional(),
  }).strict().superRefine((payload, context) => {
    if (Boolean(payload.artifactId) !== Boolean(payload.artifactRevision)) {
      context.addIssue({ code: "custom", message: "artifactId 与 artifactRevision 必须同时提供" });
    }
  })),
  workflowEnvelope("failed", z.object({
    errorCode: WorkflowErrorCodeSchema,
    failedStepId: WorkflowIdSchema.nullable().optional(),
    outcomeUnknown: z.boolean(),
  }).strict()),
  workflowEnvelope("cancelled", z.object({
    cancelRequestId: WorkflowIdSchema,
    cancelledStepId: WorkflowIdSchema.nullable().optional(),
  }).strict()),
]);

export const ResumeEventSchema = z.object({
  type: z.literal("resume"),
  taskId: z.string(),
  resumeType: z.string(),
  historyCount: z.number().optional(),
  lastActiveAgent: z.string().nullable().optional(),
});

// ============================================
// Agent 事件
// ============================================

export const AgentStartEventSchema = z.object({
  type: z.literal("agent_start"),
  agentId: CoreAgentIdSchema,
  agentName: z.string(),
});

export const AgentDoneEventSchema = z.object({
  type: z.literal("agent_done"),
  agentId: CoreAgentIdSchema,
  agentName: z.string(),
  durationMs: z.number().optional(),
  hasOutput: z.boolean().optional(),
  content: z.string().optional(),
  insights: z.array(z.unknown()).optional(),
  proactiveSuggestions: z.array(z.unknown()).optional(),
  scores: z.object({}).passthrough().optional(),
  qualityGate: z.string().nullable().optional(),
  rewriteBrief: z.string().nullable().optional(),
  source: z.string().optional(),
});

export const AgentStatusEventSchema = z.object({
  type: z.literal("agent_status"),
  agentId: z.string(),
  status: z.string(),
  message: z.string().optional(),
  question: z.string().optional(),
  targetType: z.string().optional(),
  targetName: z.string().optional(),
  changes: z.string().optional(),
  error: z.string().optional(),
  toolName: z.string().optional(),
  argsSummary: z.string().optional(),
  resultSummary: z.string().optional(),
  detailsHidden: z.boolean().optional(),
});

export const AgentChunkEventSchema = z.object({
  type: z.literal("agent_chunk"),
  agentId: z.string(),
  chunk: z.string(),
});

// ============================================
// 路由/意图事件
// ============================================

export const ClassifyingIntentEventSchema = z.object({
  type: z.literal("classifying_intent"),
  message: z.string().optional(),
});

export const IntentClassifiedEventSchema = z.object({
  type: z.literal("intent_classified"),
  targetAgent: CoreAgentIdSchema.nullable(),
  operation: CreativeOperationSchema.nullable().optional(),
  confidence: z.number(),
  reasoning: z.string(),
  rawMessage: z.string().optional(),
});

export const OperationClassifiedEventSchema = z.object({
  type: z.literal("operation_classified"),
  operation: CreativeOperationSchema,
  rawMessage: z.string().optional(),
});

export const OperationStageEventSchema = z.object({
  type: z.literal("operation_stage"),
  stage: z.string(),
  label: z.string(),
  message: z.string().optional(),
  artifactId: z.string().optional(),
});

export const CommandParsedEventSchema = z.object({
  type: z.literal("command_parsed"),
  targetAgent: CoreAgentIdSchema.nullable(),
  operation: CreativeOperationSchema.nullable().optional(),
  rawMessage: z.string(),
});

// ============================================
// 交互事件
// ============================================

export const UserInputRequiredEventSchema = z.object({
  type: z.literal("user_input_required"),
  decisionType: z.enum(["artifact_review", "chapter_target_confirmation"]).optional(),
  phase: z.string().optional(),
  content: z.string().optional(),
  generatedContent: z.string().optional(),
  pendingUpdates: z.unknown().optional(),
  artifactId: z.string().optional(),
  artifact: z.unknown().optional(),
  summary: z.string().optional(),
  options: z.array(z.string()).optional(),
  allowedDecisions: z.array(ReviewArtifactDecisionSchema).optional(),
});

export const PhaseStartEventSchema = z.object({
  type: z.literal("phase_start"),
  phase: z.string(),
  agents: z.array(z.string()).optional(),
});

export const PhaseChangeEventSchema = z.object({
  type: z.literal("phase_change"),
  phase: z.string(),
});

export const UpdatesSavedEventSchema = z.object({
  type: z.literal("updates_saved"),
  agentId: z.string(),
  success: z.boolean(),
  summary: z.string().optional(),
  errors: z.array(z.string()).optional(),
  savedCount: z.number().optional(),
});

export const UpdatesDeclinedEventSchema = z.object({
  type: z.literal("updates_declined"),
  agentId: z.string(),
});

export const ArtifactSubmittedEventSchema = z.object({
  type: z.literal("artifact_submitted"),
  agentId: z.string(),
  artifactId: z.string(),
  status: z.string(),
  revision: z.number().optional(),
  artifact: z.unknown().optional(),
});

export const ArtifactReviewStartedEventSchema = z.object({
  type: z.literal("artifact_review_started"),
  fromAgent: z.string(),
  toAgent: z.string(),
  artifactId: z.string(),
  artifactKey: z.string().nullable().optional(),
  revision: z.number().optional(),
  depth: z.number().optional(),
});

export const ArtifactAwaitingUserApprovalEventSchema = z.object({
  type: z.literal("artifact_awaiting_user_approval"),
  agentId: z.string(),
  artifactId: z.string(),
  artifact: z.unknown().optional(),
});

export const ArtifactAppliedEventSchema = z.object({
  type: z.literal("artifact_applied"),
  artifactId: z.string(),
  success: z.boolean(),
  summary: z.string().optional(),
  errors: z.array(z.string()).optional(),
  savedCount: z.number().optional(),
  artifact: z.unknown().optional(),
});

export const ArtifactDeletedEventSchema = z.object({
  type: z.literal("artifact_deleted"),
  artifactId: z.string(),
});

export const ReviewArtifactRequestedEventSchema = z.object({
  type: z.literal("review_artifact_requested"),
  agentId: z.string(),
  artifactId: z.string(),
  artifact: z.unknown().optional(),
  reason: z.string().optional(),
});

export const UpdateBuilderStartedEventSchema = z.object({
  type: z.literal("update_builder_started"),
  agentId: z.string(),
  artifactKey: z.string(),
  summary: z.string().optional(),
});

export const UpdateBuilderBatchAppendedEventSchema = z.object({
  type: z.literal("update_builder_batch_appended"),
  agentId: z.string(),
  artifactKey: z.string(),
  sectionNames: z.array(z.string()).optional(),
});

export const UpdateBuilderOutlineTreeAppendedEventSchema = z.object({
  type: z.literal("update_builder_outline_tree_appended"),
  agentId: z.string(),
  artifactKey: z.string(),
  stageCount: z.number().optional(),
  nodeCount: z.number().optional(),
});

export const UpdateBuilderBatchIgnoredEventSchema = z.object({
  type: z.literal("update_builder_batch_ignored"),
  agentId: z.string(),
  artifactKey: z.string(),
  reason: z.string().optional(),
});

export const UpdateBuilderTextPutEventSchema = z.object({
  type: z.literal("update_builder_text_put"),
  agentId: z.string(),
  artifactKey: z.string(),
  section: z.string(),
});

export const UpdateBuilderTextIgnoredEventSchema = z.object({
  type: z.literal("update_builder_text_ignored"),
  agentId: z.string(),
  artifactKey: z.string(),
  section: z.string().optional(),
  reason: z.string().optional(),
});

export const UpdateBuilderValidationFailedEventSchema = z.object({
  type: z.literal("update_builder_validation_failed"),
  agentId: z.string(),
  artifactKey: z.string(),
  errors: z.array(z.string()),
});

// ============================================
// Agent 间调用事件
// ============================================

export const CallConfirmedEventSchema = z.object({
  type: z.literal("call_confirmed"),
  fromAgent: z.string(),
  toAgent: z.string(),
  depth: z.number().optional(),
});

export const CallDeclinedEventSchema = z.object({
  type: z.literal("call_declined"),
  fromAgent: z.string(),
  toAgent: z.string(),
});

// ============================================
// 主动智能事件
// ============================================

export const AgentInsightsEventSchema = z.object({
  type: z.literal("agent_insights"),
  agentId: z.string(),
  insights: z.array(z.unknown()),
});

export const ProactiveSuggestionsEventSchema = z.object({
  type: z.literal("proactive_suggestions"),
  agentId: z.string(),
  suggestions: z.array(z.unknown()),
});

// ============================================
// 状态事件
// ============================================

export const StateUpdateEventSchema = z.object({
  type: z.literal("state_update"),
  node: z.string().optional(),
  phase: WritingTaskPhaseSchema.optional(),
  activeAgent: CoreAgentIdSchema.nullable().optional(),
  changedKeys: z.array(z.string()).optional(),
});

export const StatusReportEventSchema = z.object({
  type: z.literal("status_report"),
  content: z.string().optional(),
});

// ============================================
// Union
// ============================================

const LegacyWritingSseEventSchema = z.discriminatedUnion("type", [
  StartEventSchema,
  DoneEventSchema,
  CompletedEventSchema,
  ErrorEventSchema,
  RunOutcomeEventSchema,
  ResumeEventSchema,
  AgentStartEventSchema,
  AgentDoneEventSchema,
  AgentStatusEventSchema,
  AgentChunkEventSchema,
  ClassifyingIntentEventSchema,
  IntentClassifiedEventSchema,
  OperationClassifiedEventSchema,
  OperationStageEventSchema,
  CommandParsedEventSchema,
  UserInputRequiredEventSchema,
  UpdatesSavedEventSchema,
  UpdatesDeclinedEventSchema,
  ArtifactSubmittedEventSchema,
  ArtifactReviewStartedEventSchema,
  ArtifactAwaitingUserApprovalEventSchema,
  ArtifactAppliedEventSchema,
  ArtifactDeletedEventSchema,
  ReviewArtifactRequestedEventSchema,
  UpdateBuilderStartedEventSchema,
  UpdateBuilderBatchAppendedEventSchema,
  UpdateBuilderOutlineTreeAppendedEventSchema,
  UpdateBuilderBatchIgnoredEventSchema,
  UpdateBuilderTextPutEventSchema,
  UpdateBuilderTextIgnoredEventSchema,
  UpdateBuilderValidationFailedEventSchema,
  CallConfirmedEventSchema,
  CallDeclinedEventSchema,
  AgentInsightsEventSchema,
  ProactiveSuggestionsEventSchema,
  StateUpdateEventSchema,
  StatusReportEventSchema,
  PhaseStartEventSchema,
  PhaseChangeEventSchema,
]);

export const WritingSseEventSchema = z.union([
  LegacyWritingSseEventSchema,
  RunSnapshotEventSchema,
  WorkflowEventEnvelopeSchema,
]);

export type WritingSseEvent = z.infer<typeof WritingSseEventSchema>;

/** 所有事件类型名 */
export type SseEventType = WritingSseEvent["type"];

/** 事件类型列表 */
export const SSE_EVENT_TYPES: SseEventType[] = [
  "start", "done", "completed", "error", "run_outcome", "resume",
  "agent_start", "agent_done", "agent_status", "agent_chunk",
  "classifying_intent", "intent_classified", "operation_classified", "operation_stage", "command_parsed",
  "user_input_required", "updates_saved", "updates_declined",
  "artifact_submitted", "artifact_review_started", "artifact_awaiting_user_approval", "artifact_applied", "artifact_deleted",
  "review_artifact_requested",
  "update_builder_started", "update_builder_batch_appended", "update_builder_outline_tree_appended", "update_builder_batch_ignored",
  "update_builder_text_put", "update_builder_text_ignored", "update_builder_validation_failed",
  "call_confirmed", "call_declined",
  "agent_insights", "proactive_suggestions",
  "state_update", "status_report",
  "phase_start", "phase_change",
  "run_snapshot", "workflow_event",
];

/**
 * 安全解析 SSE 事件。
 * 解析失败返回 null，调用方应记录日志但不应崩溃。
 */
export function normalizeSseEventData(
  raw: Record<string, unknown>,
  eventType?: string,
): Record<string, unknown> {
  if (
    raw.protocolVersion === "2.0"
    && raw.engineVersion === 2
    && typeof raw.eventType === "string"
  ) {
    return { ...raw, type: "workflow_event" };
  }
  if (
    eventType === "run_snapshot"
    || (
      raw.protocolVersion === "2.0"
      && raw.engineVersion === 2
      && "baseSequence" in raw
      && "snapshot" in raw
    )
  ) {
    return { ...raw, type: "run_snapshot" };
  }
  if (eventType && eventType !== "message") {
    return { ...raw, type: eventType };
  }
  return raw;
}

export function parseSseEvent(raw: unknown, eventType?: string): WritingSseEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const result = WritingSseEventSchema.safeParse(
    normalizeSseEventData(raw as Record<string, unknown>, eventType),
  );
  if (result.success) return result.data;
  return null;
}

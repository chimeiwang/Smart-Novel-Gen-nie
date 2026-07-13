/**
 * SSE 事件契约（Phase 4：唯一字段来源）
 *
 * @module shared/contracts/sse-events
 * @description 后端 SSE 事件和前端 processStream 使用同一 union。
 *  新增事件类型只需改此文件，前后端同步感知。
 *
 * @phase Phase 4 — SSE 事件契约统一
 */

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

export const WritingSseEventSchema = z.discriminatedUnion("type", [
  StartEventSchema,
  DoneEventSchema,
  CompletedEventSchema,
  ErrorEventSchema,
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

export type WritingSseEvent = z.infer<typeof WritingSseEventSchema>;

/** 所有事件类型名 */
export type SseEventType = WritingSseEvent["type"];

/** 事件类型列表 */
export const SSE_EVENT_TYPES: SseEventType[] = [
  "start", "done", "completed", "error", "resume",
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
];

/**
 * 安全解析 SSE 事件。
 * 解析失败返回 null，调用方应记录日志但不应崩溃。
 */
export function normalizeSseEventData(
  raw: Record<string, unknown>,
  eventType?: string,
): Record<string, unknown> {
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

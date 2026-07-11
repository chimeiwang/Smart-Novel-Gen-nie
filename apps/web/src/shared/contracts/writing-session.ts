/**
 * 写作会话恢复契约。
 *
 * WritingSession 只承载用户可见消息；可继续状态必须来自显式绑定到会话的
 * WritingTask。终态任务只作为历史摘要，不能成为 `/api/writing/resume` 的默认句柄。
 */

import { z } from "zod";

import { CreativeOperationSchema } from "./creative-operation";
import { WritingTaskPhaseSchema } from "./workflow";

export const ResumableWritingTaskPhaseSchema = z.enum([
  "awaiting_user_review",
  "active",
  "waiting_call",
]);
export type ResumableWritingTaskPhase = z.infer<typeof ResumableWritingTaskPhaseSchema>;

export const HistoricalWritingTaskPhaseSchema = z.enum(["completed", "error"]);
export type HistoricalWritingTaskPhase = z.infer<typeof HistoricalWritingTaskPhaseSchema>;

export const WritingSessionTaskSummarySchema = z.object({
  id: z.string(),
  phase: WritingTaskPhaseSchema,
  updatedAt: z.string(),
  hasAwaitingReviewArtifact: z.boolean(),
  currentOperation: CreativeOperationSchema.nullable(),
  operationStage: z.string().nullable(),
  activeArtifactId: z.string().nullable(),
});
export type WritingSessionTaskSummary = z.infer<typeof WritingSessionTaskSummarySchema>;

export const WritingSessionRecoveryStateSchema = z.object({
  currentTask: WritingSessionTaskSummarySchema.nullable(),
  lastTask: WritingSessionTaskSummarySchema.nullable(),
});
export type WritingSessionRecoveryState = z.infer<typeof WritingSessionRecoveryStateSchema>;

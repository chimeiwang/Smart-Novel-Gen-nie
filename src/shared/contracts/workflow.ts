/**
 * 工作流契约（Phase 1：唯一字段来源）
 *
 * @module shared/contracts/workflow
 * @description 写作任务阶段、写作会话阶段、章节状态、工作流运行状态。
 *  替代各处散落的硬编码字符串。
 *
 * @phase Phase 1 — 字段契约统一
 */

import { z } from "zod";

// ============================================
// Chapter 状态
// ============================================

export const ChapterStatusSchema = z.enum(["drafting", "review", "completed"]);
export type ChapterStatus = z.infer<typeof ChapterStatusSchema>;

// ============================================
// WritingTask 阶段
// ============================================

export const WritingTaskPhaseSchema = z.enum([
  "idle",
  "active",
  "waiting_call",
  "awaiting_user_review",
  "completed",
  "error",
]);
export type WritingTaskPhase = z.infer<typeof WritingTaskPhaseSchema>;

// ============================================
// WritingSession 阶段
// ============================================

export const WritingSessionPhaseSchema = z.enum([
  "idle",
  "discussing",
  "generating",
  "recording",
  "completed",
]);
export type WritingSessionPhase = z.infer<typeof WritingSessionPhaseSchema>;

// ============================================
// WorkflowRun（Phase 2 预备）
// ============================================

export const WorkflowRunKindSchema = z.enum([
  "chat",
  "chapter_generation",
  "quality_check",
  "lore_sync",
  "beat_plan",
]);
export type WorkflowRunKind = z.infer<typeof WorkflowRunKindSchema>;

export const WorkflowRunStatusSchema = z.enum([
  "pending",
  "running",
  "waiting_user",
  "completed",
  "failed",
  "cancelled",
]);
export type WorkflowRunStatus = z.infer<typeof WorkflowRunStatusSchema>;

// ============================================
// 步骤类型
// ============================================

export const WorkflowStepTypeSchema = z.enum([
  "agent",
  "tool",
  "user_confirmation",
  "persistence",
]);
export type WorkflowStepType = z.infer<typeof WorkflowStepTypeSchema>;

export const WorkflowStepStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "failed",
  "skipped",
]);
export type WorkflowStepStatus = z.infer<typeof WorkflowStepStatusSchema>;

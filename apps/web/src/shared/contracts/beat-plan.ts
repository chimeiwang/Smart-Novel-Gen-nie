/**
 * Beat Plan 契约（Phase 4：一等化）
 *
 * @module shared/contracts/beat-plan
 * @description 章节写前规划：写作目标、节拍规划、确认/驳回状态。
 *
 * @phase Phase 4 — Beat Plan 一等化
 */

import { z } from "zod";
import { CoreAgentIdSchema } from "./agent";

// ============================================
// Beat Plan 状态
// ============================================

export const BeatPlanStatusSchema = z.enum([
  "draft",
  "reviewing",
  "approved",
  "rejected",
  "superseded",
]);
export type BeatPlanStatus = z.infer<typeof BeatPlanStatusSchema>;

// ============================================
// 章节写作目标
// ============================================

export const ChapterWritingGoalSchema = z.object({
  id: z.string().optional(),
  novelId: z.string(),
  chapterId: z.string(),
  narrativeGoal: z.string().min(1, "叙事目标不能为空"),
  desiredEmotion: z.string().optional(),
  requiredForeshadowing: z.array(z.string()).optional(),
  requiredCharacters: z.array(z.string()).optional(),
  wordCountMin: z.number().optional(),
  wordCountMax: z.number().optional(),
  specialNotes: z.string().optional(),
});
export type ChapterWritingGoal = z.infer<typeof ChapterWritingGoalSchema>;

// ============================================
// 场景节拍
// ============================================

export const SceneBeatSchema = z.object({
  id: z.string().optional(),
  beatPlanId: z.string(),
  order: z.number().min(1),
  goal: z.string().min(1),
  conflict: z.string().optional(),
  characters: z.array(z.string()),
  foreshadowingRefs: z.array(z.string()).optional(),
  estimatedWords: z.number().min(0),
  acceptanceCriteria: z.string(),
});
export type SceneBeat = z.infer<typeof SceneBeatSchema>;

export const BeatPlanDraftSceneSchema = z.object({
  order: z.number().int().min(1).optional(),
  goal: z.string().min(1).max(1000),
  conflict: z.string().max(1000).optional(),
  characters: z.array(z.string().min(1).max(100)).default([]),
  foreshadowingRefs: z.array(z.string().min(1).max(200)).optional(),
  estimatedWords: z.number().int().min(0).optional(),
  acceptanceCriteria: z.string().min(1).max(1000).optional(),
});
export type BeatPlanDraftScene = z.infer<typeof BeatPlanDraftSceneSchema>;

export const BeatPlanDraftSchema = z.object({
  title: z.string().min(1).max(200),
  summary: z.string().min(1).max(2000),
  chapterGoal: z.string().min(1).max(1000),
  mainPlotConnection: z.string().max(1000).optional(),
  chapterAcceptanceCriteria: z.string().max(1000).optional(),
  totalEstimatedWords: z.number().int().min(0).optional(),
  sceneBeats: z.array(BeatPlanDraftSceneSchema).min(1).max(50),
});
export type BeatPlanDraft = z.infer<typeof BeatPlanDraftSchema>;

// ============================================
// 章季节拍规划
// ============================================

export const ChapterBeatPlanSchema = z.object({
  id: z.string().optional(),
  chapterId: z.string(),
  goalId: z.string().optional(),
  status: BeatPlanStatusSchema.default("draft"),
  chapterGoal: z.string().min(1),
  mainPlotConnection: z.string().optional(),
  chapterAcceptanceCriteria: z.string().optional(),
  totalEstimatedWords: z.number().min(0).default(0),
  generatedBy: CoreAgentIdSchema.optional(),
  createdAt: z.string().optional(),
  updatedAt: z.string().optional(),
});
export type ChapterBeatPlan = z.infer<typeof ChapterBeatPlanSchema>;

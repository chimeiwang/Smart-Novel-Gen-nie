/**
 * 质量检查契约（Phase 1：唯一字段来源）
 *
 * @module shared/contracts/quality-check
 * @description 质量检查的界面定义、请求校验和展示辅助；公共 DTO 来自 OpenAPI 生成客户端。
 *
 * @phase Phase 1 — 质量检查契约统一
 */

import type { components } from "@inkforge/api-client";
import { z } from "zod";

// ============================================
// 枚举 Schema
// ============================================

export const QualityCheckTypeSchema = z.enum([
  "consistency",
  "lore_sync",
  "editorial",
  "craft",
]);
export type QualityCheckType = z.infer<typeof QualityCheckTypeSchema>;

export const QualityCheckStatusSchema = z.enum([
  "pending",
  "running",
  "completed",
  "skipped",
  "failed",
]);
export type QualityCheckStatus = z.infer<typeof QualityCheckStatusSchema>;

export const QualityGateSchema = z.enum(["pass", "revise", "rewrite"]);
export type QualityGate = z.infer<typeof QualityGateSchema>;

// ============================================
// 评分 Schema
// ============================================

export const QualityScoresSchema = z.object({
  hook: z.number().min(0).max(10).optional(),
  tension: z.number().min(0).max(10).optional(),
  payoff: z.number().min(0).max(10).optional(),
  pacing: z.number().min(0).max(10).optional(),
  endingHook: z.number().min(0).max(10).optional(),
  readerPromise: z.number().min(0).max(10).optional(),
  overall: z.number().min(0).max(10).optional(),
});
export type QualityScores = z.infer<typeof QualityScoresSchema>;

// ============================================
// 检查项定义
// ============================================

export interface QualityCheckDefinition {
  type: QualityCheckType;
  title: string;
  summary: string;
  /** 负责此检查的 Agent ID */
  agentId: string;
}

/** 默认质量检查项（唯一来源） */
export const QUALITY_CHECK_DEFINITIONS: QualityCheckDefinition[] = [
  {
    type: "consistency",
    title: "一致性终检",
    summary: "最终检查正文与设定的一致性、角色 OOC、伏笔回收、逻辑矛盾",
    agentId: "校验",
  },
];

// ============================================
// 映射表（从定义自动派生）
// ============================================

/** type → Agent ID */
export const QUALITY_CHECK_AGENT_MAP: Record<QualityCheckType, string> =
  Object.fromEntries(
    QUALITY_CHECK_DEFINITIONS.map((d) => [d.type, d.agentId])
  ) as Record<QualityCheckType, string>;

/** type → 默认运行消息 */
export const QUALITY_CHECK_MESSAGE_MAP: Record<QualityCheckType, string> = {
  consistency: "@校验 对当前章节正文做一致性终检：检查是否存在 OOC、前后设定冲突、世界规则矛盾、伏笔误用或剧情逻辑问题。请给出明确证据和可执行修改建议。",
  lore_sync: "@设定 根据最近章节正文同步更新设定：提取明确发生的事实变化（生死/失踪/被囚、身份揭露、实力突破、物品归属、势力归属、重要经历），生成 characterExperiences 和必要的状态更新。不要因为临时情绪或场景描写覆盖核心画像字段。",
  editorial: "@编辑 从网文商业性角度评审当前章节：检查开篇钩子、主角目标、冲突强度、爽点兑现、信息差、节奏、章节尾钩和读者承诺。如果明显影响追读，请给作家明确返工 brief。",
  craft: "@编辑 从作家技法和反流水账角度评审当前章节：检查每个主要场景是否有目标、阻力、转折、代价、结果和余波，并给出可执行改法。",
};

/** 公共响应字段只由 Core OpenAPI 生成，不在前端重复声明。 */
export type QualityCheckDto = components["schemas"]["QualityCheckDto"];

// ============================================
// API 请求 Schema
// ============================================

/** 状态更新请求（只允许状态变更，不允许直接写分数） */
export const UpdateQualityCheckStatusSchema = z.object({
  id: z.string(),
  status: z.enum(["pending", "skipped"]),
  resetResult: z.boolean().optional(),
});
export type UpdateQualityCheckStatusInput = z.infer<typeof UpdateQualityCheckStatusSchema>;

/** 质量检查运行请求 */
export const RunQualityCheckSchema = z.object({
  checkId: z.string(),
  taskId: z.string().optional(),
  message: z.string().optional(),
});
export type RunQualityCheckInput = z.infer<typeof RunQualityCheckSchema>;

/** 评分归一化（0-10 取整） */
export function normalizeQualityScores(
  raw: Record<string, unknown> | null | undefined
): QualityScores | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const result: QualityScores = {};
  const keys = ["hook", "tension", "payoff", "pacing", "endingHook", "readerPromise", "overall"] as const;
  for (const key of keys) {
    const v = raw[key];
    const num = typeof v === "number" ? v : typeof v === "string" ? Number(v) : NaN;
    if (Number.isFinite(num)) {
      result[key] = Math.max(0, Math.min(10, Math.round(num)));
    }
  }
  return Object.keys(result).length > 0 ? result : undefined;
}

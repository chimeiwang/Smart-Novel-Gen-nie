/**
 * 质量检查服务（Phase 6：服务端化）
 *
 * @module agents/lib/quality-check-service
 * @description Phase 6 核心：质量报告不依赖前端 SSE 落库。
 *  当编辑/校验 Agent 产出 scores + qualityGate 后，服务端直接写入 chapterQualityCheck。
 *
 * @phase Phase 6 — 质量检查服务端化
 */

import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import type { AgentQualityFields, AgentVisibleOutput, CoreAgentId } from "../graph/state";
import { evaluateQualityGate, DEFAULT_QUALITY_GATE } from "./writing-workflow-service";
import {
  QUALITY_CHECK_DEFINITIONS,
  QUALITY_CHECK_AGENT_MAP,
  type QualityCheckType,
} from "@/shared/contracts/quality-check";

// ============================================
// 默认质量检查项
// ============================================

/** @deprecated 从共享契约导入 QUALITY_CHECK_DEFINITIONS */
export const DEFAULT_CHAPTER_QUALITY_CHECKS = QUALITY_CHECK_DEFINITIONS.map((d) => ({
  type: d.type,
  title: d.title,
  summary: d.summary,
}));

export async function ensureDefaultChapterQualityChecks(chapterId: string): Promise<void> {
  await Promise.all(
    QUALITY_CHECK_DEFINITIONS.map((check) =>
      prisma.chapterQualityCheck.upsert({
        where: {
          chapterId_type: {
            chapterId,
            type: check.type,
          },
        },
        update: {
          title: check.title,
          summary: check.summary,
        },
        create: {
          chapterId,
          type: check.type,
          title: check.title,
          summary: check.summary,
        },
      })
    )
  );
}

/** 检查类型 → Agent 映射（从共享契约导入） */
const CHECK_TYPE_TO_AGENT: Record<string, CoreAgentId> = QUALITY_CHECK_AGENT_MAP as Record<string, CoreAgentId>;

// ============================================
// 质量检查结果类型
// ============================================

export interface QualityCheckResult {
  checkId: string;
  checkType: string;
  success: boolean;
  status: "completed" | "failed";
  result?: string;
  scores?: {
    hook?: number;
    tension?: number;
    payoff?: number;
    pacing?: number;
    endingHook?: number;
    readerPromise?: number;
    overall?: number;
  };
  qualityGate?: "pass" | "revise" | "rewrite";
  rewriteBrief?: string;
  error?: string;
}

// ============================================
// 服务函数
// ============================================

/**
 * 尝试保存质量检查结果
 *
 * P1 修复：
 * - checkId 参数 → 精确匹配，不再通过 "chapterId + running" 模糊查询
 * - 无 checkId 时回退模糊匹配（向后兼容前端 SSE 触发）
 * - 保存失败时标记检查项为 "failed"
 *
 * @param checkId 可选，质量检查项 ID。传入时直接精确保存。
 */
export async function trySaveQualityCheckResult(
  agentId: CoreAgentId,
  output: AgentVisibleOutput & Partial<AgentQualityFields>,
  chapterId?: string,
  checkId?: string
): Promise<QualityCheckResult | null> {
  if (!chapterId && !checkId) return null;

  try {
    // P1：精确匹配 — 有 checkId 时直接保存
    if (checkId) {
      const targetCheck = await prisma.chapterQualityCheck.findUnique({
        where: { id: checkId },
      });
      if (!targetCheck || targetCheck.status !== "running") return null;

      const expectedAgent = CHECK_TYPE_TO_AGENT[targetCheck.type];
      if (expectedAgent && expectedAgent !== agentId) return null;

      return saveCheckResult(checkId, targetCheck.type, output);
    }

    // 回退：模糊匹配（向后兼容前端 SSE 触发）
    if (!chapterId) return null;

    const runningChecks = await prisma.chapterQualityCheck.findMany({
      where: { chapterId, status: "running" },
    });

    if (runningChecks.length === 0) return null;

    const matchedCheck = runningChecks.find(
      (c) => CHECK_TYPE_TO_AGENT[c.type] === agentId
    );
    if (!matchedCheck) return null;

    return saveCheckResult(matchedCheck.id, matchedCheck.type, output);
  } catch (error) {
    logger.error("QUALITY_CHECK", "保存质量检查结果失败", { agentId, chapterId, checkId, error: String(error) });
    // P1：保存失败 → 标记检查项 failed
    if (checkId) {
      await markCheckFailed(checkId, String(error));
    }
    return null;
  }
}

/**
 * 将质量检查结果写入数据库
 */
async function saveCheckResult(
  checkId: string,
  checkType: string,
  output: AgentVisibleOutput & Partial<AgentQualityFields>
): Promise<QualityCheckResult> {
  const scores = output.scores;
  const normalizedScores = {
    hook: clampScore(scores?.hook),
    tension: clampScore(scores?.tension),
    payoff: clampScore(scores?.payoff),
    pacing: clampScore(scores?.pacing),
    endingHook: clampScore(scores?.endingHook),
    readerPromise: clampScore(scores?.readerPromise),
    overall: clampScore(scores?.overall),
  };

  const qualityGate = output.qualityGate || evaluateQualityGate(normalizedScores).verdict;

  try {
    await prisma.chapterQualityCheck.update({
      where: { id: checkId },
      data: {
        status: "completed",
        result: output.content.trim(),
        scoreHook: normalizedScores.hook ?? null,
        scoreTension: normalizedScores.tension ?? null,
        scorePayoff: normalizedScores.payoff ?? null,
        scorePacing: normalizedScores.pacing ?? null,
        scoreEndingHook: normalizedScores.endingHook ?? null,
        scoreReaderPromise: normalizedScores.readerPromise ?? null,
        scoreOverall: normalizedScores.overall ?? null,
        qualityGate,
        rewriteBrief: output.rewriteBrief ?? null,
      },
    });

    logger.info("QUALITY_CHECK", "质量检查结果已保存", {
      checkId,
      checkType,
      qualityGate,
      overall: normalizedScores.overall,
    });

    return {
      checkId,
      checkType,
      success: true,
      status: "completed",
      result: output.content.trim(),
      scores: normalizedScores,
      qualityGate,
      rewriteBrief: output.rewriteBrief,
    };
  } catch (error) {
    logger.error("QUALITY_CHECK", "写入质量检查结果失败", {
      checkId,
      error: String(error),
    });
    return {
      checkId,
      checkType,
      success: false,
      status: "failed",
      error: String(error),
    };
  }
}

/**
 * 标记检查项为 failed（保存异常时调用）
 */
async function markCheckFailed(checkId: string, error: string): Promise<void> {
  try {
    await prisma.chapterQualityCheck.update({
      where: { id: checkId },
      data: { status: "failed", result: `保存失败: ${error}` },
    });
  } catch (e) {
    logger.error("QUALITY_CHECK", "标记检查失败也失败了", { checkId, error: String(e) });
  }
}

/**
 * 标记检查项为 running
 */
export async function markCheckRunning(checkId: string): Promise<void> {
  try {
    await prisma.chapterQualityCheck.update({
      where: { id: checkId },
      data: {
        status: "running",
        result: null,
        scoreHook: null,
        scoreTension: null,
        scorePayoff: null,
        scorePacing: null,
        scoreEndingHook: null,
        scoreReaderPromise: null,
        scoreOverall: null,
        qualityGate: null,
        rewriteBrief: null,
      },
    });
  } catch (error) {
    logger.error("QUALITY_CHECK", "标记检查项 running 失败", {
      checkId,
      error: String(error),
    });
  }
}

// ============================================
// 辅助函数
// ============================================

function clampScore(value: number | undefined | null): number | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return Math.max(0, Math.min(10, Math.round(value)));
}

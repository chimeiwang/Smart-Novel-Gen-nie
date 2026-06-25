/**
 * Beat Plan 服务（Phase 4：一等化）
 *
 * @module agents/lib/beat-plan-service
 * @description 章节写作目标的保存、节拍规划的创建/确认/驳回。
 *
 * @phase Phase 4 — Beat Plan 一等化
 */

import { prisma } from "@/shared/db/prisma";
import { logger } from "@/shared/lib/logger";
import type { BeatPlanDraft, BeatPlanDraftScene, BeatPlanStatus } from "@/shared/contracts/beat-plan";

// ============================================
// 写作目标
// ============================================

export async function saveWritingGoal(params: {
  novelId: string;
  chapterId: string;
  narrativeGoal: string;
  desiredEmotion?: string;
  requiredForeshadowing?: string[];
  requiredCharacters?: string[];
  wordCountMin?: number;
  wordCountMax?: number;
  specialNotes?: string;
}): Promise<string> {
  const existing = await prisma.chapterWritingGoal.findFirst({
    where: { chapterId: params.chapterId },
  });

  const data = {
    narrativeGoal: params.narrativeGoal,
    desiredEmotion: params.desiredEmotion,
    requiredForeshadowing: params.requiredForeshadowing ? JSON.stringify(params.requiredForeshadowing) : null,
    requiredCharacters: params.requiredCharacters ? JSON.stringify(params.requiredCharacters) : null,
    wordCountMin: params.wordCountMin,
    wordCountMax: params.wordCountMax,
    specialNotes: params.specialNotes,
  };

  if (existing) {
    await prisma.chapterWritingGoal.update({ where: { id: existing.id }, data });
    logger.info("BEAT_PLAN", "写作目标已更新", { goalId: existing.id });
    return existing.id;
  }

  const created = await prisma.chapterWritingGoal.create({
    data: { ...data, novelId: params.novelId, chapterId: params.chapterId },
  });
  logger.info("BEAT_PLAN", "写作目标已创建", { goalId: created.id });
  return created.id;
}

// ============================================
// Beat Plan
// ============================================

export async function createBeatPlan(params: {
  chapterId: string;
  goalId?: string;
  chapterGoal: string;
  mainPlotConnection?: string;
  chapterAcceptanceCriteria?: string;
  totalEstimatedWords: number;
  generatedBy?: string;
  beats: Array<{
    order: number;
    goal: string;
    conflict?: string;
    characters: string[];
    foreshadowingRefs?: string[];
    estimatedWords: number;
    acceptanceCriteria: string;
  }>;
}): Promise<string> {
  const plan = await prisma.chapterBeatPlan.create({
    data: {
      chapterId: params.chapterId,
      goalId: params.goalId,
      status: "draft",
      chapterGoal: params.chapterGoal,
      mainPlotConnection: params.mainPlotConnection,
      chapterAcceptanceCriteria: params.chapterAcceptanceCriteria,
      totalEstimatedWords: params.totalEstimatedWords,
      generatedBy: params.generatedBy,
      sceneBeats: {
        create: params.beats.map((b) => ({
          order: b.order,
          goal: b.goal,
          conflict: b.conflict,
          characters: JSON.stringify(b.characters),
          foreshadowingRefs: b.foreshadowingRefs ? JSON.stringify(b.foreshadowingRefs) : null,
          estimatedWords: b.estimatedWords,
          acceptanceCriteria: b.acceptanceCriteria,
        })),
      },
    },
    include: { sceneBeats: true },
  });
  logger.info("BEAT_PLAN", "Beat Plan 已创建", { planId: plan.id, beatCount: plan.sceneBeats.length });
  return plan.id;
}

export async function updateBeatPlanStatus(
  planId: string,
  status: BeatPlanStatus
): Promise<void> {
  await prisma.chapterBeatPlan.update({
    where: { id: planId },
    data: { status },
  });
  logger.info("BEAT_PLAN", "Beat Plan 状态更新", { planId, status });
}

export async function getLatestBeatPlan(chapterId: string) {
  return prisma.chapterBeatPlan.findFirst({
    where: { chapterId, status: "approved" },
    include: { sceneBeats: { orderBy: { order: "asc" } } },
    orderBy: { updatedAt: "desc" },
  });
}

function normalizeBeatDraftScene(scene: BeatPlanDraftScene, index: number) {
  return {
    order: scene.order ?? index + 1,
    goal: scene.goal,
    conflict: scene.conflict,
    characters: scene.characters,
    foreshadowingRefs: scene.foreshadowingRefs,
    estimatedWords: scene.estimatedWords ?? 0,
    acceptanceCriteria: scene.acceptanceCriteria ?? scene.goal,
  };
}

export function buildBeatPlanDraftFromText(input: {
  title?: string | null;
  summary?: string | null;
  content: string;
}): BeatPlanDraft {
  const normalized = input.content.replace(/\s+/g, " ").trim();
  const title = input.title?.trim() || input.summary?.trim() || "章节计划草案";
  const summary = input.summary?.trim() || normalized.slice(0, 2000) || title;
  return {
    title: title.slice(0, 200),
    summary: summary.slice(0, 2000),
    chapterGoal: summary.slice(0, 1000) || title,
    totalEstimatedWords: 0,
    sceneBeats: [
      {
        order: 1,
        goal: normalized.slice(0, 1000) || title,
        characters: [],
        estimatedWords: 0,
        acceptanceCriteria: "按文本草案执行，并在写作前由作者确认细化。",
      },
    ],
  };
}

export async function applyApprovedBeatPlan(input: {
  chapterId: string;
  beatPlan: BeatPlanDraft;
  generatedBy?: string | null;
}): Promise<string> {
  const scenes = input.beatPlan.sceneBeats.map(normalizeBeatDraftScene);
  const totalEstimatedWords =
    input.beatPlan.totalEstimatedWords ??
    scenes.reduce((sum, scene) => sum + scene.estimatedWords, 0);

  const plan = await prisma.$transaction(async (tx) => {
    await tx.chapterBeatPlan.updateMany({
      where: {
        chapterId: input.chapterId,
        status: "approved",
      },
      data: { status: "superseded" },
    });

    return tx.chapterBeatPlan.create({
      data: {
        chapterId: input.chapterId,
        status: "approved",
        chapterGoal: input.beatPlan.chapterGoal,
        mainPlotConnection: input.beatPlan.mainPlotConnection,
        chapterAcceptanceCriteria: input.beatPlan.chapterAcceptanceCriteria,
        totalEstimatedWords,
        generatedBy: input.generatedBy ?? undefined,
        sceneBeats: {
          create: scenes.map((scene) => ({
            order: scene.order,
            goal: scene.goal,
            conflict: scene.conflict,
            characters: JSON.stringify(scene.characters),
            foreshadowingRefs: scene.foreshadowingRefs ? JSON.stringify(scene.foreshadowingRefs) : null,
            estimatedWords: scene.estimatedWords,
            acceptanceCriteria: scene.acceptanceCriteria,
          })),
        },
      },
    });
  });

  logger.info("BEAT_PLAN", "Beat Plan 已应用为 approved", {
    planId: plan.id,
    chapterId: input.chapterId,
    beatCount: scenes.length,
  });
  return plan.id;
}

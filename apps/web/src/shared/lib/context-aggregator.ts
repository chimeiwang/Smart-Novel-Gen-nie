/**
 * 小说上下文聚合模块
 *
 * @module shared/lib/context-aggregator
 * @description 聚合小说的所有设定数据，供 Agent 使用
 */

import { prisma } from "@/shared/db/prisma";
import type { NovelWithContext } from "@/agents/types";
import { DEFAULT_ENABLED_AGENTS, DEFAULT_ENABLED_AGENTS_STRING } from "@/shared/contracts/agent";
import { resolveWritingOutlineContext } from "@/agents/lib/writing-outline-context";

function parseStringArray(value: string | null | undefined): string[] {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

async function getApprovedBeatPlanContext(chapterId: string): Promise<NovelWithContext["approvedBeatPlan"]> {
  const plan = await prisma.chapterBeatPlan.findFirst({
    where: { chapterId, status: "approved" },
    include: { sceneBeats: { orderBy: { order: "asc" } } },
    orderBy: { updatedAt: "desc" },
  });
  if (!plan) return null;

  return {
    id: plan.id,
    chapterGoal: plan.chapterGoal,
    mainPlotConnection: plan.mainPlotConnection ?? undefined,
    chapterAcceptanceCriteria: plan.chapterAcceptanceCriteria ?? undefined,
    totalEstimatedWords: plan.totalEstimatedWords,
    sceneBeats: plan.sceneBeats.map((beat) => ({
      order: beat.order,
      goal: beat.goal,
      conflict: beat.conflict ?? undefined,
      characters: parseStringArray(beat.characters),
      foreshadowingRefs: parseStringArray(beat.foreshadowingRefs),
      estimatedWords: beat.estimatedWords,
      acceptanceCriteria: beat.acceptanceCriteria,
    })),
  };
}

async function getChapterWritingGoalContext(chapterId: string): Promise<NonNullable<NovelWithContext["chapterWritingGoal"]> | null> {
  const goal = await prisma.chapterWritingGoal.findFirst({
    where: { chapterId },
    orderBy: { updatedAt: "desc" },
  });
  if (!goal) return null;
  return {
    id: goal.id,
    narrativeGoal: goal.narrativeGoal,
    desiredEmotion: goal.desiredEmotion ?? undefined,
    requiredForeshadowing: parseStringArray(goal.requiredForeshadowing),
    requiredCharacters: parseStringArray(goal.requiredCharacters),
    wordCountMin: goal.wordCountMin ?? undefined,
    wordCountMax: goal.wordCountMax ?? undefined,
    specialNotes: goal.specialNotes ?? undefined,
  };
}

/**
 * 聚合小说的所有设定数据
 *
 * @param novelId - 小说 ID
 * @param chapterId - 当前章节 ID
 * @returns 聚合的设定数据
 */
export async function aggregateNovelContext(
  novelId: string,
  chapterId: string
): Promise<NovelWithContext> {
  const novel = await prisma.novel.findUnique({
    where: { id: novelId },
    include: {
      chapters: {
        orderBy: { order: "asc" },
      },
      characters: {
        orderBy: { updatedAt: "desc" },
        include: {
          faction: true,
          experiences: {
            orderBy: { order: "asc" },
          },
          outgoingRelations: {
            include: {
              target: { select: { id: true, name: true } },
            },
          },
          incomingRelations: {
            include: {
              character: { select: { id: true, name: true } },
            },
          },
        },
      },
      items: {
        orderBy: { updatedAt: "desc" },
        include: {
          owner: true,
        },
      },
      locations: {
        orderBy: { updatedAt: "desc" },
      },
      factions: {
        orderBy: { updatedAt: "desc" },
        include: {
          base: true,
        },
      },
      glossaries: {
        orderBy: { updatedAt: "desc" },
      },
      storyBackground: true,
      worldSetting: true,
      writingBible: true,
      outline: true,
      outlineNodes: {
        orderBy: { order: "asc" },
      },
      plotProgress: true,
      references: {
        orderBy: { updatedAt: "desc" },
        take: 5,
      },
      appliedStyle: true,
      foreshadowings: {
        orderBy: { createdAt: "desc" },
      },
    },
  });

  if (!novel) {
    throw new Error(`Novel not found: ${novelId}`);
  }

  const chapter = novel.chapters.find((c) => c.id === chapterId);
  if (!chapter) {
    throw new Error(`Chapter not found: ${chapterId}`);
  }

  return {
    chapters: novel.chapters.map((c) => ({
      id: c.id,
      title: c.title,
      content: c.content,
      order: c.order,
    })),
    novelName: novel.name,
    chapterTitle: chapter.title,
    chapterContent: chapter.content,
    outlineSummary: novel.outline?.content ?? "",
    outlineNodes:
      novel.outlineNodes?.map((n) => ({
        id: n.id,
        title: n.title,
        content: n.content ?? undefined,
        kind: n.kind,
        status: n.status,
        order: n.order,
        parentId: n.parentId ?? undefined,
        linkedChapterId: n.linkedChapterId ?? undefined,
        chapterStartOrder: n.chapterStartOrder ?? undefined,
        chapterEndOrder: n.chapterEndOrder ?? undefined,
      })) ?? [],
    plotProgress: novel.plotProgress
      ? {
          currentStage: novel.plotProgress.currentStage,
          currentGoal: novel.plotProgress.currentGoal ?? undefined,
          currentConflict: novel.plotProgress.currentConflict ?? undefined,
          nextMilestone: novel.plotProgress.nextMilestone ?? undefined,
        }
      : {
          currentStage: "未设置",
        },
    storyBackground: novel.storyBackground?.content ?? "",
    worldSetting: novel.worldSetting?.content ?? "",
    writingBible: novel.writingBible
      ? {
          storyLengthProfile: novel.writingBible.storyLengthProfile,
          targetTotalWordCount: novel.writingBible.targetTotalWordCount ?? undefined,
          genre: novel.writingBible.genre ?? undefined,
          targetReaders: novel.writingBible.targetReaders ?? undefined,
          coreSellingPoint: novel.writingBible.coreSellingPoint ?? undefined,
          readerPromise: novel.writingBible.readerPromise ?? undefined,
          appealModel: novel.writingBible.appealModel ?? undefined,
          taboo: novel.writingBible.taboo ?? undefined,
          comparableTitles: novel.writingBible.comparableTitles ?? undefined,
          notes: novel.writingBible.notes ?? undefined,
        }
      : null,
    storyProgress: novel.storyProgress ?? "",
    characters:
      novel.characters?.map((c) => ({
        id: c.id,
        name: c.name,
        aliases: c.aliases ?? undefined,
        gender: c.gender ?? undefined,
        age: c.age ?? undefined,
        appearance: c.appearance ?? undefined,
        personality: c.personality ?? undefined,
        identity: c.identity ?? undefined,
        background: c.background ?? undefined,
        coreDesire: c.coreDesire ?? undefined,
        behaviorBoundaries: c.behaviorBoundaries ?? undefined,
        speechStyle: c.speechStyle ?? undefined,
        relationshipPrinciples: c.relationshipPrinciples ?? undefined,
        shortTermGoal: c.shortTermGoal ?? undefined,
        // 新增：实力相关
        powerLevel: c.powerLevel ?? undefined,
        combatAbility: c.combatAbility ?? undefined,
        specialSkills: c.specialSkills ?? undefined,
        // 新增：当前状态
        currentStatus: c.currentStatus,
        statusNote: c.statusNote ?? undefined,
        faction: c.faction
          ? {
              id: c.faction.id,
              name: c.faction.name,
            }
          : undefined,
        // 角色关系
        outgoingRelations: c.outgoingRelations?.map((r) => ({
          id: r.id,
          targetId: r.targetId,
          target: { id: r.target.id, name: r.target.name },
          relationType: r.relationType,
          intimacy: r.intimacy,
          description: r.description ?? undefined,
          startDate: r.startDate ?? undefined,
          endDate: r.endDate ?? undefined,
        })) ?? [],
        incomingRelations: c.incomingRelations?.map((r) => ({
          id: r.id,
          characterId: r.characterId,
          character: { id: r.character.id, name: r.character.name },
          relationType: r.relationType,
          intimacy: r.intimacy,
          description: r.description ?? undefined,
        })) ?? [],
        experiences: c.experiences?.map((e) => ({
          id: e.id,
          characterId: e.characterId,
          chapterId: e.chapterId ?? undefined,
          content: e.content,
          order: e.order,
        })) ?? [],
      })) ?? [],
    items:
      novel.items?.map((i) => ({
        id: i.id,
        name: i.name,
        aliases: i.aliases ?? undefined,
        type: i.type ?? undefined,
        rarity: i.rarity ?? undefined,
        effect: i.effect ?? undefined,
        origin: i.origin ?? undefined,
        description: i.description ?? undefined,
        ownerId: i.ownerId ?? undefined,
        owner: i.owner
          ? {
              id: i.owner.id,
              name: i.owner.name,
            }
          : undefined,
      })) ?? [],
    locations:
      novel.locations?.map((l) => ({
        id: l.id,
        name: l.name,
        aliases: l.aliases ?? undefined,
        type: l.type ?? undefined,
        parentId: l.parentId ?? undefined,
        climate: l.climate ?? undefined,
        culture: l.culture ?? undefined,
        description: l.description ?? undefined,
      })) ?? [],
    factions:
      novel.factions?.map((f) => ({
        id: f.id,
        name: f.name,
        aliases: f.aliases ?? undefined,
        type: f.type ?? undefined,
        baseId: f.baseId ?? undefined,
        base: f.base
          ? {
              id: f.base.id,
              name: f.base.name,
            }
          : undefined,
        description: f.description ?? undefined,
      })) ?? [],
    glossaries:
      novel.glossaries?.map((g) => ({
        id: g.id,
        term: g.term,
        definition: g.definition,
        category: g.category ?? undefined,
      })) ?? [],
    foreshadowings:
      novel.foreshadowings?.map((f) => ({
        id: f.id,
        name: f.name,
        plantedAt: f.plantedAt ?? undefined,
        plantedContent: f.plantedContent ?? undefined,
        expectedPayoff: f.expectedPayoff ?? undefined,
        payoffAt: f.payoffAt ?? undefined,
        status: f.status,
      })) ?? [],
    references:
      novel.references?.map((r) => ({
        id: r.id,
        title: r.title,
        type: r.type,
        content: r.content,
      })) ?? [],
    styleProfile: novel.appliedStyle?.portraitMarkdown ?? "",
    approvedBeatPlan: null,
  };
}

export async function aggregateNovelContextForWriting(
  novelId: string,
  contextChapterId: string,
  target?: {
    chapterId?: string | null;
    order?: number;
    title?: string;
    contextAnchorChapterId?: string | null;
  }
): Promise<NovelWithContext> {
  const targetChapterId = target ? target.chapterId ?? null : contextChapterId;
  const [novelData, approvedBeatPlan, chapterWritingGoal] = await Promise.all([
    aggregateNovelContext(novelId, contextChapterId),
    targetChapterId ? getApprovedBeatPlanContext(targetChapterId) : Promise.resolve(null),
    targetChapterId ? getChapterWritingGoalContext(targetChapterId) : Promise.resolve(null),
  ]);
  const targetChapter = novelData.chapters?.find((chapter) => chapter.id === targetChapterId);
  const targetOrder = target?.order ?? targetChapter?.order;
  if (targetOrder === undefined) {
    throw new Error("无法确定写作目标章节序号");
  }
  const targetTitle = target?.title ?? targetChapter?.title ?? novelData.chapterTitle;
  const writingOutlineContext = resolveWritingOutlineContext({
    outlineNodes: novelData.outlineNodes,
    targetChapter: { id: targetChapterId, order: targetOrder, title: targetTitle },
    hasApprovedBeatPlan: Boolean(approvedBeatPlan),
    hasChapterWritingGoal: Boolean(chapterWritingGoal),
  });
  return {
    ...novelData,
    novelId,
    chapterId: targetChapterId ?? contextChapterId,
    chapterTitle: targetTitle,
    targetChapterOrder: targetOrder,
    contextAnchorChapterId: target?.contextAnchorChapterId ?? contextChapterId,
    approvedBeatPlan,
    chapterWritingGoal,
    writingOutlineContext,
  };
}

export async function aggregateNovelContextLightweight(
  novelId: string,
  chapterId: string
): Promise<NovelWithContext> {
  const [novel, chapter] = await Promise.all([
    prisma.novel.findUnique({
      where: { id: novelId },
      include: {
        storyBackground: true,
        worldSetting: true,
        outline: true,
      },
    }),
    prisma.chapter.findFirst({
      where: { id: chapterId, novelId },
      select: { id: true, title: true },
    }),
  ]);

  if (!novel) {
    throw new Error(`Novel not found: ${novelId}`);
  }

  if (!chapter) {
    throw new Error(`Chapter not found: ${chapterId}`);
  }

  return {
    novelId: novel.id,
    chapterId: chapter.id,
    chapters: [],
    novelName: novel.name,
    chapterTitle: chapter.title,
    chapterContent: "",
    outlineSummary: novel.outline?.content ?? "",
    outlineNodes: [],
    plotProgress: { currentStage: "未设置" },
    storyBackground: novel.storyBackground?.content ?? "",
    worldSetting: novel.worldSetting?.content ?? "",
    writingBible: null,
    storyProgress: "",
    characters: [],
    items: [],
    locations: [],
    factions: [],
    glossaries: [],
    foreshadowings: [],
    references: [],
    styleProfile: "",
    approvedBeatPlan: null,
  };
}

/**
 * 获取写作配置
 */
export async function getWritingConfig(novelId: string): Promise<{
  defaultWordCount: number;
  enabledAgents: string[];
}> {
  const config = await prisma.writingConfig.findUnique({
    where: { novelId },
  });

  if (config) {
    return {
      defaultWordCount: config.defaultWordCount,
      enabledAgents: config.enabledAgents.split(",").filter(Boolean),
    };
  }

  // 默认配置
  return {
    defaultWordCount: 4000,
    enabledAgents: [...DEFAULT_ENABLED_AGENTS],
  };
}

/**
 * 创建或更新写作配置
 */
export async function upsertWritingConfig(
  novelId: string,
  data: {
    defaultWordCount?: number;
    enabledAgents?: string[];
  }
): Promise<void> {
  await prisma.writingConfig.upsert({
    where: { novelId },
    create: {
      novelId,
      defaultWordCount: data.defaultWordCount ?? 4000,
      enabledAgents: data.enabledAgents?.join(",") ?? DEFAULT_ENABLED_AGENTS_STRING,
    },
    update: {
      ...(data.defaultWordCount !== undefined && {
        defaultWordCount: data.defaultWordCount,
      }),
      ...(data.enabledAgents && { enabledAgents: data.enabledAgents.join(",") }),
    },
  });
}

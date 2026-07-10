"use server";

import fs from "node:fs/promises";
import path from "node:path";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { createPortraitAgent } from "@/agents";
import { deserializeGraphStateSnapshot } from "@/agents/graph/graph-state-snapshot";
import { prisma } from "@/shared/db/prisma";
import { executeUpdates } from "@/agents/lib/db-operations";
import { authorizeNovel, authorizeWritingTask } from "@/agents/lib/task-auth";
import { DEFAULT_ENABLED_AGENTS, DEFAULT_ENABLED_AGENTS_STRING } from "@/shared/contracts/agent";
import { QUALITY_CHECK_DEFINITIONS, type QualityCheckType } from "@/shared/contracts/quality-check";
import {
  hashPassword,
  verifyPassword,
  createToken,
  setSessionCookie,
  deleteSessionCookie,
  getSession,
} from "@/shared/lib/auth";
import { normalizeTokenUsageBreakdown, type TokenUsageBreakdown } from "@/shared/lib/token-cost";
import {
  SIGNUP_BONUS_MICROS,
  SIGNUP_BONUS_CREDITS,
  formatCreditMicros,
} from "@/shared/lib/billing";
import {
  DEFAULT_STORY_LENGTH_PROFILE,
  STORY_LENGTH_PROFILE_CONFIG,
  normalizeStoryLengthProfile,
  type StoryLengthProfile,
} from "@/shared/contracts/story-length-profile";
import { upsertReferenceMaterialRagIndex } from "@/shared/lib/rag-service";

type ReferenceMaterialType = "note" | "web" | "book" | "image" | "custom";
type StyleSourceType = "manual" | "agent";
type OutlineNodeKind = "stage" | "plot_unit" | "chapter_group";
type OutlineNodeStatus = "planned" | "in_progress" | "completed" | "skipped";

const OUTLINE_NODE_KINDS: OutlineNodeKind[] = ["stage", "plot_unit", "chapter_group"];
const OUTLINE_NODE_STATUSES: OutlineNodeStatus[] = ["planned", "in_progress", "completed", "skipped"];

function parsePositiveInt(value: FormDataEntryValue | string | number | null | undefined): number | null {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function defaultTargetTotalWordCount(profile: StoryLengthProfile): number {
  return profile === "short_medium" ? 80_000 : 1_000_000;
}

async function requireCurrentSession() {
  const session = await getSession();
  if (!session) throw new Error("未登录");
  return session;
}

async function requireNovelAccess(novelId: string) {
  const session = await requireCurrentSession();
  const auth = await authorizeNovel(novelId, session.userId);
  if (!auth.authorized) throw new Error(auth.reason ?? "无权访问该小说");
  return session;
}

async function requireChapterAccess(chapterId: string): Promise<string> {
  const chapter = await prisma.chapter.findUnique({
    where: { id: chapterId },
    select: { novelId: true },
  });
  if (!chapter) throw new Error("章节不存在");
  await requireNovelAccess(chapter.novelId);
  return chapter.novelId;
}

async function requireCharacterAccess(characterId: string): Promise<string> {
  const character = await prisma.character.findUnique({
    where: { id: characterId },
    select: { novelId: true },
  });
  if (!character) throw new Error("角色不存在");
  await requireNovelAccess(character.novelId);
  return character.novelId;
}

async function requireCharacterExperienceAccess(experienceId: string): Promise<string> {
  const experience = await prisma.characterExperience.findUnique({
    where: { id: experienceId },
    select: { character: { select: { novelId: true } } },
  });
  if (!experience) throw new Error("角色经历不存在");
  await requireNovelAccess(experience.character.novelId);
  return experience.character.novelId;
}

async function requireCharacterRelationAccess(relationId: string): Promise<string> {
  const relation = await prisma.characterRelation.findUnique({
    where: { id: relationId },
    select: { character: { select: { novelId: true } } },
  });
  if (!relation) throw new Error("人物关系不存在");
  await requireNovelAccess(relation.character.novelId);
  return relation.character.novelId;
}

async function assertSameNovel(
  expectedNovelId: string,
  actualNovelId: string,
  message = "资源不属于该小说"
) {
  if (expectedNovelId !== actualNovelId) throw new Error(message);
}

function assertUpdated(count: number, message = "资源不存在或无权操作") {
  if (count === 0) throw new Error(message);
}

function normalizeOutlineNodeKind(value: string): OutlineNodeKind {
  return OUTLINE_NODE_KINDS.includes(value as OutlineNodeKind) ? (value as OutlineNodeKind) : "stage";
}

function normalizeOutlineNodeStatus(value: string | undefined): OutlineNodeStatus {
  return OUTLINE_NODE_STATUSES.includes(value as OutlineNodeStatus) ? (value as OutlineNodeStatus) : "planned";
}

function getAllowedOutlineChildKind(kind: OutlineNodeKind): OutlineNodeKind | null {
  if (kind === "stage") return "plot_unit";
  if (kind === "plot_unit") return "chapter_group";
  return null;
}

async function assertOutlineParentAllowed(input: {
  novelId: string;
  kind: OutlineNodeKind;
  parentId?: string | null;
  selfId?: string;
}) {
  if (input.kind === "stage") {
    if (input.parentId) throw new Error("阶段/卷必须是顶层节点");
    return null;
  }

  if (!input.parentId) {
    throw new Error(input.kind === "plot_unit" ? "剧情单元必须挂在阶段/卷下" : "章节组必须挂在剧情单元下");
  }

  if (input.parentId === input.selfId) {
    throw new Error("大纲节点不能设为自己的父节点");
  }

  const parent = await prisma.outlineNode.findFirst({
    where: { id: input.parentId, novelId: input.novelId },
    select: { id: true, kind: true },
  });

  if (!parent) throw new Error("父节点不存在或无权访问");
  if (input.kind === "plot_unit" && parent.kind !== "stage") throw new Error("剧情单元只能挂在阶段/卷下");
  if (input.kind === "chapter_group" && parent.kind !== "plot_unit") throw new Error("章节组只能挂在剧情单元下");
  return parent;
}

async function assertOutlineChildrenAllowed(input: {
  nodeId: string;
  nextKind: OutlineNodeKind;
}) {
  const childCount = await prisma.outlineNode.count({ where: { parentId: input.nodeId } });
  if (childCount === 0) return;

  const allowedChildKind = getAllowedOutlineChildKind(input.nextKind);
  if (!allowedChildKind) {
    throw new Error("存在子节点的节点不能改为章节组，请先移动或删除子节点");
  }

  const invalidChild = await prisma.outlineNode.findFirst({
    where: {
      parentId: input.nodeId,
      kind: { not: allowedChildKind },
    },
    select: { title: true },
  });

  if (invalidChild) {
    const label = input.nextKind === "stage" ? "阶段/卷" : input.nextKind === "plot_unit" ? "剧情单元" : "章节组";
    throw new Error(`存在不兼容子节点的节点不能改为${label}，请先移动或删除子节点`);
  }
}

// ============================================
// 小说相关
// ============================================

export async function createNovelAction(formData: FormData) {
  const name = String(formData.get("name") ?? "").trim();
  const summary = String(formData.get("summary") ?? "").trim();
  const storyLengthProfile = normalizeStoryLengthProfile(formData.get("storyLengthProfile"));
  const targetTotalWordCount = parsePositiveInt(formData.get("targetTotalWordCount")) ?? defaultTargetTotalWordCount(storyLengthProfile);
  const genre = String(formData.get("genre") ?? "").trim();
  const protagonist = String(formData.get("protagonist") ?? "").trim();
  const coreSellingPoint = String(formData.get("coreSellingPoint") ?? "").trim();
  const readerPromise = String(formData.get("readerPromise") ?? "").trim();
  const firstChapterGoal = String(formData.get("firstChapterGoal") ?? "").trim();
  const session = await requireCurrentSession();

  if (!name) {
    return { novelId: null };
  }

  const writingBibleNotes = [
    protagonist ? "主角起点：" + protagonist : "",
    firstChapterGoal ? "第一章目标：" + firstChapterGoal : "",
  ].filter(Boolean).join("\n");

  const novel = await prisma.novel.create({
    data: {
      name,
      summary: summary || null,
      storyProgress: firstChapterGoal ? "第一章目标：" + firstChapterGoal : null,
      userId: session.userId,
      chapters: {
        create: {
          title: "第一章",
          order: 1,
        },
      },
      outline: {
        create: {
          content: "",
        },
      },
      plotProgress: {
        create: {
          currentStage: "开篇",
          currentGoal: firstChapterGoal || null,
        },
      },
      writingBible: {
        create: {
          storyLengthProfile,
          targetTotalWordCount,
          genre: genre || null,
          coreSellingPoint: coreSellingPoint || null,
          readerPromise: readerPromise || null,
          notes: writingBibleNotes || null,
        },
      },
    },
    include: {
      chapters: {
        orderBy: {
          order: "asc",
        },
      },
    },
  });

  revalidatePath("/");

  return { novelId: novel.id, chapterId: novel.chapters[0]?.id ?? null };
}

export async function createChapterAction(novelId: string) {
  await requireNovelAccess(novelId);

  const lastChapter = await prisma.chapter.findFirst({
    where: { novelId },
    orderBy: { order: "desc" },
  });

  const nextOrder = (lastChapter?.order ?? 0) + 1;

  const chapter = await prisma.chapter.create({
    data: {
      novelId,
      title: `第 ${nextOrder} 章`,
      order: nextOrder,
    },
  });

  revalidatePath(`/workspace/${novelId}`);

  return chapter.id;
}

export async function saveChapterDraftAction(input: {
  chapterId: string;
  title: string;
  content: string;
}) {
  await requireChapterAccess(input.chapterId);

  const chapter = await prisma.chapter.update({
    where: { id: input.chapterId },
    data: {
      title: input.title.trim() || "未命名章节",
      content: input.content,
    },
  });

  return {
    updatedAt: chapter.updatedAt.toISOString(),
  };
}

/** 从共享契约导入（唯一来源） */
const DEFAULT_CHAPTER_QUALITY_CHECKS = QUALITY_CHECK_DEFINITIONS.map((d) => ({
  type: d.type,
  title: d.title,
  summary: d.summary,
})) as readonly { type: QualityCheckType; title: string; summary: string }[];

export async function setChapterStatusAction(input: {
  chapterId: string;
  status: "drafting" | "review" | "completed";
}) {
  await requireChapterAccess(input.chapterId);

  if (input.status === "completed") {
    const consistencyCheck = await prisma.chapterQualityCheck.findUnique({
      where: {
        chapterId_type: {
          chapterId: input.chapterId,
          type: "consistency",
        },
      },
      select: { status: true },
    });
    if (!consistencyCheck || !["completed", "skipped"].includes(consistencyCheck.status)) {
      throw new Error("一致性终检完成或跳过后，才能标记章节完成。");
    }
  }

  const chapter = await prisma.chapter.update({
    where: { id: input.chapterId },
    data: {
      status: input.status,
      completedAt: input.status === "completed" ? new Date() : null,
    },
    select: { novelId: true },
  });

  if (input.status === "review" || input.status === "completed") {
    await Promise.all(
      DEFAULT_CHAPTER_QUALITY_CHECKS.map((check) =>
        prisma.chapterQualityCheck.upsert({
          where: {
            chapterId_type: {
              chapterId: input.chapterId,
              type: check.type,
            },
          },
          update: {
            title: check.title,
            summary: check.summary,
          },
          create: {
            chapterId: input.chapterId,
            type: check.type,
            title: check.title,
            summary: check.summary,
          },
        })
      )
    );
  }

  revalidatePath(`/workspace/${chapter.novelId}`);
}

export async function updateChapterQualityCheckStatusAction(input: {
  id: string;
  status: "pending" | "skipped";
  resetResult?: boolean;
}) {
  // P1 安全：校验登录 + 检查项归属
  const check = await prisma.chapterQualityCheck.findUnique({
    where: { id: input.id },
    include: { chapter: { select: { novelId: true, novel: { select: { userId: true } } } } },
  });
  if (!check) throw new Error("检查项不存在");
  await requireNovelAccess(check.chapter.novelId);

  // Phase 1：收窄——只允许状态变更，不允许直接写评分
  await prisma.chapterQualityCheck.update({
    where: { id: input.id },
    data: {
      status: input.status,
      ...(input.resetResult ? {
        result: null,
        scoreHook: null, scoreTension: null, scorePayoff: null,
        scorePacing: null, scoreEndingHook: null, scoreReaderPromise: null,
        scoreOverall: null, qualityGate: null, rewriteBrief: null,
      } : {}),
    },
  });

  revalidatePath(`/workspace/${check.chapter.novelId}`);
}

// ============================================
// 设定相关 - 角色
// ============================================

export async function createCharacterAction(input: {
  novelId: string;
  name: string;
  aliases?: string;
  gender?: string;
  age?: string;
  appearance?: string;
  personality?: string;
  identity?: string;
  background?: string;
  coreDesire?: string;
  behaviorBoundaries?: string;
  speechStyle?: string;
  relationshipPrinciples?: string;
  shortTermGoal?: string;
  factionId?: string;
  // 新增：实力相关
  powerLevel?: string;
  combatAbility?: string;
  specialSkills?: string;
  // 新增：当前状态
  currentStatus?: string;
  statusNote?: string;
}): Promise<string | undefined> {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  const character = await prisma.character.create({
    data: {
      novelId: input.novelId,
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      gender: input.gender?.trim() || null,
      age: input.age?.trim() || null,
      appearance: input.appearance?.trim() || null,
      personality: input.personality?.trim() || null,
      identity: input.identity?.trim() || null,
      background: input.background?.trim() || null,
      coreDesire: input.coreDesire?.trim() || null,
      behaviorBoundaries: input.behaviorBoundaries?.trim() || null,
      speechStyle: input.speechStyle?.trim() || null,
      relationshipPrinciples: input.relationshipPrinciples?.trim() || null,
      shortTermGoal: input.shortTermGoal?.trim() || null,
      factionId: input.factionId?.trim() || null,
      // 新增字段
      powerLevel: input.powerLevel?.trim() || null,
      combatAbility: input.combatAbility?.trim() || null,
      specialSkills: input.specialSkills?.trim() || null,
      currentStatus: (input.currentStatus as "active" | "missing" | "dead" | "imprisoned" | "unknown") || "active",
      statusNote: input.statusNote?.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);

  return character.id;
}

export async function updateCharacterAction(input: {
  id: string;
  novelId: string;
  name: string;
  aliases?: string;
  gender?: string;
  age?: string;
  appearance?: string;
  personality?: string;
  identity?: string;
  background?: string;
  coreDesire?: string;
  behaviorBoundaries?: string;
  speechStyle?: string;
  relationshipPrinciples?: string;
  shortTermGoal?: string;
  factionId?: string;
  // 新增：实力相关
  powerLevel?: string;
  combatAbility?: string;
  specialSkills?: string;
  // 新增：当前状态
  currentStatus?: string;
  statusNote?: string;
}) {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  const result = await prisma.character.updateMany({
    where: { id: input.id, novelId: input.novelId },
    data: {
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      gender: input.gender?.trim() || null,
      age: input.age?.trim() || null,
      appearance: input.appearance?.trim() || null,
      personality: input.personality?.trim() || null,
      identity: input.identity?.trim() || null,
      background: input.background?.trim() || null,
      coreDesire: input.coreDesire?.trim() || null,
      behaviorBoundaries: input.behaviorBoundaries?.trim() || null,
      speechStyle: input.speechStyle?.trim() || null,
      relationshipPrinciples: input.relationshipPrinciples?.trim() || null,
      shortTermGoal: input.shortTermGoal?.trim() || null,
      factionId: input.factionId?.trim() || null,
      // 新增字段
      powerLevel: input.powerLevel?.trim() || null,
      combatAbility: input.combatAbility?.trim() || null,
      specialSkills: input.specialSkills?.trim() || null,
      currentStatus: (input.currentStatus as "active" | "missing" | "dead" | "imprisoned" | "unknown") || "active",
      statusNote: input.statusNote?.trim() || null,
    },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function deleteCharacterAction(input: {
  id: string;
  novelId: string;
}) {
  await requireNovelAccess(input.novelId);

  const result = await prisma.character.deleteMany({
    where: { id: input.id, novelId: input.novelId },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 设定相关 - 角色经历
// ============================================

export async function createCharacterExperienceAction(input: {
  characterId: string;
  chapterId?: string;
  content: string;
  order?: number;
}) {
  if (!input.content.trim()) {
    return;
  }
  await requireCharacterAccess(input.characterId);

  // 获取当前最大 order
  const maxOrder = await prisma.characterExperience.findFirst({
    where: { characterId: input.characterId },
    orderBy: { order: "desc" },
    select: { order: true },
  });

  const nextOrder = input.order ?? (maxOrder?.order ?? -1) + 1;

  const experience = await prisma.characterExperience.create({
    data: {
      characterId: input.characterId,
      chapterId: input.chapterId?.trim() || null,
      content: input.content.trim(),
      order: nextOrder,
    },
  });

  return experience.id;
}

export async function updateCharacterExperienceAction(input: {
  id: string;
  chapterId?: string;
  content: string;
  order?: number;
}) {
  if (!input.content.trim()) {
    return;
  }
  await requireCharacterExperienceAccess(input.id);

  await prisma.characterExperience.update({
    where: { id: input.id },
    data: {
      chapterId: input.chapterId?.trim() || null,
      content: input.content.trim(),
      order: input.order,
    },
  });
}

export async function deleteCharacterExperienceAction(input: {
  id: string;
}) {
  await requireCharacterExperienceAccess(input.id);

  await prisma.characterExperience.delete({
    where: { id: input.id },
  });
}

// ============================================
// 设定相关 - 人物关系
// ============================================

export async function createCharacterRelationAction(input: {
  characterId: string;
  targetId: string;
  relationType: string;
  description?: string;
  // 新增字段
  intimacy?: number;
  startDate?: string;
  endDate?: string;
}) {
  if (!input.relationType.trim()) {
    return;
  }
  const [sourceNovelId, target] = await Promise.all([
    requireCharacterAccess(input.characterId),
    prisma.character.findUnique({
      where: { id: input.targetId },
      select: { novelId: true },
    }),
  ]);
  if (!target) throw new Error("目标角色不存在");
  await assertSameNovel(sourceNovelId, target.novelId, "人物关系不能跨小说创建");

  await prisma.characterRelation.create({
    data: {
      characterId: input.characterId,
      targetId: input.targetId,
      relationType: input.relationType.trim() as any,
      description: input.description?.trim() || null,
      intimacy: input.intimacy ?? 0,
      startDate: input.startDate?.trim() || null,
      endDate: input.endDate?.trim() || null,
    },
  });

  // 获取 novelId 用于 revalidate
  const character = await prisma.character.findUnique({
    where: { id: input.characterId },
    select: { novelId: true },
  });

  if (character) {
    revalidatePath(`/workspace/${character.novelId}`);
  }
}

export async function updateCharacterRelationAction(input: {
  id: string;
  novelId: string;
  relationType: string;
  description?: string;
  intimacy?: number;
  startDate?: string;
  endDate?: string;
}) {
  const novelId = await requireCharacterRelationAccess(input.id);
  await assertSameNovel(input.novelId, novelId);

  await prisma.characterRelation.update({
    where: { id: input.id },
    data: {
      relationType: input.relationType.trim() as any,
      description: input.description?.trim() || null,
      intimacy: input.intimacy ?? 0,
      startDate: input.startDate?.trim() || null,
      endDate: input.endDate?.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function deleteCharacterRelationAction(input: {
  id: string;
  novelId: string;
}) {
  const novelId = await requireCharacterRelationAccess(input.id);
  await assertSameNovel(input.novelId, novelId);

  await prisma.characterRelation.delete({
    where: { id: input.id },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 设定相关 - 物品
// ============================================

export async function createItemAction(input: {
  novelId: string;
  name: string;
  aliases?: string;
  type?: string;
  rarity?: string;
  effect?: string;
  origin?: string;
  description?: string;
  ownerId?: string;
}) {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  await prisma.item.create({
    data: {
      novelId: input.novelId,
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      type: input.type?.trim() || null,
      rarity: input.rarity?.trim() || null,
      effect: input.effect?.trim() || null,
      origin: input.origin?.trim() || null,
      description: input.description?.trim() || null,
      ownerId: input.ownerId?.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function updateItemAction(input: {
  id: string;
  novelId: string;
  name: string;
  aliases?: string;
  type?: string;
  rarity?: string;
  effect?: string;
  origin?: string;
  description?: string;
  ownerId?: string;
}) {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  const result = await prisma.item.updateMany({
    where: { id: input.id, novelId: input.novelId },
    data: {
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      type: input.type?.trim() || null,
      rarity: input.rarity?.trim() || null,
      effect: input.effect?.trim() || null,
      origin: input.origin?.trim() || null,
      description: input.description?.trim() || null,
      ownerId: input.ownerId?.trim() || null,
    },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function deleteItemAction(input: {
  id: string;
  novelId: string;
}) {
  await requireNovelAccess(input.novelId);

  const result = await prisma.item.deleteMany({
    where: { id: input.id, novelId: input.novelId },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 设定相关 - 地点
// ============================================

export async function createLocationAction(input: {
  novelId: string;
  name: string;
  aliases?: string;
  type?: string;
  parentId?: string;
  climate?: string;
  culture?: string;
  description?: string;
}) {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  await prisma.location.create({
    data: {
      novelId: input.novelId,
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      type: input.type?.trim() || null,
      parentId: input.parentId?.trim() || null,
      climate: input.climate?.trim() || null,
      culture: input.culture?.trim() || null,
      description: input.description?.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function updateLocationAction(input: {
  id: string;
  novelId: string;
  name: string;
  aliases?: string;
  type?: string;
  parentId?: string;
  climate?: string;
  culture?: string;
  description?: string;
}) {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  const result = await prisma.location.updateMany({
    where: { id: input.id, novelId: input.novelId },
    data: {
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      type: input.type?.trim() || null,
      parentId: input.parentId?.trim() || null,
      climate: input.climate?.trim() || null,
      culture: input.culture?.trim() || null,
      description: input.description?.trim() || null,
    },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function deleteLocationAction(input: {
  id: string;
  novelId: string;
}) {
  await requireNovelAccess(input.novelId);

  const result = await prisma.location.deleteMany({
    where: { id: input.id, novelId: input.novelId },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 设定相关 - 势力
// ============================================

export async function createFactionAction(input: {
  novelId: string;
  name: string;
  aliases?: string;
  type?: string;
  baseId?: string;
  description?: string;
}) {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  await prisma.faction.create({
    data: {
      novelId: input.novelId,
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      type: input.type?.trim() || null,
      baseId: input.baseId?.trim() || null,
      description: input.description?.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function updateFactionAction(input: {
  id: string;
  novelId: string;
  name: string;
  aliases?: string;
  type?: string;
  baseId?: string;
  description?: string;
}) {
  if (!input.name.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  const result = await prisma.faction.updateMany({
    where: { id: input.id, novelId: input.novelId },
    data: {
      name: input.name.trim(),
      aliases: input.aliases?.trim() || null,
      type: input.type?.trim() || null,
      baseId: input.baseId?.trim() || null,
      description: input.description?.trim() || null,
    },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function deleteFactionAction(input: {
  id: string;
  novelId: string;
}) {
  await requireNovelAccess(input.novelId);

  const result = await prisma.faction.deleteMany({
    where: { id: input.id, novelId: input.novelId },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 设定相关 - 术语
// ============================================

export async function createGlossaryAction(input: {
  novelId: string;
  term: string;
  definition: string;
  category?: string;
}) {
  if (!input.term.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  await prisma.glossary.create({
    data: {
      novelId: input.novelId,
      term: input.term.trim(),
      definition: input.definition.trim(),
      category: input.category?.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function updateGlossaryAction(input: {
  id: string;
  novelId: string;
  term: string;
  definition: string;
  category?: string;
}) {
  if (!input.term.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  const result = await prisma.glossary.updateMany({
    where: { id: input.id, novelId: input.novelId },
    data: {
      term: input.term.trim(),
      definition: input.definition.trim(),
      category: input.category?.trim() || null,
    },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function deleteGlossaryAction(input: {
  id: string;
  novelId: string;
}) {
  await requireNovelAccess(input.novelId);

  const result = await prisma.glossary.deleteMany({
    where: { id: input.id, novelId: input.novelId },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 设定相关 - 故事基础背景
// ============================================

export async function updateStoryBackgroundAction(input: {
  novelId: string;
  content: string;
}) {
  await requireNovelAccess(input.novelId);

  await prisma.storyBackground.upsert({
    where: { novelId: input.novelId },
    update: {
      content: input.content,
    },
    create: {
      novelId: input.novelId,
      content: input.content,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 设定相关 - 世界设定
// ============================================

export async function updateWorldSettingAction(input: {
  novelId: string;
  content: string;
}) {
  await requireNovelAccess(input.novelId);

  await prisma.worldSetting.upsert({
    where: { novelId: input.novelId },
    update: {
      content: input.content,
    },
    create: {
      novelId: input.novelId,
      content: input.content,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function updateWritingBibleAction(input: {
  novelId: string;
  storyLengthProfile?: string;
  targetTotalWordCount?: string | number | null;
  genre?: string;
  targetReaders?: string;
  coreSellingPoint?: string;
  readerPromise?: string;
  appealModel?: string;
  taboo?: string;
  comparableTitles?: string;
  notes?: string;
}) {
  await requireNovelAccess(input.novelId);
  const storyLengthProfile = normalizeStoryLengthProfile(input.storyLengthProfile ?? DEFAULT_STORY_LENGTH_PROFILE);
  const targetTotalWordCount = parsePositiveInt(input.targetTotalWordCount);

  await prisma.writingBible.upsert({
    where: { novelId: input.novelId },
    update: {
      storyLengthProfile,
      targetTotalWordCount,
      genre: input.genre?.trim() || null,
      targetReaders: input.targetReaders?.trim() || null,
      coreSellingPoint: input.coreSellingPoint?.trim() || null,
      readerPromise: input.readerPromise?.trim() || null,
      appealModel: input.appealModel?.trim() || null,
      taboo: input.taboo?.trim() || null,
      comparableTitles: input.comparableTitles?.trim() || null,
      notes: input.notes?.trim() || null,
    },
    create: {
      novelId: input.novelId,
      storyLengthProfile,
      targetTotalWordCount: targetTotalWordCount ?? STORY_LENGTH_PROFILE_CONFIG[storyLengthProfile].targetWords[1],
      genre: input.genre?.trim() || null,
      targetReaders: input.targetReaders?.trim() || null,
      coreSellingPoint: input.coreSellingPoint?.trim() || null,
      readerPromise: input.readerPromise?.trim() || null,
      appealModel: input.appealModel?.trim() || null,
      taboo: input.taboo?.trim() || null,
      comparableTitles: input.comparableTitles?.trim() || null,
      notes: input.notes?.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 故事进展相关
// ============================================

export async function updateStoryProgressAction(input: {
  novelId: string;
  content: string;
}) {
  await requireNovelAccess(input.novelId);

  // 限制最多3万字
  const content = input.content.slice(0, 30000);

  await prisma.novel.update({
    where: { id: input.novelId },
    data: {
      storyProgress: content,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 章节进展相关
// ============================================

export async function updateChapterProgressAction(input: {
  chapterId: string;
  content: string;
}) {
  await requireChapterAccess(input.chapterId);

  await prisma.chapterProgress.upsert({
    where: { chapterId: input.chapterId },
    update: {
      content: input.content,
    },
    create: {
      chapterId: input.chapterId,
      content: input.content,
    },
  });

  // 获取 novelId 用于 revalidate
  const chapter = await prisma.chapter.findUnique({
    where: { id: input.chapterId },
    select: { novelId: true },
  });

  if (chapter) {
    revalidatePath(`/workspace/${chapter.novelId}`);
  }
}

// ============================================
// 大纲相关
// ============================================

/**
 * 更新大纲内容
 */
export async function updateOutlineAction(input: {
  novelId: string;
  content: string;
}) {
  await requireNovelAccess(input.novelId);

  await prisma.outline.upsert({
    where: { novelId: input.novelId },
    update: {
      content: input.content,
    },
    create: {
      novelId: input.novelId,
      content: input.content,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function createOutlineNodeAction(input: {
  novelId: string;
  title: string;
  content?: string;
  kind: OutlineNodeKind;
  parentId?: string | null;
  status?: OutlineNodeStatus;
  estimatedWordCount?: number | null;
  actualWordCount?: number | null;
}) {
  const title = input.title.trim();
  if (!title) throw new Error("节点标题不能为空");
  await requireNovelAccess(input.novelId);

  const kind = normalizeOutlineNodeKind(input.kind);
  const parentId = kind === "stage" ? null : input.parentId?.trim() || null;
  await assertOutlineParentAllowed({ novelId: input.novelId, kind, parentId });

  const siblingCount = await prisma.outlineNode.count({
    where: { novelId: input.novelId, parentId },
  });

  await prisma.outlineNode.create({
    data: {
      novelId: input.novelId,
      title,
      content: input.content?.trim() || null,
      kind,
      parentId,
      status: normalizeOutlineNodeStatus(input.status),
      estimatedWordCount: input.estimatedWordCount ?? null,
      actualWordCount: input.actualWordCount ?? null,
      order: siblingCount,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function updateOutlineNodeAction(input: {
  id: string;
  novelId: string;
  title: string;
  content?: string;
  kind: OutlineNodeKind;
  parentId?: string | null;
  status?: OutlineNodeStatus;
  estimatedWordCount?: number | null;
  actualWordCount?: number | null;
}) {
  const title = input.title.trim();
  if (!title) throw new Error("节点标题不能为空");
  await requireNovelAccess(input.novelId);

  const existing = await prisma.outlineNode.findFirst({
    where: { id: input.id, novelId: input.novelId },
    select: { id: true },
  });
  if (!existing) throw new Error("大纲节点不存在或无权访问");

  const kind = normalizeOutlineNodeKind(input.kind);
  const parentId = kind === "stage" ? null : input.parentId?.trim() || null;
  await assertOutlineParentAllowed({ novelId: input.novelId, kind, parentId, selfId: input.id });
  await assertOutlineChildrenAllowed({ nodeId: input.id, nextKind: kind });

  await prisma.outlineNode.update({
    where: { id: input.id },
    data: {
      title,
      content: input.content?.trim() || null,
      kind,
      parentId,
      status: normalizeOutlineNodeStatus(input.status),
      estimatedWordCount: input.estimatedWordCount ?? null,
      actualWordCount: input.actualWordCount ?? null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

export async function deleteOutlineNodeAction(input: {
  id: string;
  novelId: string;
}) {
  await requireNovelAccess(input.novelId);

  const childCount = await prisma.outlineNode.count({ where: { parentId: input.id } });
  if (childCount > 0) {
    throw new Error("该大纲节点仍有子节点，请先删除或移动子节点");
  }

  const result = await prisma.outlineNode.deleteMany({
    where: { id: input.id, novelId: input.novelId },
  });
  assertUpdated(result.count);

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 剧情进度相关
// ============================================

export async function updatePlotProgressAction(input: {
  novelId: string;
  currentStage: string;
  currentGoal: string;
  currentConflict: string;
  nextMilestone: string;
}) {
  await requireNovelAccess(input.novelId);

  await prisma.plotProgress.upsert({
    where: { novelId: input.novelId },
    update: {
      currentStage: input.currentStage.trim() || "开篇",
      currentGoal: input.currentGoal.trim() || null,
      currentConflict: input.currentConflict.trim() || null,
      nextMilestone: input.nextMilestone.trim() || null,
    },
    create: {
      novelId: input.novelId,
      currentStage: input.currentStage.trim() || "开篇",
      currentGoal: input.currentGoal.trim() || null,
      currentConflict: input.currentConflict.trim() || null,
      nextMilestone: input.nextMilestone.trim() || null,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 参考资料相关
// ============================================

export async function createReferenceMaterialAction(input: {
  novelId: string;
  title: string;
  type: ReferenceMaterialType;
  content: string;
  sourceUrl?: string;
}) {
  if (!input.title.trim()) {
    return;
  }
  await requireNovelAccess(input.novelId);

  const reference = await prisma.referenceMaterial.create({
    data: {
      novelId: input.novelId,
      title: input.title.trim(),
      type: input.type,
      content: input.content.trim(),
      sourceUrl: input.sourceUrl?.trim() || null,
    },
  });

  try {
    await upsertReferenceMaterialRagIndex(reference.id);
  } catch (error) {
    console.error("upsertReferenceMaterialRagIndex error:", error);
  }

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 文风相关
// ============================================

/**
 * 创建空白文风（用于后续上传参考资料）
 */
export async function createWritingStyleAction(input: {
  name: string;
}): Promise<{ styleId: string }> {
  await requireCurrentSession();

  if (!input.name.trim()) {
    throw new Error("文风名称不能为空");
  }

  const style = await prisma.writingStyle.create({
    data: {
      name: input.name.trim(),
      sourceType: "agent",
    },
  });

  revalidatePath("/styles");

  return { styleId: style.id };
}

/**
 * 上传 txt 参考资料文件
 */
export async function uploadStyleReferenceAction(input: {
  styleId: string;
  filename: string;
  content: string;
}): Promise<{ success: true; referenceId: string; charCount: number } | { success: false; error: string }> {
  try {
    await requireCurrentSession();

    if (!input.filename.endsWith(".txt")) {
      return { success: false, error: "只支持 .txt 文件" };
    }

    if (!input.content.trim()) {
      return { success: false, error: "文件内容为空" };
    }

    // 检查文件大小（50MB 限制）
    const contentSizeMB = Buffer.byteLength(input.content, "utf-8") / (1024 * 1024);
    if (contentSizeMB > 50) {
      return { success: false, error: `文件过大（${contentSizeMB.toFixed(1)}MB），最大支持 50MB` };
    }

    // 创建存储目录
    const uploadsDir = path.join(process.cwd(), "uploads", "styles", input.styleId);
    await fs.mkdir(uploadsDir, { recursive: true });

    // 生成文件路径
    const referenceId = `ref_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const safeFilename = `${referenceId}_${input.filename.replace(/[^\w\u4e00-\u9fa5.-]/g, "_")}`;
    const filepath = path.join(uploadsDir, safeFilename);

    // 写入文件
    await fs.writeFile(filepath, input.content, "utf-8");

    // 计算字符数（去除空白）
    const charCount = input.content.replace(/\s+/g, "").length;

    // 创建数据库记录
    const reference = await prisma.styleReference.create({
      data: {
        styleId: input.styleId,
        filename: input.filename,
        filepath,
        charCount,
        status: "ready",
      },
    });

    revalidatePath("/styles");

    return { success: true, referenceId: reference.id, charCount };
  } catch (error) {
    console.error("uploadStyleReferenceAction error:", error);
    return { success: false, error: error instanceof Error ? error.message : "上传失败" };
  }
}

/**
 * 删除参考资料
 */
export async function deleteStyleReferenceAction(input: {
  styleId: string;
  referenceId: string;
}): Promise<void> {
  await requireCurrentSession();

  const reference = await prisma.styleReference.findUnique({
    where: { id: input.referenceId },
  });

  if (reference && reference.styleId === input.styleId) {
    // 删除文件
    try {
      await fs.unlink(reference.filepath);
    } catch {
      // 文件可能已不存在
    }

    // 删除数据库记录
    await prisma.styleReference.delete({
      where: { id: input.referenceId },
    });
  }

  revalidatePath("/styles");
}

/**
 * 删除文风（及其所有参考资料和任务）
 */
export async function deleteWritingStyleAction(input: {
  styleId: string;
}): Promise<void> {
  await requireCurrentSession();

  // 获取所有参考资料
  const references = await prisma.styleReference.findMany({
    where: { styleId: input.styleId },
  });

  // 删除所有文件
  for (const ref of references) {
    try {
      await fs.unlink(ref.filepath);
    } catch {
      // 文件可能已不存在
    }
  }

  // 删除数据库记录（级联删除）
  await prisma.writingStyle.delete({
    where: { id: input.styleId },
  });

  revalidatePath("/styles");
  revalidatePath("/");
}

/**
 * 生成文风画像
 * 流程：
 * 1. 创建任务记录，返回 taskId
 * 2. 异步执行画像生成（不阻塞请求）
 * 3. 前端轮询 getPortraitTaskStatusAction 检查状态
 * 4. 任务完成后前端自动刷新页面
 */
export async function generatePortraitAction(input: {
  styleId: string;
}): Promise<{ taskId: string }> {
  const session = await requireCurrentSession();

  // 检查是否有参考资料
  const references = await prisma.styleReference.findMany({
    where: {
      styleId: input.styleId,
      status: "ready",
    },
  });

  if (references.length === 0) {
    throw new Error("请先上传参考资料");
  }

  // 创建任务
  const task = await prisma.stylePortraitTask.create({
    data: {
      styleId: input.styleId,
      status: "processing",
    },
  });

  // 更新文风状态
  await prisma.writingStyle.update({
    where: { id: input.styleId },
    data: {
      errorMessage: null,
    },
  });

  // 异步执行画像生成（不等待结果，前端会轮询状态）
  void generatePortraitAsync(input.styleId, task.id, session.userId);

  return { taskId: task.id };
}

/**
 * 异步画像生成（内部函数）
 * 完成后只更新数据库，不调用 revalidatePath
 * 前端通过轮询 getPortraitTaskStatusAction 获取状态并自行刷新
 */
async function generatePortraitAsync(
  styleId: string,
  taskId: string,
  userId: string
): Promise<void> {
  try {
    // 获取所有参考资料
    const references = await prisma.styleReference.findMany({
      where: {
        styleId,
        status: "ready",
      },
    });

    if (references.length === 0) {
      throw new Error("没有可用的参考资料");
    }

    // 读取所有文件内容
    const texts: string[] = [];
    let totalCharCount = 0;

    for (const ref of references) {
      const content = await fs.readFile(ref.filepath, "utf-8");
      texts.push(`参考资料：${ref.filename}\n\n${content}`);
      totalCharCount += ref.charCount;
    }

    const sourceText = texts.join("\n\n");

    // 调用 Agent 生成画像
    const agent = await createPortraitAgent();
    const result = await agent.generatePortrait(sourceText, {
      userId,
      agentId: "Portrait",
      note: "文风画像生成",
    });
    const portraitMarkdown = agent.getPortraitMarkdown(result);

    // 更新数据库 - 任务成功
    await prisma.$transaction([
      prisma.stylePortraitTask.update({
        where: { id: taskId },
        data: {
          status: "success",
        },
      }),
      prisma.writingStyle.update({
        where: { id: styleId },
        data: {
          creativeMethodology: result.creativeMethodology,
          uniqueMarkers: result.uniqueMarkers,
          generationStyle: result.generationStyle,
          expressionFeatures: result.expressionFeatures,
          styleTraits: result.styleTraits,
          portraitMarkdown,
          originalCharCount: totalCharCount,
          usedCharCount: result.usedCharCount,
          truncated: result.truncated,
          errorMessage: null,
        },
      }),
    ]);
  } catch (error) {
    // 更新数据库 - 任务失败
    const errorMessage = error instanceof Error ? error.message : "画像生成失败";

    await prisma.$transaction([
      prisma.stylePortraitTask.update({
        where: { id: taskId },
        data: {
          status: "error",
          errorMessage,
        },
      }),
      prisma.writingStyle.update({
        where: { id: styleId },
        data: {
          errorMessage,
        },
      }),
    ]);
  }
}

/**
 * 获取画像任务状态
 */
export async function getPortraitTaskStatusAction(input: {
  taskId: string;
}): Promise<{
  status: string;
  errorMessage?: string | null;
}> {
  await requireCurrentSession();

  const task = await prisma.stylePortraitTask.findUnique({
    where: { id: input.taskId },
  });

  if (!task) {
    throw new Error("任务不存在");
  }

  return {
    status: task.status,
    errorMessage: task.errorMessage,
  };
}

/**
 * 应用文风到小说
 */
export async function applyWritingStyleAction(input: {
  novelId: string;
  styleId: string;
}) {
  await requireNovelAccess(input.novelId);

  await prisma.novel.update({
    where: { id: input.novelId },
    data: {
      appliedStyleId: input.styleId,
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
}

// ============================================
// 文风画像编辑
// ============================================

type PortraitSectionKey = "creativeMethodology" | "uniqueMarkers" | "generationStyle" | "expressionFeatures" | "styleTraits";

/**
 * 更新文风画像单个维度
 */
export async function updateStyleSectionAction(input: {
  styleId: string;
  section: PortraitSectionKey;
  content: string;
}): Promise<{ success: boolean }> {
  await requireCurrentSession();

  const { styleId, section, content } = input;

  await prisma.writingStyle.update({
    where: { id: styleId },
    data: {
      [section]: content.trim(),
    },
  });

  revalidatePath("/styles");
  return { success: true };
}

// ============================================
// 智能写作相关
// ============================================

/**
 * 获取写作配置
 */
export async function getWritingConfigAction(input: {
  novelId: string;
}): Promise<{
  defaultWordCount: number;
  enabledAgents: string[];
}> {
  await requireNovelAccess(input.novelId);

  const config = await prisma.writingConfig.findUnique({
    where: { novelId: input.novelId },
  });

  if (config) {
    return {
      defaultWordCount: config.defaultWordCount,
      enabledAgents: config.enabledAgents.split(",").filter(Boolean),
    };
  }

  return {
    defaultWordCount: 4000,
    enabledAgents: [...DEFAULT_ENABLED_AGENTS],
  };
}

/**
 * 更新写作配置
 */
export async function updateWritingConfigAction(input: {
  novelId: string;
  defaultWordCount?: number;
  enabledAgents?: string[];
}): Promise<{ success: boolean }> {
  await requireNovelAccess(input.novelId);

  await prisma.writingConfig.upsert({
    where: { novelId: input.novelId },
    create: {
      novelId: input.novelId,
      defaultWordCount: input.defaultWordCount ?? 4000,
      enabledAgents: input.enabledAgents?.join(",") ?? DEFAULT_ENABLED_AGENTS_STRING,
    },
    update: {
      ...(input.defaultWordCount !== undefined && {
        defaultWordCount: input.defaultWordCount,
      }),
      ...(input.enabledAgents && { enabledAgents: input.enabledAgents.join(",") }),
    },
  });

  revalidatePath(`/workspace/${input.novelId}`);
  return { success: true };
}

/**
 * 获取写作任务
 */
export async function getWritingTaskAction(input: {
  taskId: string;
}): Promise<{
  task: {
    id: string;
    phase: string;
    targetWordCount: number;
    selectedAgents: string[];
    generatedContent: string | null;
    agentOutputs: Record<string, unknown> | null;
  } | null;
}> {
  // Phase 1.1: 鉴权
  const session = await getSession();
  if (!session) throw new Error("未登录");
  const auth = await authorizeWritingTask(input.taskId, session.userId);
  if (!auth.authorized) throw new Error(auth.reason ?? "无权访问该任务");

  const task = await prisma.writingTask.findUnique({
    where: { id: input.taskId },
  });

  if (!task) {
    return { task: null };
  }

  return {
    task: {
      id: task.id,
      phase: task.phase,
      targetWordCount: task.targetWordCount,
      selectedAgents: task.selectedAgents.split(",").filter(Boolean),
      generatedContent: task.generatedContent,
      agentOutputs: task.agentOutputs ? JSON.parse(task.agentOutputs) : null,
    },
  };
}

/**
 * 确认规划阶段
 */
export async function confirmPlanningAction(input: {
  taskId: string;
  accepted: boolean;
  feedback?: string;
}): Promise<{ success: boolean }> {
  // Phase 1.1: 鉴权
  const session = await getSession();
  if (!session) throw new Error("未登录");
  const auth = await authorizeWritingTask(input.taskId, session.userId);
  if (!auth.authorized) throw new Error(auth.reason ?? "无权访问该任务");

  await prisma.writingTask.update({
    where: { id: input.taskId },
    data: {
      phase: input.accepted ? "active" : "waiting_call",
    },
  });

  return { success: true };
}

/**
 * 采纳生成内容
 *
 * P0 修复：强制使用 task.chapterId，不再信任前端传入的 chapterId。
 * 防止攻击者用自己的 taskId 将生成内容写入他人的章节。
 */
export async function acceptGeneratedContentAction(input: {
  taskId: string;
  chapterId: string;
}): Promise<{ success: boolean; newWordCount: number }> {
  // Phase 1.1: 鉴权
  const session = await getSession();
  if (!session) throw new Error("未登录");
  const auth = await authorizeWritingTask(input.taskId, session.userId);
  if (!auth.authorized) throw new Error(auth.reason ?? "无权访问该任务");

  const task = await prisma.writingTask.findUnique({
    where: { id: input.taskId },
    include: { novel: { select: { userId: true } } },
  });

  if (!task?.generatedContent) {
    throw new Error("没有可用的生成内容");
  }
  const snapshot = deserializeGraphStateSnapshot(task.graphStateJson);
  const activeArtifactId = snapshot?.artifactReview.activeArtifactId ?? snapshot?.activeArtifactId ?? null;
  if (task.phase === "awaiting_user_review" || task.generatedContent === activeArtifactId) {
    throw new Error("当前内容是待审核草案，请通过草案审核卡片确认应用。");
  }

  // P0：校验前端传入的 chapterId 必须与 task.chapterId 一致
  if (input.chapterId !== task.chapterId) {
    throw new Error("章节不匹配：传入的 chapterId 与任务所属章节不一致");
  }

  const chapter = await prisma.chapter.findUnique({
    where: { id: task.chapterId },
  });

  if (!chapter) {
    throw new Error("章节不存在");
  }

  // 追加生成内容到正文
  const newContent = `${chapter.content.trimEnd()}\n\n${task.generatedContent.trim()}`;
  const newWordCount = newContent.length;

  await prisma.$transaction([
    prisma.chapter.update({
      where: { id: task.chapterId },
      data: { content: newContent },
    }),
    prisma.writingTask.update({
      where: { id: input.taskId },
      data: {
        finalContent: task.generatedContent,
        phase: "completed",
      },
    }),
  ]);

  revalidatePath(`/workspace/${task.novelId}`);
  return { success: true, newWordCount };
}

/**
 * 执行数据更新（记录员 Agent 的输出）
 * 使用统一的 db-operations 模块，支持事务和回滚
 */
export async function persistUpdatesAction(input: {
  taskId: string;
  updates: {
    foreshadowing?: Array<{
      action: string;
      name: string;
      id?: string;
      plantedAt?: string;
      plantedContent?: string;
      expectedPayoff?: string;
    }>;
    outline?: Array<{
      nodeId: string;
      status: string;
      actualWordCount?: number;
    }>;
    outlineAdjustments?: Array<{
      action: string;
      nodeId?: string;
      title: string;
      content?: string;
      parentId?: string;
      status?: string;
    }>;
    characters?: Array<{
      action: string;
      characterId?: string;
      id?: string;
      name: string;
      aliases?: string;
      identity?: string;
      personality?: string;
      appearance?: string;
      background?: string;
      coreDesire?: string;
      behaviorBoundaries?: string;
      speechStyle?: string;
      relationshipPrinciples?: string;
      shortTermGoal?: string;
      gender?: string;
      age?: string;
      factionId?: string;
      powerLevel?: string;
      combatAbility?: string;
      specialSkills?: string;
      currentStatus?: string;
      statusNote?: string;
    }>;
    characterExperiences?: Array<{
      action: string;
      id?: string;
      characterId?: string;
      characterName?: string;
      chapterId?: string;
      chapterTitle?: string;
      content: string;
      order?: number;
    }>;
    locations?: Array<{
      action: string;
      locationId?: string;
      id?: string;
      name: string;
      aliases?: string;
      type?: string;
      parentId?: string;
      description?: string;
      climate?: string;
      culture?: string;
    }>;
    items?: Array<{
      action: string;
      itemId?: string;
      id?: string;
      name: string;
      aliases?: string;
      type?: string;
      rarity?: string;
      effect?: string;
      origin?: string;
      description?: string;
      ownerId?: string;
    }>;
    factions?: Array<{
      action: string;
      factionId?: string;
      id?: string;
      name: string;
      aliases?: string;
      type?: string;
      baseId?: string;
      description?: string;
    }>;
    glossaries?: Array<{
      action: string;
      glossaryId?: string;
      term: string;
      definition: string;
      category?: string;
    }>;
    references?: Array<{
      action: string;
      referenceId?: string;
      title: string;
      type?: string;
      content?: string;
    }>;
    worldSetting?: string;
    storyBackground?: string;
  };
}): Promise<{ success: boolean; summary: string; errors?: string[] }> {
  // Phase 1.1: 鉴权
  const session = await getSession();
  if (!session) throw new Error("未登录");
  const auth = await authorizeWritingTask(input.taskId, session.userId);
  if (!auth.authorized) throw new Error(auth.reason ?? "无权访问该任务");

  const result = await executeUpdates(input.taskId, input.updates as Parameters<typeof executeUpdates>[1]);

  if (result.success) {
    const task = await prisma.writingTask.findUnique({
      where: { id: input.taskId },
      select: { novelId: true },
    });
    if (task) {
      revalidatePath(`/workspace/${task.novelId}`);
    }
  }

  return {
    success: result.success,
    summary: result.summary,
    errors: result.errors.length > 0 ? result.errors : undefined,
  };
}

// ============================================
// 用户认证相关
// ============================================

export async function loginAction(formData: FormData): Promise<{
  success: boolean;
  error?: string;
}> {
  const username = String(formData.get("username") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");

  if (!username || !password) {
    return { success: false, error: "请输入用户名和密码" };
  }

  const user = await prisma.user.findUnique({ where: { username } });
  if (!user) {
    return { success: false, error: "用户名或密码错误" };
  }

  const valid = await verifyPassword(password, user.passwordHash);
  if (!valid) {
    return { success: false, error: "用户名或密码错误" };
  }

  // 将孤儿小说分配给当前用户
  await prisma.novel.updateMany({
    where: { userId: null },
    data: { userId: user.id },
  });

  const token = await createToken(user.id);
  await setSessionCookie(token);

  revalidatePath("/");
  return { success: true };
}

export async function registerAction(formData: FormData): Promise<{
  success: boolean;
  error?: string;
}> {
  const username = String(formData.get("username") ?? "").trim().toLowerCase();
  const password = String(formData.get("password") ?? "");
  const confirmPassword = String(formData.get("confirmPassword") ?? "");

  if (!username || !password || !confirmPassword) {
    return { success: false, error: "请输入用户名、密码和确认密码" };
  }

  if (!/^[a-z0-9_-]{3,32}$/.test(username)) {
    return { success: false, error: "用户名只能包含 3-32 位小写字母、数字、下划线或短横线" };
  }

  if (password.length < 6) {
    return { success: false, error: "密码至少 6 位" };
  }

  if (password !== confirmPassword) {
    return { success: false, error: "两次输入的密码不一致" };
  }

  try {
    const passwordHash = await hashPassword(password);
    const user = await prisma.$transaction(async (tx) => {
      const created = await tx.user.create({
        data: {
          username,
          passwordHash,
          creditBalanceMicros: SIGNUP_BONUS_MICROS,
        },
        select: { id: true, creditBalanceMicros: true },
      });

      await tx.creditLedger.create({
        data: {
          userId: created.id,
          type: "signup_bonus",
          amountMicros: SIGNUP_BONUS_MICROS,
          balanceAfterMicros: created.creditBalanceMicros,
          note: `注册赠送 ${SIGNUP_BONUS_CREDITS.toString()} 积分`,
        },
      });

      return created;
    });

    const token = await createToken(user.id);
    await setSessionCookie(token);
    revalidatePath("/");
    return { success: true };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (message.includes("Unique constraint") || message.includes("username")) {
      return { success: false, error: "用户名已存在" };
    }
    return { success: false, error: "注册失败，请稍后重试" };
  }
}

export async function logoutAction(): Promise<void> {
  await deleteSessionCookie();
  revalidatePath("/");
}

// ============================================
// Token 用量查询
// ============================================

export async function getUserTokenStatsAction(): Promise<{
  totalTokens: number;
  monthlyTokens: number;
  totalUsage: TokenUsageBreakdown;
  monthlyUsage: TokenUsageBreakdown;
}> {
  const emptyUsage = normalizeTokenUsageBreakdown();
  const session = await getSession();
  if (!session) {
    return {
      totalTokens: 0,
      monthlyTokens: 0,
      totalUsage: emptyUsage,
      monthlyUsage: emptyUsage,
    };
  }

  const userId = session.userId;
  const monthStart = new Date();
  monthStart.setDate(1);
  monthStart.setHours(0, 0, 0, 0);

  const [totalResult, monthlyResult] = await Promise.all([
    prisma.tokenUsage.aggregate({
      where: { userId },
      _sum: {
        promptTokens: true,
        cachedTokens: true,
        completionTokens: true,
        totalTokens: true,
      },
    }),
    prisma.tokenUsage.aggregate({
      where: {
        userId,
        createdAt: { gte: monthStart },
      },
      _sum: {
        promptTokens: true,
        cachedTokens: true,
        completionTokens: true,
        totalTokens: true,
      },
    }),
  ]);

  const totalUsage = normalizeTokenUsageBreakdown({
    promptTokens: totalResult._sum.promptTokens ?? 0,
    cachedTokens: totalResult._sum.cachedTokens ?? 0,
    completionTokens: totalResult._sum.completionTokens ?? 0,
    totalTokens: totalResult._sum.totalTokens ?? 0,
  });
  const monthlyUsage = normalizeTokenUsageBreakdown({
    promptTokens: monthlyResult._sum.promptTokens ?? 0,
    cachedTokens: monthlyResult._sum.cachedTokens ?? 0,
    completionTokens: monthlyResult._sum.completionTokens ?? 0,
    totalTokens: monthlyResult._sum.totalTokens ?? 0,
  });

  return {
    totalTokens: totalUsage.totalTokens,
    monthlyTokens: monthlyUsage.totalTokens,
    totalUsage,
    monthlyUsage,
  };
}

export async function getUserCreditSummaryAction(): Promise<{
  balanceMicros: string;
  balanceCredits: string;
}> {
  const session = await getSession();
  if (!session) {
    return { balanceMicros: "0", balanceCredits: "0" };
  }

  const user = await prisma.user.findUnique({
    where: { id: session.userId },
    select: { creditBalanceMicros: true },
  });

  const balanceMicros = user?.creditBalanceMicros ?? BigInt(0);
  return {
    balanceMicros: balanceMicros.toString(),
    balanceCredits: formatCreditMicros(balanceMicros),
  };
}

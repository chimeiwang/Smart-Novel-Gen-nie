/**
 * ReviewArtifact 服务。
 *
 * @module agents/artifacts/artifact-service
 * @description 管理 Agent 待审核草案的创建、修订、评审和状态流转。
 */

import { prisma } from "@/shared/db/prisma";
import type { AgentUpdates } from "@/shared/contracts/agent-updates";
import type { CoreAgentId, NovelData } from "@/agents/graph/state";
import type { BeatPlanDraft } from "@/shared/contracts/beat-plan";
import type {
  ReviewArtifactDto,
  ReviewArtifactEvaluationVerdict,
  ReviewArtifactPayload,
  ReviewArtifactStatus,
  TextReviewArtifactKind,
} from "@/shared/contracts/review-artifact";
import {
  assertReviewArtifactStatusTransition,
  ReviewArtifactPayloadSchema,
  ReviewArtifactStatusSchema,
} from "@/shared/contracts/review-artifact";
import { buildUpdateDiffs, type UpdateDiffItem } from "./artifact-diff";

type ArtifactRecord = {
  id: string;
  novelId: string;
  chapterId: string | null;
  taskId: string | null;
  workflowRunId: string | null;
  artifactKey: string | null;
  kind: string;
  status: string;
  title: string | null;
  summary: string | null;
  payloadJson: string;
  diffJson: string | null;
  createdByAgent: string | null;
  updatedByAgent: string | null;
  reviewerAgent: string | null;
  revision: number;
  createdAt: Date;
  updatedAt: Date;
  evaluations?: Array<{
    id: string;
    artifactId: string;
    revision: number;
    evaluatorAgent: string;
    verdict: string;
    summary: string;
    requiredChanges: string | null;
    createdAt: Date;
  }>;
};

function parseJson<T>(value: string | null, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function parseArtifactStatus(status: string): ReviewArtifactStatus {
  return ReviewArtifactStatusSchema.parse(status);
}

export function toReviewArtifactDto(record: ArtifactRecord): ReviewArtifactDto {
  return {
    id: record.id,
    novelId: record.novelId,
    chapterId: record.chapterId,
    taskId: record.taskId,
    workflowRunId: record.workflowRunId,
    artifactKey: record.artifactKey,
    kind: record.kind as ReviewArtifactDto["kind"],
    status: record.status as ReviewArtifactDto["status"],
    title: record.title,
    summary: record.summary,
    payload: parseJson<ReviewArtifactPayload>(record.payloadJson, {
      kind: "freeform_markdown",
      markdown: "",
    }),
    diff: parseJson<unknown>(record.diffJson, null),
    createdByAgent: record.createdByAgent as CoreAgentId | null,
    updatedByAgent: record.updatedByAgent as CoreAgentId | null,
    reviewerAgent: record.reviewerAgent as CoreAgentId | null,
    revision: record.revision,
    evaluations: record.evaluations?.map((evaluation) => ({
      id: evaluation.id,
      artifactId: evaluation.artifactId,
      revision: evaluation.revision,
      evaluatorAgent: evaluation.evaluatorAgent as CoreAgentId,
      verdict: evaluation.verdict as ReviewArtifactEvaluationVerdict,
      summary: evaluation.summary,
      requiredChanges: evaluation.requiredChanges,
      createdAt: evaluation.createdAt.toISOString(),
    })),
    createdAt: record.createdAt.toISOString(),
    updatedAt: record.updatedAt.toISOString(),
  };
}

async function loadNovelDataForArtifactDiff(input: {
  novelId: string;
  chapterId?: string | null;
  fallback?: NovelData;
}): Promise<NovelData> {
  const novel = await prisma.novel.findUnique({
    where: { id: input.novelId },
    include: {
      chapters: {
        orderBy: { order: "asc" },
        select: { id: true, title: true, content: true, order: true },
      },
      characters: {
        orderBy: { updatedAt: "desc" },
        include: {
          faction: { select: { id: true, name: true } },
          experiences: { orderBy: { order: "asc" } },
          outgoingRelations: {
            include: { target: { select: { id: true, name: true } } },
          },
          incomingRelations: {
            include: { character: { select: { id: true, name: true } } },
          },
        },
      },
      items: {
        orderBy: { updatedAt: "desc" },
        include: { owner: { select: { id: true, name: true } } },
      },
      locations: { orderBy: { updatedAt: "desc" } },
      factions: {
        orderBy: { updatedAt: "desc" },
        include: { base: { select: { id: true, name: true } } },
      },
      glossaries: { orderBy: { updatedAt: "desc" } },
      storyBackground: true,
      worldSetting: true,
      writingBible: true,
      outline: true,
      outlineNodes: { orderBy: { order: "asc" } },
      plotProgress: true,
      references: { orderBy: { updatedAt: "desc" } },
      appliedStyle: true,
      foreshadowings: { orderBy: { createdAt: "desc" } },
    },
  });

  if (!novel) {
    if (input.fallback) return input.fallback;
    throw new Error(`Novel not found: ${input.novelId}`);
  }

  const chapter =
    novel.chapters.find((item) => item.id === input.chapterId) ??
    novel.chapters.find((item) => item.id === input.fallback?.chapterId) ??
    novel.chapters[0];

  return {
    novelId: novel.id,
    chapterId: chapter?.id ?? input.fallback?.chapterId ?? "",
    chapters: novel.chapters.map((item) => ({
      id: item.id,
      title: item.title,
      content: item.content,
      order: item.order,
    })),
    novelName: novel.name,
    chapterTitle: chapter?.title ?? input.fallback?.chapterTitle ?? "",
    chapterContent: chapter?.content ?? input.fallback?.chapterContent ?? "",
    outlineSummary: novel.outline?.content ?? "",
    outlineNodes: novel.outlineNodes.map((node) => ({
      id: node.id,
      title: node.title,
      content: node.content ?? undefined,
      kind: node.kind,
      status: node.status,
      order: node.order,
      parentId: node.parentId ?? undefined,
    })),
    plotProgress: novel.plotProgress
      ? {
          currentStage: novel.plotProgress.currentStage,
          currentGoal: novel.plotProgress.currentGoal ?? undefined,
          currentConflict: novel.plotProgress.currentConflict ?? undefined,
          nextMilestone: novel.plotProgress.nextMilestone ?? undefined,
        }
      : { currentStage: "未设置" },
    storyBackground: novel.storyBackground?.content ?? "",
    worldSetting: novel.worldSetting?.content ?? "",
    writingBible: novel.writingBible
      ? {
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
    characters: novel.characters.map((character) => ({
      id: character.id,
      name: character.name,
      aliases: character.aliases ?? undefined,
      gender: character.gender ?? undefined,
      age: character.age ?? undefined,
      appearance: character.appearance ?? undefined,
      personality: character.personality ?? undefined,
      identity: character.identity ?? undefined,
      background: character.background ?? undefined,
      coreDesire: character.coreDesire ?? undefined,
      behaviorBoundaries: character.behaviorBoundaries ?? undefined,
      speechStyle: character.speechStyle ?? undefined,
      relationshipPrinciples: character.relationshipPrinciples ?? undefined,
      shortTermGoal: character.shortTermGoal ?? undefined,
      powerLevel: character.powerLevel ?? undefined,
      combatAbility: character.combatAbility ?? undefined,
      specialSkills: character.specialSkills ?? undefined,
      currentStatus: character.currentStatus,
      statusNote: character.statusNote ?? undefined,
      faction: character.faction
        ? { id: character.faction.id, name: character.faction.name }
        : undefined,
      outgoingRelations: character.outgoingRelations.map((relation) => ({
        id: relation.id,
        targetId: relation.targetId,
        target: { id: relation.target.id, name: relation.target.name },
        relationType: relation.relationType,
        intimacy: relation.intimacy,
        description: relation.description ?? undefined,
        startDate: relation.startDate ?? undefined,
        endDate: relation.endDate ?? undefined,
      })),
      incomingRelations: character.incomingRelations.map((relation) => ({
        id: relation.id,
        characterId: relation.characterId,
        character: { id: relation.character.id, name: relation.character.name },
        relationType: relation.relationType,
        intimacy: relation.intimacy,
        description: relation.description ?? undefined,
      })),
      experiences: character.experiences.map((experience) => ({
        id: experience.id,
        characterId: experience.characterId,
        chapterId: experience.chapterId ?? undefined,
        content: experience.content,
        order: experience.order,
      })),
    })),
    items: novel.items.map((item) => ({
      id: item.id,
      name: item.name,
      aliases: item.aliases ?? undefined,
      type: item.type ?? undefined,
      rarity: item.rarity ?? undefined,
      effect: item.effect ?? undefined,
      origin: item.origin ?? undefined,
      description: item.description ?? undefined,
      ownerId: item.ownerId ?? undefined,
      owner: item.owner ? { id: item.owner.id, name: item.owner.name } : undefined,
    })),
    locations: novel.locations.map((location) => ({
      id: location.id,
      name: location.name,
      aliases: location.aliases ?? undefined,
      type: location.type ?? undefined,
      parentId: location.parentId ?? undefined,
      climate: location.climate ?? undefined,
      culture: location.culture ?? undefined,
      description: location.description ?? undefined,
    })),
    factions: novel.factions.map((faction) => ({
      id: faction.id,
      name: faction.name,
      aliases: faction.aliases ?? undefined,
      type: faction.type ?? undefined,
      baseId: faction.baseId ?? undefined,
      base: faction.base ? { id: faction.base.id, name: faction.base.name } : undefined,
      description: faction.description ?? undefined,
    })),
    glossaries: novel.glossaries.map((glossary) => ({
      id: glossary.id,
      term: glossary.term,
      definition: glossary.definition,
      category: glossary.category ?? undefined,
    })),
    foreshadowings: novel.foreshadowings.map((foreshadowing) => ({
      id: foreshadowing.id,
      name: foreshadowing.name,
      plantedAt: foreshadowing.plantedAt ?? undefined,
      plantedContent: foreshadowing.plantedContent ?? undefined,
      expectedPayoff: foreshadowing.expectedPayoff ?? undefined,
      payoffAt: foreshadowing.payoffAt ?? undefined,
      status: foreshadowing.status,
    })),
    references: novel.references.map((reference) => ({
      id: reference.id,
      title: reference.title,
      type: reference.type,
      content: reference.content,
    })),
    styleProfile: novel.appliedStyle?.portraitMarkdown ?? "",
  };
}

async function buildAuthoritativeUpdateDiffs(input: {
  novelId: string;
  chapterId?: string | null;
  updates: AgentUpdates;
  fallbackNovelData?: NovelData;
}): Promise<UpdateDiffItem[]> {
  const novelData = await loadNovelDataForArtifactDiff({
    novelId: input.novelId,
    chapterId: input.chapterId,
    fallback: input.fallbackNovelData,
  });
  return buildUpdateDiffs(input.updates, novelData);
}

export async function toReviewArtifactDtoWithFreshDiff(
  record: ArtifactRecord,
  options: { novelData?: NovelData } = {}
): Promise<ReviewArtifactDto> {
  const dto = toReviewArtifactDto(record);
  if (dto.kind !== "agent_updates" || dto.payload.kind !== "agent_updates") {
    return dto;
  }

  const novelData = options.novelData ?? await loadNovelDataForArtifactDiff({
    novelId: record.novelId,
    chapterId: record.chapterId,
  });

  return {
    ...dto,
    diff: buildUpdateDiffs(dto.payload.updates, novelData),
  };
}

export async function toReviewArtifactDtosWithFreshDiff(records: ArtifactRecord[]): Promise<ReviewArtifactDto[]> {
  const novelDataByNovelId = new Map<string, Promise<NovelData>>();
  return Promise.all(records.map(async (record) => {
    let novelDataPromise = novelDataByNovelId.get(record.novelId);
    if (!novelDataPromise) {
      novelDataPromise = loadNovelDataForArtifactDiff({
        novelId: record.novelId,
        chapterId: record.chapterId,
      });
      novelDataByNovelId.set(record.novelId, novelDataPromise);
    }
    return toReviewArtifactDtoWithFreshDiff(record, { novelData: await novelDataPromise });
  }));
}

export async function createOrUpdateAgentUpdatesArtifact(input: {
  novelId: string;
  chapterId?: string | null;
  taskId?: string | null;
  workflowRunId?: string | null;
  artifactKey?: string | null;
  summary: string;
  updates: AgentUpdates;
  agentId: CoreAgentId;
  reviewerAgent?: CoreAgentId | null;
  novelData?: NovelData;
}): Promise<ReviewArtifactDto> {
  const payload: ReviewArtifactPayload = {
    kind: "agent_updates",
    updates: input.updates,
  };
  const diff = await buildAuthoritativeUpdateDiffs({
    novelId: input.novelId,
    chapterId: input.chapterId,
    updates: input.updates,
    fallbackNovelData: input.novelData,
  });

  const existing = input.artifactKey
    ? await prisma.reviewArtifact.findFirst({
        where: {
          novelId: input.novelId,
          artifactKey: input.artifactKey,
          status: { in: ["draft", "under_review", "awaiting_user"] },
        },
      })
    : null;

  const record = await prisma.$transaction(async (tx) => {
    if (existing) {
      const nextRevision = existing.revision + 1;
      assertReviewArtifactStatusTransition(
        parseArtifactStatus(existing.status),
        input.reviewerAgent ? "under_review" : "draft"
      );
      const updated = await tx.reviewArtifact.update({
        where: { id: existing.id },
        data: {
          status: input.reviewerAgent ? "under_review" : "draft",
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: JSON.stringify(diff),
          updatedByAgent: input.agentId,
          reviewerAgent: input.reviewerAgent ?? existing.reviewerAgent,
          revision: nextRevision,
        },
      });
      await tx.reviewArtifactRevision.create({
        data: {
          artifactId: updated.id,
          revision: nextRevision,
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: JSON.stringify(diff),
          createdByAgent: input.agentId,
        },
      });
      return updated;
    }

    const created = await tx.reviewArtifact.create({
      data: {
        novelId: input.novelId,
        chapterId: input.chapterId ?? null,
        taskId: input.taskId ?? null,
        workflowRunId: input.workflowRunId ?? null,
        artifactKey: input.artifactKey ?? null,
        kind: "agent_updates",
        status: input.reviewerAgent ? "under_review" : "draft",
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: JSON.stringify(diff),
        createdByAgent: input.agentId,
        updatedByAgent: input.agentId,
        reviewerAgent: input.reviewerAgent ?? null,
      },
    });
    await tx.reviewArtifactRevision.create({
      data: {
        artifactId: created.id,
        revision: 1,
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: JSON.stringify(diff),
        createdByAgent: input.agentId,
      },
    });
    return created;
  });

  return toReviewArtifactDto(record);
}

export async function loadUpdateBuilderArtifactUpdates(input: {
  novelId: string;
  artifactKey: string;
}): Promise<AgentUpdates | null> {
  const existing = await prisma.reviewArtifact.findFirst({
    where: {
      novelId: input.novelId,
      artifactKey: input.artifactKey,
      kind: "agent_updates",
      status: { in: ["draft", "under_review", "awaiting_user"] },
    },
    orderBy: { updatedAt: "desc" },
    select: { payloadJson: true },
  });
  if (!existing) return null;

  const payloadResult = ReviewArtifactPayloadSchema.safeParse(parseJson(existing.payloadJson, null));
  if (!payloadResult.success || payloadResult.data.kind !== "agent_updates") {
    return null;
  }
  return payloadResult.data.updates;
}

export async function upsertUpdateBuilderArtifact(input: {
  novelId: string;
  chapterId?: string | null;
  taskId?: string | null;
  workflowRunId?: string | null;
  artifactKey: string;
  summary: string;
  updates: AgentUpdates;
  agentId: CoreAgentId;
  reviewerAgent?: CoreAgentId | null;
  status: Extract<ReviewArtifactStatus, "draft" | "under_review">;
  novelData?: NovelData;
}): Promise<ReviewArtifactDto> {
  const payload: ReviewArtifactPayload = {
    kind: "agent_updates",
    updates: input.updates,
  };
  const diff = await buildAuthoritativeUpdateDiffs({
    novelId: input.novelId,
    chapterId: input.chapterId,
    updates: input.updates,
    fallbackNovelData: input.novelData,
  });

  const existing = await prisma.reviewArtifact.findFirst({
    where: {
      novelId: input.novelId,
      artifactKey: input.artifactKey,
      kind: "agent_updates",
      status: { in: ["draft", "under_review", "awaiting_user"] },
    },
    orderBy: { updatedAt: "desc" },
  });

  const record = await prisma.$transaction(async (tx) => {
    if (existing) {
      const nextRevision = existing.revision + 1;
      assertReviewArtifactStatusTransition(parseArtifactStatus(existing.status), input.status);
      const updated = await tx.reviewArtifact.update({
        where: { id: existing.id },
        data: {
          status: input.status,
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: JSON.stringify(diff),
          updatedByAgent: input.agentId,
          reviewerAgent: input.reviewerAgent ?? existing.reviewerAgent,
          revision: nextRevision,
        },
      });
      await tx.reviewArtifactRevision.create({
        data: {
          artifactId: updated.id,
          revision: nextRevision,
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: JSON.stringify(diff),
          createdByAgent: input.agentId,
        },
      });
      return updated;
    }

    const created = await tx.reviewArtifact.create({
      data: {
        novelId: input.novelId,
        chapterId: input.chapterId ?? null,
        taskId: input.taskId ?? null,
        workflowRunId: input.workflowRunId ?? null,
        artifactKey: input.artifactKey,
        kind: "agent_updates",
        status: input.status,
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: JSON.stringify(diff),
        createdByAgent: input.agentId,
        updatedByAgent: input.agentId,
        reviewerAgent: input.reviewerAgent ?? null,
      },
    });
    await tx.reviewArtifactRevision.create({
      data: {
        artifactId: created.id,
        revision: 1,
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: JSON.stringify(diff),
        createdByAgent: input.agentId,
      },
    });
    return created;
  });

  return toReviewArtifactDto(record);
}

export async function createOrUpdateTextArtifact(input: {
  novelId: string;
  chapterId?: string | null;
  taskId?: string | null;
  workflowRunId?: string | null;
  artifactKey?: string | null;
  kind: TextReviewArtifactKind;
  summary: string;
  content: string;
  agentId: CoreAgentId;
  reviewerAgent?: CoreAgentId | null;
}): Promise<ReviewArtifactDto> {
  const payload: ReviewArtifactPayload = {
    kind: input.kind,
    content: input.content,
  };

  const existing = input.artifactKey
    ? await prisma.reviewArtifact.findFirst({
        where: {
          novelId: input.novelId,
          artifactKey: input.artifactKey,
          status: { in: ["draft", "under_review", "awaiting_user"] },
        },
      })
    : null;

  const record = await prisma.$transaction(async (tx) => {
    if (existing) {
      const nextRevision = existing.revision + 1;
      assertReviewArtifactStatusTransition(
        parseArtifactStatus(existing.status),
        input.reviewerAgent ? "under_review" : "draft"
      );
      const updated = await tx.reviewArtifact.update({
        where: { id: existing.id },
        data: {
          kind: input.kind,
          status: input.reviewerAgent ? "under_review" : "draft",
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: null,
          updatedByAgent: input.agentId,
          reviewerAgent: input.reviewerAgent ?? existing.reviewerAgent,
          revision: nextRevision,
        },
      });
      await tx.reviewArtifactRevision.create({
        data: {
          artifactId: updated.id,
          revision: nextRevision,
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: null,
          createdByAgent: input.agentId,
        },
      });
      return updated;
    }

    const created = await tx.reviewArtifact.create({
      data: {
        novelId: input.novelId,
        chapterId: input.chapterId ?? null,
        taskId: input.taskId ?? null,
        workflowRunId: input.workflowRunId ?? null,
        artifactKey: input.artifactKey ?? null,
        kind: input.kind,
        status: input.reviewerAgent ? "under_review" : "draft",
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: null,
        createdByAgent: input.agentId,
        updatedByAgent: input.agentId,
        reviewerAgent: input.reviewerAgent ?? null,
      },
    });
    await tx.reviewArtifactRevision.create({
      data: {
        artifactId: created.id,
        revision: 1,
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: null,
        createdByAgent: input.agentId,
      },
    });
    return created;
  });

  return toReviewArtifactDto(record);
}

export async function createOrUpdateBeatPlanArtifact(input: {
  novelId: string;
  chapterId?: string | null;
  taskId?: string | null;
  workflowRunId?: string | null;
  artifactKey?: string | null;
  summary: string;
  beatPlan: BeatPlanDraft;
  agentId: CoreAgentId;
  reviewerAgent?: CoreAgentId | null;
}): Promise<ReviewArtifactDto> {
  const payload: ReviewArtifactPayload = {
    kind: "beat_plan",
    beatPlan: input.beatPlan,
  };

  const existing = input.artifactKey
    ? await prisma.reviewArtifact.findFirst({
        where: {
          novelId: input.novelId,
          artifactKey: input.artifactKey,
          status: { in: ["draft", "under_review", "awaiting_user"] },
        },
      })
    : null;

  const record = await prisma.$transaction(async (tx) => {
    if (existing) {
      const nextRevision = existing.revision + 1;
      assertReviewArtifactStatusTransition(
        parseArtifactStatus(existing.status),
        input.reviewerAgent ? "under_review" : "draft"
      );
      const updated = await tx.reviewArtifact.update({
        where: { id: existing.id },
        data: {
          kind: "beat_plan",
          status: input.reviewerAgent ? "under_review" : "draft",
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: null,
          updatedByAgent: input.agentId,
          reviewerAgent: input.reviewerAgent ?? existing.reviewerAgent,
          revision: nextRevision,
        },
      });
      await tx.reviewArtifactRevision.create({
        data: {
          artifactId: updated.id,
          revision: nextRevision,
          summary: input.summary,
          payloadJson: JSON.stringify(payload),
          diffJson: null,
          createdByAgent: input.agentId,
        },
      });
      return updated;
    }

    const created = await tx.reviewArtifact.create({
      data: {
        novelId: input.novelId,
        chapterId: input.chapterId ?? null,
        taskId: input.taskId ?? null,
        workflowRunId: input.workflowRunId ?? null,
        artifactKey: input.artifactKey ?? null,
        kind: "beat_plan",
        status: input.reviewerAgent ? "under_review" : "draft",
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: null,
        createdByAgent: input.agentId,
        updatedByAgent: input.agentId,
        reviewerAgent: input.reviewerAgent ?? null,
      },
    });
    await tx.reviewArtifactRevision.create({
      data: {
        artifactId: created.id,
        revision: 1,
        summary: input.summary,
        payloadJson: JSON.stringify(payload),
        diffJson: null,
        createdByAgent: input.agentId,
      },
    });
    return created;
  });

  return toReviewArtifactDto(record);
}

export async function submitArtifactEvaluation(input: {
  artifactId: string;
  evaluatorAgent: CoreAgentId;
  verdict: ReviewArtifactEvaluationVerdict;
  summary: string;
  requiredChanges?: string;
}): Promise<ReviewArtifactDto> {
  const artifact = await prisma.reviewArtifact.findUnique({
    where: { id: input.artifactId },
  });
  if (!artifact) throw new Error("待审核草案不存在");

  const nextStatus = input.verdict === "pass" ? "awaiting_user" : artifact.status;
  if (input.verdict === "pass") {
    assertReviewArtifactStatusTransition(parseArtifactStatus(artifact.status), "awaiting_user");
  }
  const updated = await prisma.$transaction(async (tx) => {
    await tx.reviewArtifactEvaluation.create({
      data: {
        artifactId: artifact.id,
        revision: artifact.revision,
        evaluatorAgent: input.evaluatorAgent,
        verdict: input.verdict,
        summary: input.summary,
        requiredChanges: input.requiredChanges ?? null,
      },
    });
    return tx.reviewArtifact.update({
      where: { id: artifact.id },
      data: {
        status: nextStatus,
        reviewerAgent: input.evaluatorAgent,
      },
      include: {
        evaluations: { orderBy: { createdAt: "desc" } },
      },
    });
  });

  return toReviewArtifactDto(updated);
}

export async function markArtifactUnderReview(input: {
  artifactId: string;
  reviewerAgent: CoreAgentId;
}): Promise<ReviewArtifactDto> {
  const current = await prisma.reviewArtifact.findUnique({
    where: { id: input.artifactId },
    select: { status: true },
  });
  if (!current) throw new Error("待审核草案不存在");
  assertReviewArtifactStatusTransition(parseArtifactStatus(current.status), "under_review");
  const artifact = await prisma.reviewArtifact.update({
    where: { id: input.artifactId },
    data: {
      status: "under_review",
      reviewerAgent: input.reviewerAgent,
    },
    include: { evaluations: { orderBy: { createdAt: "desc" } } },
  });
  return toReviewArtifactDto(artifact);
}

export async function markArtifactAwaitingUser(input: {
  artifactId: string;
}): Promise<ReviewArtifactDto> {
  const current = await prisma.reviewArtifact.findUnique({
    where: { id: input.artifactId },
    select: { status: true },
  });
  if (!current) throw new Error("待审核草案不存在");
  assertReviewArtifactStatusTransition(parseArtifactStatus(current.status), "awaiting_user");
  const artifact = await prisma.reviewArtifact.update({
    where: { id: input.artifactId },
    data: { status: "awaiting_user" },
    include: { evaluations: { orderBy: { createdAt: "desc" } } },
  });
  return toReviewArtifactDto(artifact);
}

export async function discardArtifactHard(input: {
  artifactId: string;
  userId: string;
}): Promise<void> {
  const artifact = await prisma.reviewArtifact.findUnique({
    where: { id: input.artifactId },
    include: { novel: { select: { userId: true } } },
  });
  if (!artifact) return;
  if (artifact.novel.userId && artifact.novel.userId !== input.userId) {
    throw new Error("无权删除该待审核草案");
  }
  await prisma.reviewArtifact.delete({ where: { id: input.artifactId } });
}

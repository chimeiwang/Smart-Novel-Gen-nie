/**
 * ReviewArtifact 正式应用入口。
 *
 * @module agents/artifacts/artifact-apply
 * @description 用户确认后，才允许将待审核草案写入正式小说库。
 */

import { prisma } from "@/shared/db/prisma";
import { executeUpdates } from "@/agents/lib/db-operations";
import { applyApprovedBeatPlan, buildBeatPlanDraftFromText } from "@/agents/lib/beat-plan-service";
import { ensureDefaultChapterQualityChecks } from "@/agents/lib/quality-check-service";
import {
  assertReviewArtifactStatusTransition,
  getReviewArtifactStatusLabel,
  ReviewArtifactPayloadSchema,
  ReviewArtifactStatusSchema,
} from "@/shared/contracts/review-artifact";
import {
  AgentUpdatesProposalSchema,
  hasAgentUpdates,
  type AgentUpdates,
  type AgentUpdateSelectionRef,
} from "@/shared/contracts/agent-updates";
import type { ReviewArtifactDto } from "@/shared/contracts/review-artifact";
import { toReviewArtifactDto } from "./artifact-service";

type ParsedReviewArtifactPayload = ReturnType<typeof ReviewArtifactPayloadSchema.parse>;

export type ReviewArtifactApplyTarget = "agent_updates" | "outline_content" | "chapter_content" | "beat_plan";

export function resolveReviewArtifactApplyTarget(
  payload: ParsedReviewArtifactPayload
): ReviewArtifactApplyTarget | null {
  if (payload.kind === "agent_updates") return "agent_updates";
  if (payload.kind === "outline_draft") return "outline_content";
  if (payload.kind === "chapter_content" || payload.kind === "chapter_draft") return "chapter_content";
  if (payload.kind === "beat_plan" || payload.kind === "beat_plan_draft") return "beat_plan";
  return null;
}

export function resolveChapterDraftApplyMode(input: {
  payload: ParsedReviewArtifactPayload;
  artifactChapterId: string | null;
}): { mode: "existing_chapter"; chapterId: string } | { mode: "new_next_chapter"; title?: string } | null {
  if (input.payload.kind !== "chapter_draft" && input.payload.kind !== "chapter_content") return null;
  if (input.payload.kind === "chapter_draft" && input.payload.target?.mode === "new_next_chapter") {
    return { mode: "new_next_chapter", title: input.payload.target.title };
  }
  const chapterId = input.payload.kind === "chapter_draft" && input.payload.target?.mode === "existing_chapter"
    ? input.payload.target.chapterId
    : input.artifactChapterId;
  return chapterId ? { mode: "existing_chapter", chapterId } : null;
}

export function filterAgentUpdatesBySelection(
  updates: AgentUpdates,
  selectedRefs: AgentUpdateSelectionRef[] | undefined
): AgentUpdates {
  if (selectedRefs === undefined) return updates;

  const selectedBySection = new Map<string, { fullSection: boolean; indices: Set<number> }>();
  for (const ref of selectedRefs) {
    const entry = selectedBySection.get(ref.section) ?? { fullSection: false, indices: new Set<number>() };
    if (ref.index === undefined) {
      entry.fullSection = true;
    } else {
      entry.indices.add(ref.index);
    }
    selectedBySection.set(ref.section, entry);
  }

  const output: AgentUpdates = {};

  const pickArraySection = <T>(section: keyof AgentUpdates, items: T[] | undefined) => {
    if (!items?.length) return;
    const selected = selectedBySection.get(section);
    if (!selected) return;
    const picked = selected.fullSection ? items : items.filter((_, index) => selected.indices.has(index));
    if (picked.length > 0) {
      (output as Record<string, unknown>)[section] = picked;
    }
  };

  pickArraySection("characters", updates.characters);
  pickArraySection("locations", updates.locations);
  pickArraySection("items", updates.items);
  pickArraySection("factions", updates.factions);
  pickArraySection("glossaries", updates.glossaries);
  pickArraySection("characterExperiences", updates.characterExperiences);
  pickArraySection("outline", updates.outline);
  pickArraySection("outlineAdjustments", updates.outlineAdjustments);
  pickArraySection("foreshadowing", updates.foreshadowing);
  pickArraySection("references", updates.references);

  for (const section of ["outlineContent", "worldSetting", "storyBackground"] as const) {
    if (updates[section] && selectedBySection.has(section)) {
      output[section] = updates[section];
    }
  }

  return output;
}

export async function applyReviewArtifact(input: {
  artifactId: string;
  userId: string;
  editedContent?: string;
  selectedUpdateRefs?: AgentUpdateSelectionRef[];
}): Promise<{
  success: boolean;
  summary: string;
  errors?: string[];
  savedCount?: number;
  artifact?: ReviewArtifactDto;
}> {
  const artifact = await prisma.reviewArtifact.findUnique({
    where: { id: input.artifactId },
    include: { novel: { select: { userId: true } } },
  });

  if (!artifact) {
    return { success: false, summary: "待审核草案不存在", errors: ["待审核草案不存在"] };
  }
  if (artifact.novel.userId && artifact.novel.userId !== input.userId) {
    return { success: false, summary: "无权应用该待审核草案", errors: ["无权应用该待审核草案"] };
  }
  const artifactStatusResult = ReviewArtifactStatusSchema.safeParse(artifact.status);
  if (!artifactStatusResult.success) {
    return { success: false, summary: "待审核草案状态异常", errors: ["待审核草案状态异常"] };
  }
  const artifactStatus = artifactStatusResult.data;

  if (artifactStatus !== "awaiting_user") {
    return {
      success: false,
      summary: `当前状态不能应用：${getReviewArtifactStatusLabel(artifactStatus)}`,
      errors: [`当前状态不能应用：${getReviewArtifactStatusLabel(artifactStatus)}`],
    };
  }
  if (!artifact.taskId) {
    return { success: false, summary: "草案缺少 taskId，无法执行正式落库", errors: ["草案缺少 taskId"] };
  }

  assertReviewArtifactStatusTransition(artifactStatus, "applying");
  const locked = await prisma.reviewArtifact.updateMany({
    where: { id: artifact.id, status: "awaiting_user" },
    data: { status: "applying" },
  });
  if (locked.count !== 1) {
    return { success: false, summary: "草案状态已变化，请刷新后重试", errors: ["草案状态已变化"] };
  }

  const payloadResult = ReviewArtifactPayloadSchema.safeParse(JSON.parse(artifact.payloadJson));
  const applyTarget = payloadResult.success ? resolveReviewArtifactApplyTarget(payloadResult.data) : null;
  if (!payloadResult.success || !applyTarget) {
    assertReviewArtifactStatusTransition("applying", "awaiting_user");
    await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: { status: "awaiting_user" },
    });
    return { success: false, summary: "当前草案类型暂不支持应用", errors: ["当前草案类型暂不支持应用"] };
  }

  let payload = payloadResult.data;
  if (input.editedContent !== undefined && "content" in payload) {
    const editedContent = input.editedContent.trim();
    if (!editedContent) {
      assertReviewArtifactStatusTransition("applying", "awaiting_user");
      await prisma.reviewArtifact.update({
        where: { id: artifact.id },
        data: { status: "awaiting_user" },
      });
      return { success: false, summary: "草案正文不能为空", errors: ["草案正文不能为空"] };
    }
    payload = { ...payload, content: editedContent };
    await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: {
        payloadJson: JSON.stringify(payload),
        updatedAt: new Date(),
      },
    });
  }

  if (payload.kind === "outline_draft") {
    await prisma.outline.upsert({
      where: { novelId: artifact.novelId },
      update: { content: payload.content },
      create: {
        novelId: artifact.novelId,
        content: payload.content,
      },
    });

    assertReviewArtifactStatusTransition("applying", "applied");
    const applied = await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: {
        status: "applied",
        appliedAt: new Date(),
      },
      include: { evaluations: { orderBy: { createdAt: "desc" } } },
    });

    return {
      success: true,
      summary: "大纲草案已应用到正式大纲",
      savedCount: 1,
      artifact: toReviewArtifactDto(applied),
    };
  }

  if (payload.kind === "beat_plan" || payload.kind === "beat_plan_draft") {
    if (!artifact.chapterId) {
      assertReviewArtifactStatusTransition("applying", "awaiting_user");
      await prisma.reviewArtifact.update({
        where: { id: artifact.id },
        data: { status: "awaiting_user" },
      });
      return { success: false, summary: "草案缺少 chapterId，无法应用为章节计划", errors: ["草案缺少 chapterId"] };
    }

    const beatPlan = payload.kind === "beat_plan"
      ? payload.beatPlan
      : buildBeatPlanDraftFromText({
          title: artifact.title,
          summary: artifact.summary,
          content: payload.content,
        });
    await applyApprovedBeatPlan({
      chapterId: artifact.chapterId,
      beatPlan,
      generatedBy: artifact.updatedByAgent ?? artifact.createdByAgent,
    });

    assertReviewArtifactStatusTransition("applying", "applied");
    const applied = await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: {
        status: "applied",
        appliedAt: new Date(),
      },
      include: { evaluations: { orderBy: { createdAt: "desc" } } },
    });

    return {
      success: true,
      summary: "章节计划已应用为已批准 Beat Plan",
      savedCount: 1,
      artifact: toReviewArtifactDto(applied),
    };
  }

  if (payload.kind === "chapter_content" || payload.kind === "chapter_draft") {
    const chapterApplyMode = resolveChapterDraftApplyMode({
      payload,
      artifactChapterId: artifact.chapterId,
    });

    if (chapterApplyMode?.mode === "new_next_chapter") {
      const chapter = await prisma.$transaction(async (tx) => {
        const maxChapter = await tx.chapter.findFirst({
          where: { novelId: artifact.novelId },
          orderBy: { order: "desc" },
          select: { order: true },
        });
        const nextOrder = (maxChapter?.order ?? 0) + 1;
        const created = await tx.chapter.create({
          data: {
            novelId: artifact.novelId,
            title: chapterApplyMode.title?.trim() || `第 ${nextOrder} 章`,
            order: nextOrder,
            content: payload.content,
            status: "review",
          },
        });
        await tx.reviewArtifact.update({
          where: { id: artifact.id },
          data: {
            chapterId: created.id,
            status: "applied",
            appliedAt: new Date(),
          },
        });
        return created;
      });
      await ensureDefaultChapterQualityChecks(chapter.id);
      const applied = await prisma.reviewArtifact.findUniqueOrThrow({
        where: { id: artifact.id },
        include: { evaluations: { orderBy: { createdAt: "desc" } } },
      });
      return {
        success: true,
        summary: `正文草案已应用到新章节「${chapter.title}」`,
        savedCount: 1,
        artifact: toReviewArtifactDto(applied),
      };
    }

    if (!chapterApplyMode) {
      assertReviewArtifactStatusTransition("applying", "awaiting_user");
      await prisma.reviewArtifact.update({
        where: { id: artifact.id },
        data: { status: "awaiting_user" },
      });
      return { success: false, summary: "草案缺少 chapterId，无法应用到章节正文", errors: ["草案缺少 chapterId"] };
    }

    await prisma.chapter.update({
      where: { id: chapterApplyMode.chapterId },
      data: {
        content: payload.content,
        status: "review",
      },
    });
    await ensureDefaultChapterQualityChecks(chapterApplyMode.chapterId);

    assertReviewArtifactStatusTransition("applying", "applied");
    const applied = await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: {
        status: "applied",
        appliedAt: new Date(),
      },
      include: { evaluations: { orderBy: { createdAt: "desc" } } },
    });

    return {
      success: true,
      summary: "正文草案已应用到章节正文",
      savedCount: 1,
      artifact: toReviewArtifactDto(applied),
    };
  }

  if (payload.kind !== "agent_updates") {
    assertReviewArtifactStatusTransition("applying", "awaiting_user");
    await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: { status: "awaiting_user" },
    });
    return {
      success: false,
      summary: `当前草案类型暂不支持应用：${artifact.kind}`,
      errors: [`当前草案类型暂不支持应用：${artifact.kind}`],
    };
  }

  const updatesToApply = filterAgentUpdatesBySelection(payload.updates, input.selectedUpdateRefs);
  if (!hasAgentUpdates(updatesToApply)) {
    assertReviewArtifactStatusTransition("applying", "awaiting_user");
    await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: { status: "awaiting_user" },
    });
    return {
      success: false,
      summary: "没有选择任何可应用的变更，未写入正式数据",
      errors: ["没有选择任何可应用的变更"],
      savedCount: 0,
    };
  }

  const proposalResult = AgentUpdatesProposalSchema.safeParse(updatesToApply);
  if (!proposalResult.success) {
    assertReviewArtifactStatusTransition("applying", "awaiting_user");
    await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: { status: "awaiting_user" },
    });
    const errors = proposalResult.error.issues.map((issue) => {
      const path = issue.path.length > 0 ? issue.path.join(".") : "(root)";
      return `${path}: ${issue.message}`;
    });
    return {
      success: false,
      summary: "草案结构校验失败，未写入正式数据",
      errors,
    };
  }

  const result = await executeUpdates(artifact.taskId, proposalResult.data);
  if (!result.success) {
    assertReviewArtifactStatusTransition("applying", "awaiting_user");
    await prisma.reviewArtifact.update({
      where: { id: artifact.id },
      data: { status: "awaiting_user" },
    });
    return {
      success: false,
      summary: result.summary,
      errors: result.errors,
      savedCount: result.savedCount,
    };
  }

  assertReviewArtifactStatusTransition("applying", "applied");
  const applied = await prisma.reviewArtifact.update({
    where: { id: artifact.id },
    data: {
      status: "applied",
      appliedAt: new Date(),
      ...(input.selectedUpdateRefs !== undefined
        ? { payloadJson: JSON.stringify({ ...payload, updates: proposalResult.data }) }
        : {}),
    },
    include: { evaluations: { orderBy: { createdAt: "desc" } } },
  });

  return {
    success: true,
    summary: result.summary,
    savedCount: result.savedCount,
    artifact: toReviewArtifactDto(applied),
  };
}

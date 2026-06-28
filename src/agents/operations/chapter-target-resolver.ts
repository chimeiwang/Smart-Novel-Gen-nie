import { interrupt } from "@langchain/langgraph";
import type { ChapterStatus } from "@prisma/client";
import { prisma } from "@/shared/db/prisma";
import type { ChapterDraftTarget } from "@/shared/contracts/review-artifact";
import { createChapterTargetInterrupt } from "@/shared/contracts/user-decision";

type Chapter = {
  id: string;
  title: string;
  order: number;
  status: ChapterStatus;
  content: string | null;
};

export type ResolvedChapterTarget = {
  contextChapterId: string;
  target: ChapterDraftTarget;
  targetTitle: string;
  targetContent: string;
};

export async function resolveChapterDraftTarget(input: {
  novelId: string;
  chapterId: string;
  userMessage: string;
  allowNewChapterTarget?: boolean;
}): Promise<ResolvedChapterTarget> {
  const chapters = await prisma.chapter.findMany({
    where: { novelId: input.novelId },
    orderBy: { order: "asc" },
    select: { id: true, title: true, order: true, status: true, content: true },
  });
  const current = chapters.find((chapter) => chapter.id === input.chapterId) ?? chapters[0];
  if (!current) {
    return {
      contextChapterId: input.chapterId,
      target: { mode: "existing_chapter", chapterId: input.chapterId },
      targetTitle: "",
      targetContent: "",
    };
  }

  const wantsCurrent = isExplicitCurrentChapterRequest(input.userMessage);
  const currentLocked = current.status !== "drafting" && Boolean(current.content.trim());
  const nextDraft = chapters.find((chapter) =>
    chapter.order > current.order &&
    chapter.status === "drafting" &&
    !chapter.content.trim()
  );

  if (wantsCurrent && currentLocked && nextDraft) {
    const decision = interrupt(createChapterTargetInterrupt({
      currentTitle: current.title,
      nextTitle: nextDraft.title,
    })) as { decision?: "current_chapter" | "next_chapter" } | undefined;
    if (decision?.decision !== "next_chapter") {
      return existingTarget(current);
    }
    return existingTarget(nextDraft, current.id);
  }

  if (wantsCurrent || !currentLocked) return existingTarget(current);
  if (nextDraft) return existingTarget(nextDraft, current.id);
  if (input.allowNewChapterTarget === false) return existingTarget(current);

  const nextOrder = Math.max(...chapters.map((chapter) => chapter.order), 0) + 1;
  const title = `第 ${nextOrder} 章`;
  return {
    contextChapterId: current.id,
    target: { mode: "new_next_chapter", afterChapterId: current.id, title },
    targetTitle: title,
    targetContent: "",
  };
}

function existingTarget(chapter: Chapter, contextChapterId = chapter.id): ResolvedChapterTarget {
  return {
    contextChapterId,
    target: { mode: "existing_chapter", chapterId: chapter.id },
    targetTitle: chapter.title,
    targetContent: chapter.content ?? "",
  };
}

function isExplicitCurrentChapterRequest(message: string): boolean {
  return /(?:重写|改写|修改|润色|续写|继续写).{0,8}(?:本章|当前章|这一章|这章|第一章|第[一二三四五六七八九十\d]+章|当前段落|这一段|这段)/.test(message);
}

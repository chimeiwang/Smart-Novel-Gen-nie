"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTransition } from "react";

import { createChapterAction } from "@/app/actions";

type ChapterListProps = {
  novelId: string;
  activeChapterId: string;
  chapters: Array<{
    id: string;
    title: string;
    order: number;
    updatedAt: string;
    status?: string;
    wordCount?: number;
    approvedBeatPlan?: {
      sceneCount: number;
      totalEstimatedWords: number;
    } | null;
  }>;
};

export function ChapterList({
  novelId,
  activeChapterId,
  chapters,
}: ChapterListProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  const handleCreateChapter = () => {
    startTransition(async () => {
      const chapterId = await createChapterAction(novelId);

      if (chapterId) {
        router.push(`/workspace/${novelId}?chapterId=${chapterId}`);
        router.refresh();
      }
    });
  };

  return (
    <div className="stack">
      <div className="row row-between">
        <div>
          <h2 className="title-md">章节</h2>
          <p className="muted">当前共 {chapters.length} 章</p>
        </div>
        <button className="button secondary" type="button" onClick={handleCreateChapter}>
          {pending ? "添加中..." : "新增章节"}
        </button>
      </div>
      <div className="list">
        {chapters.map((chapter) => (
          <Link
            key={chapter.id}
            href={`/workspace/${novelId}?chapterId=${chapter.id}`}
            className={`chapter-link ${activeChapterId === chapter.id ? "active" : ""}`}
          >
            <div className="title-md">{chapter.title}</div>
            <div className="chapter-link-meta">
              <span>排序 #{chapter.order}</span>
              <span>{chapter.wordCount ?? 0} 字</span>
              <span>{formatBeatPlanMeta(chapter.approvedBeatPlan)}</span>
              <span className="badge">{getStatusLabel(chapter.status)}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function getStatusLabel(status?: string) {
  if (status === "review") return "待审";
  if (status === "completed") return "完成";
  return "草稿";
}

function formatBeatPlanMeta(plan?: { sceneCount: number; totalEstimatedWords: number } | null) {
  if (!plan) return "未确认章节计划";
  return `章节计划 ${plan.sceneCount} 场 · ${plan.totalEstimatedWords} 字`;
}

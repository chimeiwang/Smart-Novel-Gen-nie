"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type MouseEvent, useState, useTransition } from "react";

import { flushActiveChapterSave } from "@/features/editor/chapter-save-navigation";
import {
  buildWorkspaceChapterHref,
  type WorkspaceView,
} from "@/features/workspace/workspace-view";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import { formatChapterBeatPlanMeta } from "./chapter-plan-presentation";

type ChapterListProps = {
  novelId: string;
  activeChapterId: string;
  view: WorkspaceView;
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
  view,
}: ChapterListProps) {
  const router = useRouter();
  const [creating, startCreatingTransition] = useTransition();
  const [, startNavigationTransition] = useTransition();
  const [navigatingChapterId, setNavigatingChapterId] = useState<string | null>(null);
  const [navigationError, setNavigationError] = useState<string | null>(null);

  const handleCreateChapter = () => {
    startCreatingTransition(async () => {
      setNavigationError(null);
      try {
        await flushActiveChapterSave();
        const chapter = requireApiData(await browserApi.POST(
          "/api/v1/novels/{novel_id}/chapters",
          { params: { path: { novel_id: novelId } } },
        ));
        router.push(buildWorkspaceChapterHref({
          novelId,
          chapterId: chapter.chapter.id,
          view,
        }));
        router.refresh();
      } catch (error) {
        setNavigationError(error instanceof Error ? error.message : "章节保存失败，无法新建章节");
      }
    });
  };

  const handleChapterNavigation = (
    event: MouseEvent<HTMLAnchorElement>,
    chapterId: string,
  ) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    event.preventDefault();
    if (navigatingChapterId === chapterId) return;
    setNavigatingChapterId(chapterId);
    startNavigationTransition(async () => {
      setNavigationError(null);
      try {
        await flushActiveChapterSave();
        router.push(buildWorkspaceChapterHref({ novelId, chapterId, view }));
      } catch (error) {
        setNavigationError(error instanceof Error ? error.message : "章节保存失败，无法切换章节");
      } finally {
        setNavigatingChapterId(null);
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
        <button className="button secondary" type="button" onClick={handleCreateChapter} disabled={creating}>
          {creating ? "添加中..." : "新增章节"}
        </button>
      </div>
      {navigationError ? <p className="muted error-text">{navigationError}</p> : null}
      <div className="list">
        {chapters.map((chapter) => {
          const isCurrentChapter = activeChapterId === chapter.id;
          const beatPlanMeta = formatChapterBeatPlanMeta(
            chapter.approvedBeatPlan ?? null,
            { isCurrentChapter },
          );
          const navigating = navigatingChapterId === chapter.id;
          return (
            <Link
              key={chapter.id}
              href={buildWorkspaceChapterHref({ novelId, chapterId: chapter.id, view })}
              className={`chapter-link ${isCurrentChapter ? "active" : ""} ${navigating ? "navigating" : ""}`}
              aria-disabled={navigating}
              onClick={(event) => handleChapterNavigation(event, chapter.id)}
            >
              <div className="title-md">{chapter.title}</div>
              <div className="chapter-link-meta">
                <span>排序 #{chapter.order}</span>
                <span>{chapter.wordCount ?? 0} 字</span>
                {beatPlanMeta ? <span>{beatPlanMeta}</span> : null}
                <span className="badge">{getStatusLabel(chapter.status)}</span>
                {navigating ? <span>切换中...</span> : null}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function getStatusLabel(status?: string) {
  if (status === "review") return "待审";
  if (status === "completed") return "完成";
  return "草稿";
}

import type { components } from "@inkforge/api-client";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { LogoutButton } from "@/features/auth/user-menu";
import { ChapterEditor } from "@/features/editor/chapter-editor";
import { SidebarTabs } from "@/features/workspace/sidebar-tabs";
import { SmartWritingPanel } from "@/features/workspace/smart-writing-panel";
import { createServerApiClient } from "@/lib/api/server";
import { CoreApiPageError, requireApiData } from "@/lib/api/response";

type WorkspacePageProps = {
  params: Promise<{ novelId: string }>;
  searchParams: Promise<{ chapterId?: string }>;
};

export default async function WorkspacePage({
  params,
  searchParams,
}: WorkspacePageProps) {
  const { novelId } = await params;
  const { chapterId } = await searchParams;
  let workspace: components["schemas"]["WorkspaceBootstrapResponse"];
  try {
    const client = await createServerApiClient();
    workspace = requireApiData(await client.GET(
      "/api/v1/novels/{novel_id}/workspace/bootstrap",
      {
        params: {
          path: { novel_id: novelId },
          query: { chapterId },
        },
      },
    ));
  } catch (error) {
    if (error instanceof CoreApiPageError && error.status === 401) redirect("/login");
    if (error instanceof CoreApiPageError && error.status === 404) notFound();
    const message = error instanceof Error ? error.message : "加载作品工作区失败";
    return <main className="page"><div className="empty">{message}</div></main>;
  }

  const { novel, chapters, currentChapter } = workspace;
  if (!currentChapter) {
    return (
      <main className="page">
        <div className="empty">当前小说还没有章节，请先添加章节。</div>
      </main>
    );
  }

  const totalCount = chapters.reduce((sum, item) => sum + item.wordCount, 0);
  const approvedBeatPlan = currentChapter.approvedBeatPlan;

  return (
    <main className="page stack">
      <div className="panel header-panel">
        <div className="panel-header">
          <Link href="/" className="muted">
            ← 返回
          </Link>
          <span style={{ marginLeft: "auto" }}>
            <LogoutButton />
          </span>
          <h1 className="title-lg">{novel.name}</h1>
          <div className="meta">
            <span className="badge">{totalCount} 字</span>
            <span className="badge">{chapters.length} 章</span>
            {novel.appliedStyle ? <span className="badge">{novel.appliedStyle.name}</span> : null}
          </div>
        </div>
      </div>

      <div className="workspace">
        <SidebarTabs
          key={novel.id}
          novelId={novel.id}
          activeChapterId={currentChapter.id}
          chapters={chapters}
          appliedStyleId={novel.appliedStyleId}
        />

        <ChapterEditor
          key={currentChapter.id}
          chapter={{
            id: currentChapter.id,
            title: currentChapter.title,
            content: currentChapter.content,
            status: currentChapter.status,
            completedAt: currentChapter.completedAt,
          }}
          chapterProgress={currentChapter.progress?.content ?? null}
          qualityChecks={currentChapter.qualityChecks.filter(
            (check) => check.type === "consistency",
          )}
          styleName={novel.appliedStyle?.name}
        />

        <SmartWritingPanel
          novelId={novel.id}
          currentChapter={{
            id: currentChapter.id,
            title: currentChapter.title,
            status: currentChapter.status,
            wordCount: currentChapter.wordCount,
            openConsistencyCheckCount: currentChapter.qualityChecks.filter(
              (check) => check.type === "consistency"
                && (check.status === "pending" || check.status === "failed"),
            ).length,
            approvedBeatPlan: approvedBeatPlan
              ? {
                  id: approvedBeatPlan.id,
                  chapterGoal: approvedBeatPlan.chapterGoal,
                  sceneCount: approvedBeatPlan.sceneBeats.length,
                  totalEstimatedWords: approvedBeatPlan.totalEstimatedWords,
                }
              : null,
          }}
        />
      </div>
    </main>
  );
}

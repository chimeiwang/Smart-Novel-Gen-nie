"use client";

import type { components } from "@inkforge/api-client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { LogoutButton } from "@/features/auth/user-menu";
import { ChapterList } from "@/features/chapters/chapter-list";
import { ChapterEditor } from "@/features/editor/chapter-editor";
import { flushActiveChapterSave } from "@/features/editor/chapter-save-navigation";
import { LibraryPane } from "./library-pane";
import { SmartWritingPanel } from "./smart-writing-panel";
import {
  commitWorkspaceViewChange,
  formatWorkspaceViewSaveError,
} from "./workspace-shell-state";
import type { WorkspaceView } from "./workspace-view";

type WorkspaceShellProps = {
  bootstrap: components["schemas"]["WorkspaceBootstrapResponse"];
  currentUser: components["schemas"]["UserResponse"];
  initialView: WorkspaceView;
};

const VIEW_OPTIONS: Array<{ value: WorkspaceView; label: string }> = [
  { value: "studio", label: "AI 创作" },
  { value: "reading", label: "阅读与小修" },
  { value: "library", label: "创作资料" },
];

export function WorkspaceShell({
  bootstrap,
  currentUser,
  initialView,
}: WorkspaceShellProps) {
  const { novel, chapters, currentChapter } = bootstrap;
  const [activeView, setActiveView] = useState<WorkspaceView>(initialView);
  const [readingSession, setReadingSession] = useState(0);
  const [switchingView, setSwitchingView] = useState<WorkspaceView | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const previousInitialViewRef = useRef(initialView);
  const totalCount = chapters.reduce((sum, item) => sum + item.wordCount, 0);
  const approvedBeatPlan = currentChapter?.approvedBeatPlan ?? null;

  const applyActiveView = useCallback((view: WorkspaceView) => {
    if (view === "reading") setReadingSession((current) => current + 1);
    setActiveView(view);
  }, []);

  useEffect(() => {
    if (previousInitialViewRef.current === initialView) return;
    previousInitialViewRef.current = initialView;
    const syncTimer = window.setTimeout(() => applyActiveView(initialView), 0);
    return () => window.clearTimeout(syncTimer);
  }, [applyActiveView, initialView]);

  const selectView = async (nextView: WorkspaceView) => {
    if (switchingView) return;
    setViewError(null);
    setSwitchingView(nextView);
    try {
      await commitWorkspaceViewChange({
        currentView: activeView,
        nextView,
        flush: flushActiveChapterSave,
        commit: (view) => {
          const url = new URL(window.location.href);
          url.searchParams.set("view", view);
          window.history.replaceState(window.history.state, "", url);
          applyActiveView(view);
        },
      });
    } catch (error) {
      setViewError(formatWorkspaceViewSaveError(error));
    } finally {
      setSwitchingView(null);
    }
  };

  return (
    <main className="page stack workspace-page">
      <header className="panel workspace-shell-header">
        <div className="workspace-shell-summary">
          <Link href="/" className="muted">← 返回</Link>
          <div>
            <h1 className="title-lg">{novel.name}</h1>
            <div className="meta">
              <span className="badge">{totalCount} 字</span>
              <span className="badge">{chapters.length} 章</span>
              {novel.appliedStyle ? <span className="badge">{novel.appliedStyle.name}</span> : null}
            </div>
          </div>
        </div>
        <nav className="workspace-view-switcher" aria-label="工作区模式">
          {VIEW_OPTIONS.map((option) => (
            <button
              key={option.value}
              className={`workspace-view-button ${activeView === option.value ? "active" : ""}`}
              type="button"
              aria-pressed={activeView === option.value}
              disabled={switchingView !== null}
              onClick={() => void selectView(option.value)}
            >
              {option.label}
            </button>
          ))}
        </nav>
        <LogoutButton />
      </header>

      {viewError ? <p className="workspace-view-error" role="alert">{viewError}</p> : null}

      <div className="workspace-shell" data-view={activeView}>
        <aside className="panel workspace-chapter-navigation" hidden={activeView === "library"}>
          <div className="panel-body">
            <ChapterList
              novelId={novel.id}
              activeChapterId={currentChapter?.id ?? ""}
              chapters={chapters}
              view={activeView}
            />
          </div>
        </aside>

        <div className="workspace-shell-main" data-view={activeView}>
          <section className="workspace-pane workspace-agent-pane" hidden={activeView !== "studio"}>
            <SmartWritingPanel
              novelId={novel.id}
              currentChapter={currentChapter ? {
                id: currentChapter.id,
                title: currentChapter.title,
                status: currentChapter.status,
                wordCount: currentChapter.wordCount,
                openConsistencyCheckCount: currentChapter.qualityChecks.filter(
                  (check) => check.type === "consistency"
                    && (check.status === "pending" || check.status === "failed"),
                ).length,
                approvedBeatPlan: approvedBeatPlan ? {
                  id: approvedBeatPlan.id,
                  chapterGoal: approvedBeatPlan.chapterGoal,
                  sceneCount: approvedBeatPlan.sceneBeats.length,
                  totalEstimatedWords: approvedBeatPlan.totalEstimatedWords,
                } : null,
              } : undefined}
            />
          </section>

          <section className="workspace-pane workspace-editor-pane" hidden={activeView !== "reading"}>
            {currentChapter ? (
              <ChapterEditor
                key={`${currentChapter.id}:${currentChapter.updatedAt}`}
                view={activeView}
                readingSession={readingSession}
                userId={currentUser.id}
                novelId={novel.id}
                chapter={{
                  id: currentChapter.id,
                  title: currentChapter.title,
                  content: currentChapter.content,
                  status: currentChapter.status,
                  completedAt: currentChapter.completedAt,
                  updatedAt: currentChapter.updatedAt,
                }}
                chapterProgress={currentChapter.progress?.content ?? null}
                qualityChecks={currentChapter.qualityChecks.filter(
                  (check) => check.type === "consistency",
                )}
                styleName={novel.appliedStyle?.name}
              />
            ) : (
              <div className="panel empty">当前小说还没有章节，请先添加章节。</div>
            )}
          </section>

          <section className="workspace-pane workspace-library-pane" hidden={activeView !== "library"}>
            <LibraryPane
              novelId={novel.id}
              appliedStyleId={novel.appliedStyleId}
              active={activeView === "library"}
            />
          </section>
        </div>

        <aside
          id="workspace-review-rail"
          className="panel workspace-review-rail"
          aria-label="当前章节审核栏"
        />
      </div>
    </main>
  );
}

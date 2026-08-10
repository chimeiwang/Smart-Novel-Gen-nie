"use client";

import type { components } from "@inkforge/api-client";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { LogoutButton } from "@/features/auth/user-menu";
import { ChapterList } from "@/features/chapters/chapter-list";
import { ChapterEditor } from "@/features/editor/chapter-editor";
import { flushActiveChapterSave } from "@/features/editor/chapter-save-navigation";
import {
  buildSelectionAttachment,
  type SelectionBridge,
  type SelectionCaptureInput,
  type SelectionAttachment,
  type TransientSelection,
} from "@/features/editor/selection-identity";
import { countUnhandledQualityChecks } from "@/features/editor/quality-presentation";
import { ShortMediumWorkspace } from "@/features/short-medium/short-medium-workspace";
import { LibraryNavigation, LibraryPane, type LibraryItem } from "./library-pane";
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

type WorkspaceSection = "chapters" | "library";

export function WorkspaceShell({
  bootstrap,
  currentUser,
  initialView,
}: WorkspaceShellProps) {
  const { novel, chapters, currentChapter } = bootstrap;
  const [activeView, setActiveView] = useState<WorkspaceView>(initialView);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>(
    initialView === "library" ? "library" : "chapters",
  );
  const [chapterView, setChapterView] = useState<Exclude<WorkspaceView, "library">>(
    initialView === "reading" ? "reading" : "studio",
  );
  const [activeLibraryItem, setActiveLibraryItem] = useState<LibraryItem>("characters");
  const [chaptersExpanded, setChaptersExpanded] = useState(initialView !== "library");
  const [libraryExpanded, setLibraryExpanded] = useState(initialView === "library");
  const [readingSession, setReadingSession] = useState(0);
  const [switchingView, setSwitchingView] = useState<WorkspaceView | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [transientSelection, setTransientSelection] = useState<TransientSelection | null>(null);
  const [attachedSelection, setAttachedSelection] = useState<SelectionAttachment | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const selectionGenerationRef = useRef(0);
  const previousInitialViewRef = useRef(initialView);
  const totalCount = chapters.reduce((sum, item) => sum + item.wordCount, 0);
  const approvedBeatPlan = currentChapter?.approvedBeatPlan ?? null;

  const captureSelection = useCallback(async (input: SelectionCaptureInput) => {
    const generation = ++selectionGenerationRef.current;
    try {
      const attachment = await buildSelectionAttachment(input);
      if (selectionGenerationRef.current !== generation) return;
      setTransientSelection({ ...attachment, content: input.content });
      setSelectionError(null);
    } catch (error) {
      if (selectionGenerationRef.current !== generation) return;
      setSelectionError(error instanceof Error ? error.message : "无法读取选区");
    }
  }, []);
  const attachSelection = useCallback(() => {
    if (!transientSelection) return;
    if (attachedSelection) {
      setSelectionError("已有选区附件，请先移除后重新选择");
      return;
    }
    selectionGenerationRef.current += 1;
    setAttachedSelection(transientSelection);
    setTransientSelection(null);
    setSelectionError(null);
  }, [attachedSelection, transientSelection]);
  const removeSelection = useCallback(() => {
    selectionGenerationRef.current += 1;
    setAttachedSelection(null);
    setSelectionError(null);
  }, []);
  const reselectSelection = useCallback(() => {
    selectionGenerationRef.current += 1;
    setAttachedSelection(null);
    setTransientSelection(null);
    setSelectionError("已移除，请在来源处重新选择");
  }, []);
  const clearTransientSelection = useCallback(() => {
    selectionGenerationRef.current += 1;
    setTransientSelection(null);
  }, []);
  const clearAllSelection = useCallback(() => {
    selectionGenerationRef.current += 1;
    setTransientSelection(null);
    setAttachedSelection(null);
    setSelectionError(null);
  }, []);
  const markSelectionSourceChanged = useCallback((input: {
    resourceType: SelectionCaptureInput["resourceType"];
    resourceId: string;
    updatedAt: string;
    content: string;
  }) => {
    selectionGenerationRef.current += 1;
    setTransientSelection((candidate) => (
      candidate && candidate.resourceType === input.resourceType && candidate.resourceId === input.resourceId
        ? null
        : candidate
    ));
    setAttachedSelection((attachment) => {
      if (!attachment || attachment.resourceType !== input.resourceType || attachment.resourceId !== input.resourceId) return attachment;
      return { ...attachment, stale: true };
    });
  }, []);
  const visibleAttachedSelection = useMemo(() => (
    attachedSelection && attachedSelection.resourceType === "chapter_content"
      && attachedSelection.resourceId !== currentChapter?.id
      ? { ...attachedSelection, stale: true }
      : attachedSelection
  ), [attachedSelection, currentChapter?.id]);
  const visibleTransientSelection = useMemo(() => (
    transientSelection && transientSelection.resourceType === "chapter_content"
      && transientSelection.resourceId !== currentChapter?.id
      ? null
      : transientSelection
  ), [currentChapter?.id, transientSelection]);
  const selectionBridge = useMemo<SelectionBridge>(() => ({
    transientSelection: visibleTransientSelection,
    attachedSelection: visibleAttachedSelection,
    captureSelection,
    attachSelection,
    clearTransientSelection,
    clearAllSelection,
    removeSelection,
    reselectSelection,
    markSelectionSourceChanged,
  }), [attachSelection, captureSelection, clearAllSelection, clearTransientSelection, markSelectionSourceChanged, removeSelection, reselectSelection, visibleAttachedSelection, visibleTransientSelection]);

  const applyActiveView = useCallback((view: WorkspaceView) => {
    if (view === "reading") setReadingSession((current) => current + 1);
    setActiveView(view);
    if (view === "library") {
      setActiveSection("library");
      setLibraryExpanded(true);
    } else {
      setActiveSection("chapters");
      setChapterView(view);
      setChaptersExpanded(true);
    }
  }, []);

  useEffect(() => {
    if (previousInitialViewRef.current === initialView) return;
    previousInitialViewRef.current = initialView;
    const syncTimer = window.setTimeout(() => applyActiveView(initialView), 0);
    return () => window.clearTimeout(syncTimer);
  }, [applyActiveView, initialView]);

  const selectSection = async (
    section: WorkspaceSection,
    requestedChapterView?: Exclude<WorkspaceView, "library">,
  ): Promise<boolean> => {
    if (switchingView) return false;
    const nextView: WorkspaceView = section === "library"
      ? "library"
      : requestedChapterView ?? chapterView;
    clearTransientSelection();
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
      return true;
    } catch (error) {
      setViewError(formatWorkspaceViewSaveError(error));
      return false;
    } finally {
      setSwitchingView(null);
    }
  };

  const selectLibraryItem = async (item: LibraryItem) => {
    if (switchingView) return;
    clearTransientSelection();
    if (activeSection !== "library") {
      const switched = await selectSection("library");
      if (!switched) return;
    }
    setActiveLibraryItem(item);
  };

  if (novel.storyLengthProfile === "short_medium" && currentChapter) {
    return (
      <main className="page stack workspace-page">
        <header className="panel workspace-shell-header">
          <div className="workspace-shell-summary">
            <Link href="/" className="muted">← 返回</Link>
            <div>
              <h1 className="title-lg">{novel.name}</h1>
              <div className="meta">
                <span className="badge">中短篇</span>
                <span className="badge">目标 {novel.targetTotalWordCount ?? 20_000} 字</span>
              </div>
            </div>
          </div>
          <LogoutButton />
        </header>
        <ShortMediumWorkspace
          userId={currentUser.id}
          novelId={novel.id}
          targetTotalWordCount={novel.targetTotalWordCount ?? 20_000}
          chapter={{
            id: currentChapter.id,
            title: currentChapter.title,
            content: currentChapter.content,
            updatedAt: currentChapter.updatedAt,
          }}
        />
      </main>
    );
  }

  const chatChapter = currentChapter ? {
    id: currentChapter.id,
    title: currentChapter.title,
    status: currentChapter.status,
    wordCount: currentChapter.wordCount,
    openConsistencyCheckCount: countUnhandledQualityChecks(
      currentChapter.qualityChecks.filter((check) => check.type === "consistency"),
    ),
    approvedBeatPlan: approvedBeatPlan ? {
      id: approvedBeatPlan.id,
      chapterGoal: approvedBeatPlan.chapterGoal,
      sceneCount: approvedBeatPlan.sceneBeats.length,
      totalEstimatedWords: approvedBeatPlan.totalEstimatedWords,
    } : null,
  } : undefined;

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
        <LogoutButton />
      </header>

      {viewError ? <p className="workspace-view-error" role="alert">{viewError}</p> : null}

      <div className="workspace-shell" data-view={activeView} data-section={activeSection}>
        <aside className="panel workspace-left-navigation" aria-label="工作区导航">
          <section className="workspace-navigation-root">
            <button
              className={`workspace-navigation-root-button ${activeSection === "chapters" ? "active" : ""}`}
              type="button"
              aria-expanded={chaptersExpanded}
              onClick={() => {
                setChaptersExpanded((expanded) => !expanded);
                void selectSection("chapters");
              }}
            >
              <span>章节</span>
              <span aria-hidden="true">{chaptersExpanded ? "⌄" : "›"}</span>
            </button>
            {chaptersExpanded ? (
              <div className="workspace-navigation-root-content">
                <div className="workspace-chapter-mode-switcher" aria-label="章节视图">
                  {(["studio", "reading"] as const).map((view) => (
                    <button
                      key={view}
                      className={`workspace-view-button ${chapterView === view ? "active" : ""}`}
                      type="button"
                      aria-pressed={chapterView === view}
                      disabled={switchingView !== null}
                      onClick={() => void selectSection("chapters", view)}
                    >
                      {view === "studio" ? "AI 创作" : "阅读与小修"}
                    </button>
                  ))}
                </div>
                <ChapterList
                  novelId={novel.id}
                  activeChapterId={currentChapter?.id ?? ""}
                  chapters={chapters}
                  view={chapterView}
                  onChapterChangeReady={clearAllSelection}
                />
              </div>
            ) : null}
          </section>

          <section className="workspace-navigation-root">
            <button
              className={`workspace-navigation-root-button ${activeSection === "library" ? "active" : ""}`}
              type="button"
              aria-expanded={libraryExpanded}
              onClick={() => {
                setLibraryExpanded((expanded) => !expanded);
                void selectSection("library");
              }}
            >
              <span>创作资料</span>
              <span aria-hidden="true">{libraryExpanded ? "⌄" : "›"}</span>
            </button>
            {libraryExpanded ? (
              <LibraryNavigation
                activeItem={activeLibraryItem}
                onSelect={(item) => void selectLibraryItem(item)}
              />
            ) : null}
          </section>
        </aside>

        <div className="workspace-shell-main" data-view={activeView}>
          <section className="workspace-pane workspace-editor-pane" hidden={activeSection !== "chapters"}>
            {currentChapter ? (
              <ChapterEditor
                key={`${currentChapter.id}:${currentChapter.updatedAt}`}
                view={chapterView}
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
                chapterProgress={currentChapter.progress ?? null}
                qualityChecks={currentChapter.qualityChecks.filter((check) => check.type === "consistency")}
                styleName={novel.appliedStyle?.name}
                selectionBridge={selectionBridge}
              />
            ) : (
              <div className="panel empty">当前小说还没有章节，请先添加章节。</div>
            )}
          </section>

          <section className="workspace-pane workspace-library-pane" hidden={activeSection !== "library"}>
            <LibraryPane
              novelId={novel.id}
              appliedStyleId={novel.appliedStyleId}
              active={activeSection === "library"}
              activeItem={activeLibraryItem}
              onActiveItemChange={setActiveLibraryItem}
              showNavigation={false}
              selectionBridge={selectionBridge}
            />
          </section>
        </div>

        <aside className="workspace-collaboration-dock" aria-label="聊天协作与审核">
          <section className="workspace-pane workspace-agent-pane">
            <SmartWritingPanel
              novelId={novel.id}
              currentChapter={chatChapter}
              selectionBridge={selectionBridge}
            />
          </section>
          <aside
            id="workspace-review-rail"
            className="panel workspace-review-rail"
            aria-label="当前章节审核栏"
          />
        </aside>
      </div>
      {visibleTransientSelection ? (
        <div className="selection-action-bar" role="status">
          <span>已选 {visibleTransientSelection.selectedText.length} 字 · {visibleTransientSelection.sourceLabel}</span>
          <button className="button" type="button" onClick={attachSelection} disabled={Boolean(visibleAttachedSelection)}>
            让 AI 修改这段
          </button>
          <button className="button ghost" type="button" onClick={clearTransientSelection}>取消</button>
        </div>
      ) : null}
      {selectionError ? <div className="selection-error" role="alert">{selectionError}</div> : null}
    </main>
  );
}

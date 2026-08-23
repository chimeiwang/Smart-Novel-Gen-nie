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
import { countTextLength } from "@/shared/lib/word-count";
import { ShortMediumWorkspace } from "@/features/short-medium/short-medium-workspace";
import { VideoWorkspace } from "@/features/video/video-workspace";
import {
  LIBRARY_GROUPS,
  LibraryNavigation,
  LibraryPane,
  type LibraryItem,
} from "./library-pane";
import { SmartWritingPanel } from "./smart-writing-panel";
import { formatWorkspaceViewSaveError } from "./workspace-shell-state";
import { WorkspaceDialog } from "./workspace-dialog";
import {
  resolveWorkspaceViewForProfile,
  type WorkspaceView,
} from "./workspace-view";

type WorkspaceShellProps = {
  bootstrap: components["schemas"]["WorkspaceBootstrapResponse"];
  currentUser: components["schemas"]["UserResponse"];
  initialView: WorkspaceView;
};

type WorkspaceSection = "chapters" | "library" | "video";

type LiveChapterDraft = {
  title: string;
  content: string;
  wordCount: number;
  updatedAt?: string;
};

export function WorkspaceShell({
  bootstrap,
  currentUser,
  initialView,
}: WorkspaceShellProps) {
  const { novel, chapters, currentChapter } = bootstrap;
  const resolvedInitialView = resolveWorkspaceViewForProfile(
    initialView,
    novel.storyLengthProfile,
  );
  const [activeSection, setActiveSection] = useState<WorkspaceSection>(
    resolvedInitialView === "library"
      ? "library"
      : resolvedInitialView === "video"
        ? "video"
        : "chapters",
  );
  const [activeLibraryItem, setActiveLibraryItem] = useState<LibraryItem>("characters");
  const [libraryDialogOpen, setLibraryDialogOpen] = useState(
    resolvedInitialView === "library",
  );
  const [switchingView, setSwitchingView] = useState<WorkspaceView | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const [liveDrafts, setLiveDrafts] = useState<Record<string, LiveChapterDraft>>({});
  const [transientSelection, setTransientSelection] = useState<TransientSelection | null>(null);
  const [attachedSelection, setAttachedSelection] = useState<SelectionAttachment | null>(null);
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const selectionGenerationRef = useRef(0);
  const previousInitialViewRef = useRef(resolvedInitialView);
  const visibleChapters = chapters.map((chapter) => {
    const draft = liveDrafts[chapter.id];
    return draft
      ? { ...chapter, title: draft.title, wordCount: draft.wordCount }
      : chapter;
  });
  const currentDraft = currentChapter ? liveDrafts[currentChapter.id] : undefined;
  const visibleCurrentChapter = currentChapter
    ? {
        ...currentChapter,
        title: currentDraft?.title ?? currentChapter.title,
        content: currentDraft?.content ?? currentChapter.content,
        wordCount: currentDraft?.wordCount ?? currentChapter.wordCount,
        updatedAt: currentDraft?.updatedAt ?? currentChapter.updatedAt,
      }
    : undefined;
  const totalCount = visibleChapters.reduce((sum, item) => sum + item.wordCount, 0);
  const approvedBeatPlan = currentChapter?.approvedBeatPlan ?? null;

  const updateLiveDraft = useCallback((draft: {
    chapterId: string;
    title: string;
    content: string;
    wordCount: number;
    updatedAt?: string;
  }) => {
    setLiveDrafts((current) => ({
      ...current,
      [draft.chapterId]: {
        ...current[draft.chapterId],
        title: draft.title,
        content: draft.content,
        wordCount: draft.wordCount,
        ...(draft.updatedAt ? { updatedAt: draft.updatedAt } : {}),
      },
    }));
  }, []);

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

  const applyInitialView = useCallback((view: WorkspaceView) => {
    if (view === "library") {
      setActiveSection("library");
      setLibraryDialogOpen(true);
    } else if (view === "video") {
      setActiveSection("video");
      setLibraryDialogOpen(false);
    } else {
      setActiveSection("chapters");
      setLibraryDialogOpen(false);
    }
  }, []);

  useEffect(() => {
    // 修正非长篇的非法视频深链，保证地址栏与实际工作区一致。
    if (initialView !== resolvedInitialView) {
      const url = new URL(window.location.href);
      url.searchParams.set("view", resolvedInitialView);
      window.history.replaceState(window.history.state, "", url);
    }
    if (previousInitialViewRef.current === resolvedInitialView) return;
    previousInitialViewRef.current = resolvedInitialView;
    const syncTimer = window.setTimeout(() => applyInitialView(resolvedInitialView), 0);
    return () => window.clearTimeout(syncTimer);
  }, [applyInitialView, initialView, resolvedInitialView]);

  const commitSection = (section: WorkspaceSection) => {
    clearTransientSelection();
    setActiveSection(section);
    if (section !== "library") setLibraryDialogOpen(false);
    const url = new URL(window.location.href);
    url.searchParams.set(
      "view",
      section === "library" ? "library" : section === "video" ? "video" : "studio",
    );
    window.history.replaceState(window.history.state, "", url);
  };

  const selectSection = async (section: WorkspaceSection) => {
    if (switchingView || section === activeSection) return;
    if (section !== "video") {
      commitSection(section);
      return;
    }
    setViewError(null);
    setSwitchingView("video");
    try {
      await flushActiveChapterSave();
      commitSection("video");
    } catch (error) {
      setViewError(formatWorkspaceViewSaveError(error));
    } finally {
      setSwitchingView(null);
    }
  };

  const selectLibraryItem = async (item: LibraryItem) => {
    if (switchingView) return;
    clearTransientSelection();
    setViewError(null);
    setSwitchingView("library");
    try {
      await flushActiveChapterSave();
      setActiveSection("library");
      setActiveLibraryItem(item);
      setLibraryDialogOpen(true);
      const url = new URL(window.location.href);
      url.searchParams.set("view", "library");
      window.history.replaceState(window.history.state, "", url);
    } catch (error) {
      setViewError(formatWorkspaceViewSaveError(error));
    } finally {
      setSwitchingView(null);
    }
  };

  if (novel.storyLengthProfile === "short_medium") {
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
        {currentChapter ? (
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
        ) : (
          <div className="panel empty">当前小说还没有正文，请先创建内容。</div>
        )}
      </main>
    );
  }

  const chatChapter = visibleCurrentChapter ? {
    id: visibleCurrentChapter.id,
    title: visibleCurrentChapter.title,
    status: visibleCurrentChapter.status,
    wordCount: visibleCurrentChapter.wordCount,
    openConsistencyCheckCount: countUnhandledQualityChecks(
      visibleCurrentChapter.qualityChecks.filter((check) => check.type === "consistency"),
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

      <div className="workspace-shell" data-view="studio" data-section={activeSection}>
        <aside className="panel workspace-left-navigation" aria-label="工作区导航">
          <div className="workspace-primary-switcher" aria-label="工作区内容">
            {(["chapters", "library", "video"] as const).map((section) => (
              <button
                key={section}
                className={`workspace-view-button ${activeSection === section ? "active" : ""}`}
                type="button"
                aria-pressed={activeSection === section}
                disabled={switchingView !== null}
                onClick={() => void selectSection(section)}
              >
                {section === "chapters"
                  ? "章节"
                  : section === "library"
                    ? "创作资料"
                    : "视频制作"}
              </button>
            ))}
          </div>

          <div className="workspace-primary-navigation-content">
            {activeSection !== "library" ? (
              <ChapterList
                novelId={novel.id}
                activeChapterId={currentChapter?.id ?? ""}
                chapters={visibleChapters}
                view={activeSection === "video" ? "video" : "studio"}
                onChapterChangeReady={clearAllSelection}
              />
            ) : (
              <LibraryNavigation
                activeItem={activeLibraryItem}
                onSelect={(item) => void selectLibraryItem(item)}
              />
            )}
          </div>
        </aside>

        <div className="workspace-shell-main" data-view="studio">
          {activeSection === "video" ? (
            <section className="workspace-pane workspace-video-pane">
              <VideoWorkspace
                novelId={novel.id}
                novelName={novel.name}
                currentChapter={visibleCurrentChapter ? {
                  id: visibleCurrentChapter.id,
                  title: visibleCurrentChapter.title,
                  content: visibleCurrentChapter.content,
                  updatedAt: visibleCurrentChapter.updatedAt,
                } : undefined}
              />
            </section>
          ) : (
            <section className="workspace-pane workspace-editor-pane">
            {currentChapter ? (
              <ChapterEditor
                key={`${currentChapter.id}:${currentChapter.updatedAt}`}
                view="studio"
                readingSession={0}
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
                onDraftChange={updateLiveDraft}
                onSaved={updateLiveDraft}
              />
            ) : (
              <div className="panel empty">当前小说还没有章节，请先添加章节。</div>
            )}
            </section>
          )}
        </div>

        {activeSection !== "video" ? (
          <aside className="workspace-collaboration-dock" aria-label="聊天协作">
            <section className="workspace-pane workspace-agent-pane">
              <SmartWritingPanel
                novelId={novel.id}
                currentChapter={chatChapter}
                selectionBridge={selectionBridge}
              />
            </section>
          </aside>
        ) : null}
      </div>
      <WorkspaceDialog
        open={libraryDialogOpen}
        title={LIBRARY_GROUPS.flatMap((group) => group.items).find((item) => item.key === activeLibraryItem)?.label ?? "创作资料"}
        description="编辑当前作品的设定、规划与写作素材"
        variant="library"
        onClose={() => setLibraryDialogOpen(false)}
      >
        <LibraryPane
          novelId={novel.id}
          appliedStyleId={novel.appliedStyleId}
          active={libraryDialogOpen}
          activeItem={activeLibraryItem}
          onActiveItemChange={setActiveLibraryItem}
          showNavigation={false}
          selectionBridge={selectionBridge}
        />
      </WorkspaceDialog>
      {visibleTransientSelection ? (
        <div className="selection-action-bar" role="status">
          <span>已选 {countTextLength(visibleTransientSelection.selectedText)} 字 · {visibleTransientSelection.sourceLabel}</span>
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

"use client";

import type { components } from "@inkforge/api-client";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, useTransition } from "react";

import { Modal } from "@/components/modal";
import { ChapterList } from "@/features/chapters/chapter-list";
import { LorePanel } from "@/features/lore/lore-panel";
import { OutlinePanel } from "@/features/outline/outline-panel";
import { ProgressPanel } from "@/features/progress/progress-panel";
import { ReferencePanel } from "@/features/references/reference-panel";
import { StylePanel } from "@/features/styles/style-panel";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import { countTextLength } from "@/shared/lib/word-count";
import {
  STORY_LENGTH_PROFILE_CONFIG,
  normalizeStoryLengthProfile,
  type StoryLengthProfile,
} from "@/shared/contracts/story-length-profile";
import {
  DeferredWorkspaceLoader,
  groupForTab,
  type DeferredGroupState,
} from "./deferred-workspace";
import { subscribeWorkspaceInvalidation } from "./workspace-invalidation";
import type { WorkspaceView } from "./workspace-view";

type SidebarTabKey = "chapters" | "lore" | "style" | "reference";
type PlanningData = components["schemas"]["WorkspacePlanningResponse"];

type SidebarTabsProps = {
  novelId: string;
  activeChapterId: string;
  chapters: components["schemas"]["WorkspaceChapterSummary"][];
  appliedStyleId: string | null;
  view?: WorkspaceView;
  showChapters?: boolean;
};

const TAB_ITEMS: Array<{ key: SidebarTabKey; label: string }> = [
  { key: "chapters", label: "章节" },
  { key: "lore", label: "设定" },
  { key: "style", label: "文风" },
  { key: "reference", label: "资料" },
];

function toWritingBibleForm(writingBible: PlanningData["writingBible"]) {
  return {
    storyLengthProfile: normalizeStoryLengthProfile(writingBible?.storyLengthProfile),
    targetTotalWordCount: writingBible?.targetTotalWordCount
      ? String(writingBible.targetTotalWordCount)
      : "",
    genre: writingBible?.genre ?? "",
    targetReaders: writingBible?.targetReaders ?? "",
    coreSellingPoint: writingBible?.coreSellingPoint ?? "",
    readerPromise: writingBible?.readerPromise ?? "",
    appealModel: writingBible?.appealModel ?? "",
    taboo: writingBible?.taboo ?? "",
    comparableTitles: writingBible?.comparableTitles ?? "",
    notes: writingBible?.notes ?? "",
  };
}

function DeferredStatusPanel({
  state,
  onRetry,
}: {
  state: DeferredGroupState<unknown>;
  onRetry: () => void;
}) {
  if (state.status === "error") {
    return (
      <div className="empty stack">
        <span>{state.error ?? "加载失败，请稍后重试"}</span>
        <button className="button secondary" type="button" onClick={onRetry}>
          重试
        </button>
      </div>
    );
  }
  return <div className="empty">加载中...</div>;
}

export function SidebarTabs({
  novelId,
  activeChapterId,
  chapters,
  appliedStyleId,
  view = "studio",
  showChapters = true,
}: SidebarTabsProps) {
  const [activeTab, setActiveTab] = useState<SidebarTabKey>(showChapters ? "chapters" : "lore");
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const [loader] = useState(() => new DeferredWorkspaceLoader({
    lore: async () => requireApiData(await browserApi.GET(
      "/api/v1/novels/{novel_id}/workspace/lore",
      { params: { path: { novel_id: novelId } } },
    )),
    planning: async () => requireApiData(await browserApi.GET(
      "/api/v1/novels/{novel_id}/workspace/planning",
      { params: { path: { novel_id: novelId } } },
    )),
    resources: async () => requireApiData(await browserApi.GET(
      "/api/v1/novels/{novel_id}/workspace/resources",
      { params: { path: { novel_id: novelId } } },
    )),
  }));
  const deferred = useSyncExternalStore(
    loader.subscribe,
    loader.snapshot,
    loader.snapshot,
  );
  useEffect(
    () => subscribeWorkspaceInvalidation(novelId, (groups) => {
      for (const group of groups) loader.invalidate(group);
      const activeGroup = groupForTab(activeTab);
      if (activeGroup && groups.includes(activeGroup)) {
        void loader.load(activeGroup).catch(() => undefined);
      }
    }),
    [activeTab, loader, novelId],
  );
  const loadGroup = (group: NonNullable<ReturnType<typeof groupForTab>>) => {
    void loader.load(group).catch(() => undefined);
  };
  const refreshGroup = (group: NonNullable<ReturnType<typeof groupForTab>>) => {
    void loader.refresh(group).catch(() => undefined);
  };

  // 弹窗状态：进度、故事进展、故事背景、世界设定、大纲
  const [modalKey, setModalKey] = useState<
    "progress" | "storyProgress" | "storyBackground" | "worldSetting" | "writingBible" | "outline" | null
  >(null);
  const [storyProgressDraft, setStoryProgressDraft] = useState<string | null>(null);
  const [storyBackgroundDraft, setStoryBackgroundDraft] = useState<string | null>(null);
  const [worldSettingDraft, setWorldSettingDraft] = useState<string | null>(null);
  const [writingBibleDraft, setWritingBibleDraft] = useState<
    ReturnType<typeof toWritingBibleForm> | null
  >(null);

  const planning = deferred.planning.data;
  const storyProgressContent = storyProgressDraft ?? planning?.storyProgress ?? "";
  const storyBackgroundContent =
    storyBackgroundDraft ?? planning?.storyBackground?.content ?? "";
  const worldSettingContent = worldSettingDraft ?? planning?.worldSetting?.content ?? "";
  const writingBibleForm =
    writingBibleDraft ?? toWritingBibleForm(planning?.writingBible ?? null);
  const planningFallback = (
    <DeferredStatusPanel
      state={deferred.planning}
      onRetry={() => loadGroup("planning")}
    />
  );

  const openModal = (key: NonNullable<typeof modalKey>) => {
    if (key === "storyProgress") setStoryProgressDraft(null);
    if (key === "storyBackground") setStoryBackgroundDraft(null);
    if (key === "worldSetting") setWorldSettingDraft(null);
    if (key === "writingBible") setWritingBibleDraft(null);
    setModalKey(key);
    loadGroup("planning");
  };

  const handleSaveStoryProgress = () => {
    startTransition(async () => {
      requireApiData(await browserApi.PUT("/api/v1/novels/{novel_id}/story-progress", {
        params: { path: { novel_id: novelId } },
        body: { content: storyProgressContent },
      }));
      setStoryProgressDraft(null);
      refreshGroup("planning");
      router.refresh();
    });
  };

  const handleSaveStoryBackground = () => {
    startTransition(async () => {
      requireApiData(await browserApi.PUT("/api/v1/novels/{novel_id}/story-background", {
        params: { path: { novel_id: novelId } },
        body: { content: storyBackgroundContent },
      }));
      setStoryBackgroundDraft(null);
      refreshGroup("planning");
      router.refresh();
    });
  };

  const handleSaveWorldSetting = () => {
    startTransition(async () => {
      requireApiData(await browserApi.PUT("/api/v1/novels/{novel_id}/world-setting", {
        params: { path: { novel_id: novelId } },
        body: { content: worldSettingContent },
      }));
      setWorldSettingDraft(null);
      refreshGroup("planning");
      router.refresh();
    });
  };

  const handleSaveWritingBible = () => {
    startTransition(async () => {
      requireApiData(await browserApi.PUT("/api/v1/novels/{novel_id}/writing-bible", {
        params: { path: { novel_id: novelId } },
        body: {
          ...writingBibleForm,
          targetTotalWordCount: Number(writingBibleForm.targetTotalWordCount) || null,
        },
      }));
      setWritingBibleDraft(null);
      refreshGroup("planning");
      router.refresh();
    });
  };

  const updateWritingBibleField = (field: keyof typeof writingBibleForm, value: string) => {
    setWritingBibleDraft((current) => ({ ...(current ?? writingBibleForm), [field]: value }));
  };

  const selectWritingBibleProfile = (profile: StoryLengthProfile) => {
    setWritingBibleDraft((current) => {
      const base = current ?? writingBibleForm;
      return {
        ...base,
        storyLengthProfile: profile,
        targetTotalWordCount: base.targetTotalWordCount || (profile === "short_medium" ? "80000" : "1000000"),
      };
    });
  };

  return (
    <div className="panel panel-flex sidebar-panel">
      <div className="panel-header">
        <div className="tabs sidebar-tabs">
          {TAB_ITEMS.filter((tab) => showChapters || tab.key !== "chapters").map((tab) => (
            <button
              key={tab.key}
              className={`tab-button ${activeTab === tab.key ? "active" : ""}`}
              type="button"
              onClick={() => {
                setActiveTab(tab.key);
                const group = groupForTab(tab.key);
                if (group) loadGroup(group);
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="panel-body">
        {activeTab === "chapters" ? (
          <ChapterList
            novelId={novelId}
            activeChapterId={activeChapterId}
            chapters={chapters}
            view={view}
          />
        ) : null}

        {activeTab === "lore" ? (
          deferred.lore.status === "success" && deferred.lore.data ? (
            <LorePanel
              novelId={novelId}
              characters={deferred.lore.data.characters}
              items={deferred.lore.data.items}
              locations={deferred.lore.data.locations}
              factions={deferred.lore.data.factions}
              glossaries={deferred.lore.data.glossaries}
              onChanged={() => refreshGroup("lore")}
            />
          ) : (
            <DeferredStatusPanel
              state={deferred.lore}
              onRetry={() => loadGroup("lore")}
            />
          )
        ) : null}

        {activeTab === "style" ? (
          deferred.resources.status === "success" && deferred.resources.data ? (
            <StylePanel
              novelId={novelId}
              appliedStyleId={deferred.resources.data.appliedStyle?.id ?? appliedStyleId}
              styles={deferred.resources.data.styles}
              onChanged={() => refreshGroup("resources")}
            />
          ) : (
            <DeferredStatusPanel
              state={deferred.resources}
              onRetry={() => loadGroup("resources")}
            />
          )
        ) : null}

        {activeTab === "reference" ? (
          deferred.resources.status === "success" && deferred.resources.data ? (
            <ReferencePanel
              novelId={novelId}
              references={deferred.resources.data.references}
              onChanged={() => refreshGroup("resources")}
            />
          ) : (
            <DeferredStatusPanel
              state={deferred.resources}
              onRetry={() => loadGroup("resources")}
            />
          )
        ) : null}
      </div>

      <div className="panel-footer">
        <div className="edit-buttons">
          <button type="button" className="edit-btn" onClick={() => openModal("progress")}>剧情进度</button>
          <button type="button" className="edit-btn" onClick={() => openModal("storyProgress")}>故事进展</button>
          <button type="button" className="edit-btn" onClick={() => openModal("storyBackground")}>故事背景</button>
          <button type="button" className="edit-btn" onClick={() => openModal("worldSetting")}>世界设定</button>
          <button type="button" className="edit-btn" onClick={() => openModal("writingBible")}>作品圣经</button>
          <button type="button" className="edit-btn" onClick={() => openModal("outline")}>大纲</button>
        </div>
      </div>

      <Modal title="剧情进度" open={modalKey === "progress"} onClose={() => setModalKey(null)}>
        {planning ? (
          <ProgressPanel
            novelId={novelId}
            progress={planning.plotProgress}
            onChanged={() => refreshGroup("planning")}
          />
        ) : planningFallback}
      </Modal>

      <Modal title="故事进展" description="记录故事整体进展" open={modalKey === "storyProgress"} onClose={() => setModalKey(null)}>
        {planning ? <div className="stack">
          <textarea
            className="textarea modal-textarea"
            value={storyProgressContent}
            onChange={(e) => setStoryProgressDraft(e.target.value)}
            placeholder="记录故事的整体进展、关键转折、伏笔等..."
          />
          <div className="row row-between">
            <span className="muted">{countTextLength(storyProgressContent)} / 30000 字</span>
            <button className="button" type="button" onClick={handleSaveStoryProgress}>
              {pending ? "保存中..." : "保存"}
            </button>
          </div>
        </div> : planningFallback}
      </Modal>

      <Modal title="故事背景" description="描述故事的基础背景" open={modalKey === "storyBackground"} onClose={() => setModalKey(null)}>
        {planning ? <div className="stack">
          <textarea
            className="textarea modal-textarea"
            value={storyBackgroundContent}
            onChange={(e) => setStoryBackgroundDraft(e.target.value)}
            placeholder="描述故事的基础背景，如时代背景、起始事件、核心冲突等..."
          />
          <div className="row row-end">
            <button className="button" type="button" onClick={handleSaveStoryBackground}>
              {pending ? "保存中..." : "保存"}
            </button>
          </div>
        </div> : planningFallback}
      </Modal>

      <Modal title="世界设定" description="描述世界的设定" open={modalKey === "worldSetting"} onClose={() => setModalKey(null)}>
        {planning ? <div className="stack">
          <textarea
            className="textarea modal-textarea"
            value={worldSettingContent}
            onChange={(e) => setWorldSettingDraft(e.target.value)}
            placeholder="描述世界的设定，如世界类型、力量体系、世界规则、历史概述等..."
          />
          <div className="row row-end">
            <button className="button" type="button" onClick={handleSaveWorldSetting}>
              {pending ? "保存中..." : "保存"}
            </button>
          </div>
        </div> : planningFallback}
      </Modal>

      <Modal title="作品圣经" description="记录商业定位、读者承诺和写作禁忌" open={modalKey === "writingBible"} onClose={() => setModalKey(null)}>
        {planning ? <div className="stack">
          <div className="stack">
            <span className="label">创作模式</span>
            <div className="story-profile-grid">
              {(["short_medium", "long_serial"] as const).map((profile) => {
                const config = STORY_LENGTH_PROFILE_CONFIG[profile];
                const active = writingBibleForm.storyLengthProfile === profile;
                return (
                  <button
                    key={profile}
                    className={`story-profile-option ${active ? "active" : ""}`}
                    type="button"
                    aria-pressed={active}
                    onClick={() => selectWritingBibleProfile(profile)}
                  >
                    <span>{config.label}</span>
                    <small>
                      {config.targetWords[0]}-{config.targetWords[1]} 字 · {config.chapterCount[0]}-{config.chapterCount[1]} 章
                    </small>
                  </button>
                );
              })}
            </div>
          </div>
          <label className="stack">
            <span className="label">目标总字数</span>
            <input
              className="input"
              inputMode="numeric"
              value={writingBibleForm.targetTotalWordCount}
              onChange={(e) => updateWritingBibleField("targetTotalWordCount", e.target.value)}
              placeholder="例如：80000"
            />
          </label>
          <div className="grid-two">
            <label className="stack">
              <span className="label">题材/频道</span>
              <input
                className="input"
                value={writingBibleForm.genre}
                onChange={(e) => updateWritingBibleField("genre", e.target.value)}
                placeholder="如：东方玄幻、都市异能、女频古言"
              />
            </label>
            <label className="stack">
              <span className="label">目标读者</span>
              <input
                className="input"
                value={writingBibleForm.targetReaders}
                onChange={(e) => updateWritingBibleField("targetReaders", e.target.value)}
                placeholder="读者画像、偏好、雷点"
              />
            </label>
          </div>
          <label className="stack">
            <span className="label">核心卖点</span>
            <textarea
              className="textarea textarea-resize"
              value={writingBibleForm.coreSellingPoint}
              onChange={(e) => updateWritingBibleField("coreSellingPoint", e.target.value)}
              placeholder="这本书最值得读者追下去的独特吸引力"
            />
          </label>
          <label className="stack">
            <span className="label">读者承诺</span>
            <textarea
              className="textarea textarea-resize"
              value={writingBibleForm.readerPromise}
              onChange={(e) => updateWritingBibleField("readerPromise", e.target.value)}
              placeholder="读者持续阅读后会得到什么情绪回报或故事体验"
            />
          </label>
          <label className="stack">
            <span className="label">爽点/情绪收益模型</span>
            <textarea
              className="textarea textarea-resize"
              value={writingBibleForm.appealModel}
              onChange={(e) => updateWritingBibleField("appealModel", e.target.value)}
              placeholder="升级、打脸、探索、关系拉扯、悬念、反转等"
            />
          </label>
          <div className="grid-two">
            <label className="stack">
              <span className="label">雷点/禁忌</span>
              <textarea
                className="textarea textarea-resize"
                value={writingBibleForm.taboo}
                onChange={(e) => updateWritingBibleField("taboo", e.target.value)}
                placeholder="不希望出现的剧情、写法或人设偏移"
              />
            </label>
            <label className="stack">
              <span className="label">对标方向</span>
              <textarea
                className="textarea textarea-resize"
                value={writingBibleForm.comparableTitles}
                onChange={(e) => updateWritingBibleField("comparableTitles", e.target.value)}
                placeholder="参考作品、平台风格、目标质感"
              />
            </label>
          </div>
          <label className="stack">
            <span className="label">编辑备注</span>
            <textarea
              className="textarea modal-textarea"
              value={writingBibleForm.notes}
              onChange={(e) => updateWritingBibleField("notes", e.target.value)}
              placeholder="其他商业性判断、长期写作约束、需要坚持的作者意图"
            />
          </label>
          <div className="row row-end">
            <button className="button" type="button" onClick={handleSaveWritingBible}>
              {pending ? "保存中..." : "保存"}
            </button>
          </div>
        </div> : planningFallback}
      </Modal>

      <Modal title="大纲" description="写下故事的主要脉络，智能写作时会参考这里" open={modalKey === "outline"} onClose={() => setModalKey(null)}>
        {planning ? (
          <OutlinePanel
            novelId={novelId}
            outline={planning.outline}
            outlineNodes={planning.outlineNodes}
            onChanged={() => refreshGroup("planning")}
          />
        ) : planningFallback}
      </Modal>

    </div>
  );
}

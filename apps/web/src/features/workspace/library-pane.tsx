"use client";

import type { components } from "@inkforge/api-client";
import { useRouter } from "next/navigation";
import { useEffect, useState, useSyncExternalStore, useTransition } from "react";

import { LorePanel } from "@/features/lore/lore-panel";
import { OutlinePanel } from "@/features/outline/outline-panel";
import { ProgressPanel } from "@/features/progress/progress-panel";
import { ReferencePanel } from "@/features/references/reference-panel";
import { StylePanel } from "@/features/styles/style-panel";
import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import {
  STORY_LENGTH_PROFILE_CONFIG,
  normalizeStoryLengthProfile,
  type StoryLengthProfile,
} from "@/shared/contracts/story-length-profile";
import { countTextLength } from "@/shared/lib/word-count";
import {
  DeferredWorkspaceLoader,
  groupForTab,
  type DeferredGroupState,
  type WorkspaceGroup,
} from "./deferred-workspace";
import { subscribeWorkspaceInvalidation } from "./workspace-invalidation";

type LoreItem = "characters" | "locations" | "factions" | "items" | "glossaries";
type LibraryItem = LoreItem
  | "storyBackground"
  | "worldSetting"
  | "outline"
  | "progress"
  | "storyProgress"
  | "writingBible"
  | "style"
  | "references";
type PlanningData = components["schemas"]["WorkspacePlanningResponse"];

type LibraryPaneProps = {
  novelId: string;
  appliedStyleId: string | null;
  active: boolean;
};

const LIBRARY_GROUPS: Array<{
  label: string;
  items: Array<{ key: LibraryItem; label: string }>;
}> = [
  {
    label: "设定",
    items: [
      { key: "characters", label: "角色" },
      { key: "locations", label: "地点" },
      { key: "factions", label: "势力" },
      { key: "items", label: "物品" },
      { key: "glossaries", label: "术语" },
      { key: "storyBackground", label: "故事背景" },
      { key: "worldSetting", label: "世界设定" },
    ],
  },
  {
    label: "故事规划",
    items: [
      { key: "outline", label: "大纲" },
      { key: "progress", label: "剧情进度" },
      { key: "storyProgress", label: "故事进展" },
    ],
  },
  {
    label: "写作规则与素材",
    items: [
      { key: "writingBible", label: "作品圣经" },
      { key: "style", label: "文风" },
      { key: "references", label: "参考资料" },
    ],
  },
];

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
        <button className="button secondary" type="button" onClick={onRetry}>重试</button>
      </div>
    );
  }
  return <div className="empty">加载中...</div>;
}

function PlanningTextEditor({
  title,
  description,
  initialValue,
  placeholder,
  onSave,
}: {
  title: string;
  description: string;
  initialValue: string;
  placeholder: string;
  onSave: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState(initialValue);
  const [pending, startTransition] = useTransition();

  return (
    <section className="library-form-section stack">
      <div>
        <h3 className="title-md">{title}</h3>
        <p className="muted">{description}</p>
      </div>
      <textarea
        className="textarea library-long-textarea"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder={placeholder}
      />
      <div className="row row-between">
        <span className="muted">{countTextLength(value)} 字</span>
        <button
          className="button"
          type="button"
          disabled={pending}
          onClick={() => startTransition(() => onSave(value))}
        >
          {pending ? "保存中..." : "保存"}
        </button>
      </div>
    </section>
  );
}

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

function WritingBibleEditor({
  novelId,
  writingBible,
  onChanged,
}: {
  novelId: string;
  writingBible: PlanningData["writingBible"];
  onChanged: () => void;
}) {
  const [form, setForm] = useState(() => toWritingBibleForm(writingBible));
  const [pending, startTransition] = useTransition();
  const router = useRouter();
  const update = (field: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };
  const selectProfile = (profile: StoryLengthProfile) => {
    setForm((current) => ({
      ...current,
      storyLengthProfile: profile,
      targetTotalWordCount: current.targetTotalWordCount
        || (profile === "short_medium" ? "80000" : "1000000"),
    }));
  };
  const save = () => startTransition(async () => {
    requireApiData(await browserApi.PUT("/api/v1/novels/{novel_id}/writing-bible", {
      params: { path: { novel_id: novelId } },
      body: {
        ...form,
        targetTotalWordCount: Number(form.targetTotalWordCount) || null,
      },
    }));
    onChanged();
    router.refresh();
  });

  return (
    <section className="library-form-section stack">
      <div>
        <h3 className="title-md">作品圣经</h3>
        <p className="muted">集中维护作品定位、读者承诺和长期写作约束。</p>
      </div>
      <div className="story-profile-grid">
        {(["short_medium", "long_serial"] as const).map((profile) => {
          const config = STORY_LENGTH_PROFILE_CONFIG[profile];
          return (
            <button
              key={profile}
              className={`story-profile-option ${form.storyLengthProfile === profile ? "active" : ""}`}
              type="button"
              aria-pressed={form.storyLengthProfile === profile}
              onClick={() => selectProfile(profile)}
            >
              <span>{config.label}</span>
              <small>{config.targetWords[0]}-{config.targetWords[1]} 字</small>
            </button>
          );
        })}
      </div>
      <div className="library-form-grid">
        <label className="stack">
          <span className="label">目标总字数</span>
          <input className="input" inputMode="numeric" value={form.targetTotalWordCount} onChange={(event) => update("targetTotalWordCount", event.target.value)} />
        </label>
        <label className="stack">
          <span className="label">题材/频道</span>
          <input className="input" value={form.genre} onChange={(event) => update("genre", event.target.value)} />
        </label>
        <label className="stack">
          <span className="label">目标读者</span>
          <input className="input" value={form.targetReaders} onChange={(event) => update("targetReaders", event.target.value)} />
        </label>
      </div>
      {([
        ["coreSellingPoint", "核心卖点"],
        ["readerPromise", "读者承诺"],
        ["appealModel", "爽点/情绪收益模型"],
        ["taboo", "雷点/禁忌"],
        ["comparableTitles", "对标方向"],
        ["notes", "编辑备注"],
      ] as const).map(([field, label]) => (
        <label className="stack" key={field}>
          <span className="label">{label}</span>
          <textarea className="textarea textarea-resize" value={form[field]} onChange={(event) => update(field, event.target.value)} />
        </label>
      ))}
      <div className="row row-end">
        <button className="button" type="button" disabled={pending} onClick={save}>
          {pending ? "保存中..." : "保存"}
        </button>
      </div>
    </section>
  );
}

export function LibraryPane({ novelId, appliedStyleId, active }: LibraryPaneProps) {
  const [activeItem, setActiveItem] = useState<LibraryItem>("characters");
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
  const deferred = useSyncExternalStore(loader.subscribe, loader.snapshot, loader.snapshot);

  useEffect(() => {
    if (!active) return;
    const group = groupForTab(activeItem);
    if (group) void loader.load(group).catch(() => undefined);
  }, [active, activeItem, loader]);

  useEffect(
    () => subscribeWorkspaceInvalidation(novelId, (groups) => {
      for (const group of groups) loader.invalidate(group);
      const activeGroup = groupForTab(activeItem);
      if (active && activeGroup && groups.includes(activeGroup)) {
        void loader.load(activeGroup).catch(() => undefined);
      }
    }),
    [active, activeItem, loader, novelId],
  );

  const refresh = (group: WorkspaceGroup) => {
    void loader.refresh(group).catch(() => undefined);
  };
  const retry = (group: WorkspaceGroup) => {
    void loader.retry(group).catch(() => undefined);
  };
  const savePlanningText = async (
    path: "/api/v1/novels/{novel_id}/story-progress"
      | "/api/v1/novels/{novel_id}/story-background"
      | "/api/v1/novels/{novel_id}/world-setting",
    content: string,
  ) => {
    requireApiData(await browserApi.PUT(path, {
      params: { path: { novel_id: novelId } },
      body: { content },
    }));
    refresh("planning");
    router.refresh();
  };

  const group = groupForTab(activeItem);
  const groupState = group ? deferred[group] : null;
  const selectedLabel = LIBRARY_GROUPS.flatMap((section) => section.items)
    .find((item) => item.key === activeItem)?.label;

  const renderDetail = () => {
    if (!group || !groupState || groupState.status !== "success" || !groupState.data) {
      return group && groupState
        ? <DeferredStatusPanel state={groupState} onRetry={() => retry(group)} />
        : null;
    }
    if (["characters", "locations", "factions", "items", "glossaries"].includes(activeItem)) {
      const lore = deferred.lore.data;
      if (!lore) return null;
      return (
        <LorePanel
          novelId={novelId}
          characters={lore.characters}
          items={lore.items}
          locations={lore.locations}
          factions={lore.factions}
          glossaries={lore.glossaries}
          selectedTab={activeItem as LoreItem}
          showTabs={false}
          onChanged={() => refresh("lore")}
        />
      );
    }
    if (activeItem === "style") {
      const resources = deferred.resources.data;
      return resources ? (
        <StylePanel
          novelId={novelId}
          appliedStyleId={resources.appliedStyle?.id ?? appliedStyleId}
          styles={resources.styles}
          onChanged={() => refresh("resources")}
        />
      ) : null;
    }
    if (activeItem === "references") {
      const resources = deferred.resources.data;
      return resources ? (
        <ReferencePanel
          novelId={novelId}
          references={resources.references}
          onChanged={() => refresh("resources")}
        />
      ) : null;
    }
    const planning = deferred.planning.data;
    if (!planning) return null;
    if (activeItem === "outline") {
      return <OutlinePanel novelId={novelId} outline={planning.outline} outlineNodes={planning.outlineNodes} onChanged={() => refresh("planning")} />;
    }
    if (activeItem === "progress") {
      return <ProgressPanel novelId={novelId} progress={planning.plotProgress} onChanged={() => refresh("planning")} />;
    }
    if (activeItem === "storyProgress") {
      return <PlanningTextEditor title="故事进展" description="记录故事整体进展、关键转折和伏笔。" initialValue={planning.storyProgress ?? ""} placeholder="记录故事的整体进展..." onSave={(value) => savePlanningText("/api/v1/novels/{novel_id}/story-progress", value)} />;
    }
    if (activeItem === "storyBackground") {
      return <PlanningTextEditor title="故事背景" description="描述故事的基础背景和核心冲突。" initialValue={planning.storyBackground?.content ?? ""} placeholder="描述故事的时代背景、起始事件和核心冲突..." onSave={(value) => savePlanningText("/api/v1/novels/{novel_id}/story-background", value)} />;
    }
    if (activeItem === "worldSetting") {
      return <PlanningTextEditor title="世界设定" description="描述世界类型、力量体系、规则和历史。" initialValue={planning.worldSetting?.content ?? ""} placeholder="描述世界的设定..." onSave={(value) => savePlanningText("/api/v1/novels/{novel_id}/world-setting", value)} />;
    }
    return <WritingBibleEditor novelId={novelId} writingBible={planning.writingBible} onChanged={() => refresh("planning")} />;
  };

  return (
    <div className="library-pane">
      <nav className="panel library-pane-navigation" aria-label="创作资料分类">
        <div className="panel-header">
          <div>
            <h2 className="title-md">创作资料</h2>
            <p className="muted">设定、规划与写作素材</p>
          </div>
        </div>
        <div className="panel-body library-navigation-body">
          {LIBRARY_GROUPS.map((section) => (
            <section className="library-navigation-section" key={section.label}>
              <h3>{section.label}</h3>
              {section.items.map((item) => (
                <button
                  key={item.key}
                  className={`library-navigation-item ${activeItem === item.key ? "active" : ""}`}
                  type="button"
                  aria-pressed={activeItem === item.key}
                  onClick={() => setActiveItem(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </section>
          ))}
        </div>
      </nav>
      <section className="panel library-pane-detail" aria-label={`${selectedLabel ?? "创作资料"}详情`}>
        <div className="panel-body library-detail-body">{renderDetail()}</div>
      </section>
    </div>
  );
}

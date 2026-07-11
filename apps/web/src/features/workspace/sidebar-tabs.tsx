"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { browserApi } from "@/lib/api/browser";
import { requireApiData } from "@/lib/api/response";
import { ChapterList } from "@/features/chapters/chapter-list";
import { LorePanel } from "@/features/lore/lore-panel";
import { OutlinePanel } from "@/features/outline/outline-panel";
import { ProgressPanel } from "@/features/progress/progress-panel";
import { ReferencePanel } from "@/features/references/reference-panel";
import { StylePanel } from "@/features/styles/style-panel";
import { Modal } from "@/components/modal";
import {
  STORY_LENGTH_PROFILE_CONFIG,
  normalizeStoryLengthProfile,
  type StoryLengthProfile,
} from "@/shared/contracts/story-length-profile";

type SidebarTabKey =
  | "chapters"
  | "lore"
  | "style"
  | "progress"
  | "storyProgress"
  | "storyBackground"
  | "worldSetting"
  | "outline"
  | "reference";

// 角色状态枚举
type CharacterStatus = "active" | "missing" | "dead" | "imprisoned" | "unknown";

// 关系类型枚举
type RelationType = "family" | "master_student" | "friend" | "enemy" | "ally" | "lover" | "rival" | "subordinate" | "acquaintance" | "other";

type SidebarTabsProps = {
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
  characters: Array<{
    id: string;
    name: string;
    aliases: string | null;
    gender: string | null;
    age: string | null;
    appearance: string | null;
    personality: string | null;
    identity: string | null;
    background: string | null;
    coreDesire: string | null;
    behaviorBoundaries: string | null;
    speechStyle: string | null;
    relationshipPrinciples: string | null;
    shortTermGoal: string | null;
    factionId: string | null;
    faction: { id: string; name: string } | null;
    // 新增：实力相关
    powerLevel: string | null;
    combatAbility: string | null;
    specialSkills: string | null;
    // 新增：当前状态
    currentStatus: CharacterStatus;
    statusNote: string | null;
    // 角色关系
    outgoingRelations: Array<{
      id: string;
      targetId: string;
      target: { id: string; name: string };
      relationType: RelationType;
      intimacy: number;
      description: string | null;
      startDate: string | null;
      endDate: string | null;
    }>;
    incomingRelations: Array<{
      id: string;
      characterId: string;
      character: { id: string; name: string };
      relationType: RelationType;
      intimacy: number;
      description: string | null;
    }>;
    experiences: Array<{
      id: string;
      chapterId: string | null;
      content: string;
      order: number;
    }>;
  }>;
  items: Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    rarity: string | null;
    effect: string | null;
    origin: string | null;
    description: string | null;
    ownerId: string | null;
    owner: { id: string; name: string } | null;
  }>;
  locations: Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    parentId: string | null;
    climate: string | null;
    culture: string | null;
    description: string | null;
  }>;
  factions: Array<{
    id: string;
    name: string;
    aliases: string | null;
    type: string | null;
    baseId: string | null;
    description: string | null;
  }>;
  glossaries: Array<{
    id: string;
    term: string;
    definition: string;
    category: string | null;
  }>;
  // 文风相关
  appliedStyleId: string | null;
  styles: Array<{
    id: string;
    name: string;
    portraitMarkdown: string | null;
    sourceType: string;
  }>;
  // 进度相关
  progress: {
    currentStage: string;
    currentGoal: string | null;
    currentConflict: string | null;
    nextMilestone: string | null;
  } | null;
  storyProgress: string | null;
  storyBackground: string | null;
  worldSetting: string | null;
  writingBible: {
    storyLengthProfile: string;
    targetTotalWordCount: number | null;
    genre: string | null;
    targetReaders: string | null;
    coreSellingPoint: string | null;
    readerPromise: string | null;
    appealModel: string | null;
    taboo: string | null;
    comparableTitles: string | null;
    notes: string | null;
  } | null;
  outline: {
    content: string;
  } | null;
  outlineNodes: Array<{
    id: string;
    title: string;
    content: string | null;
    kind: "stage" | "plot_unit" | "chapter_group";
    status: "planned" | "in_progress" | "completed" | "skipped";
    order: number;
    parentId: string | null;
    estimatedWordCount: number | null;
    actualWordCount: number | null;
  }>;
  references: Array<{
    id: string;
    title: string;
    type: string;
    content: string;
    sourceUrl: string | null;
  }>;
};

const TAB_ITEMS: Array<{ key: SidebarTabKey; label: string }> = [
  { key: "chapters", label: "章节" },
  { key: "lore", label: "设定" },
  { key: "style", label: "文风" },
  { key: "reference", label: "资料" },
];

function toWritingBibleForm(writingBible: SidebarTabsProps["writingBible"]) {
  return {
    storyLengthProfile: normalizeStoryLengthProfile(writingBible?.storyLengthProfile),
    targetTotalWordCount: writingBible?.targetTotalWordCount ? String(writingBible.targetTotalWordCount) : "",
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

export function SidebarTabs({
  novelId,
  activeChapterId,
  chapters,
  characters,
  items,
  locations,
  factions,
  glossaries,
  appliedStyleId,
  styles,
  progress,
  storyProgress,
  storyBackground,
  worldSetting,
  writingBible,
  outline,
  outlineNodes,
  references,
}: SidebarTabsProps) {
  const [activeTab, setActiveTab] = useState<SidebarTabKey>("chapters");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  // 弹窗状态：进度、故事进展、故事背景、世界设定、大纲
  const [modalKey, setModalKey] = useState<"progress" | "storyProgress" | "storyBackground" | "worldSetting" | "writingBible" | "outline" | null>(null);

  // 故事进展编辑状态
  const [storyProgressDraft, setStoryProgressDraft] = useState<string | null>(null);

  // 故事背景编辑状态
  const [storyBackgroundDraft, setStoryBackgroundDraft] = useState<string | null>(null);

  // 世界设定编辑状态
  const [worldSettingDraft, setWorldSettingDraft] = useState<string | null>(null);
  const [writingBibleDraft, setWritingBibleDraft] = useState<ReturnType<typeof toWritingBibleForm> | null>(null);

  const storyProgressContent = storyProgressDraft ?? storyProgress ?? "";
  const storyBackgroundContent = storyBackgroundDraft ?? storyBackground ?? "";
  const worldSettingContent = worldSettingDraft ?? worldSetting ?? "";
  const writingBibleForm = writingBibleDraft ?? toWritingBibleForm(writingBible);

  const openModal = (key: NonNullable<typeof modalKey>) => {
    if (key === "storyProgress") setStoryProgressDraft(null);
    if (key === "storyBackground") setStoryBackgroundDraft(null);
    if (key === "worldSetting") setWorldSettingDraft(null);
    if (key === "writingBible") setWritingBibleDraft(null);
    setModalKey(key);
  };

  const handleSaveStoryProgress = () => {
    startTransition(async () => {
      requireApiData(await browserApi.PUT("/api/v1/novels/{novel_id}/story-progress", {
        params: { path: { novel_id: novelId } },
        body: { content: storyProgressContent },
      }));
      setStoryProgressDraft(null);
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
          {TAB_ITEMS.map((tab) => (
            <button
              key={tab.key}
              className={`tab-button ${activeTab === tab.key ? "active" : ""}`}
              type="button"
              onClick={() => setActiveTab(tab.key)}
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
          />
        ) : null}

        {activeTab === "lore" ? (
          <LorePanel
            novelId={novelId}
            characters={characters}
            items={items}
            locations={locations}
            factions={factions}
            glossaries={glossaries}
          />
        ) : null}

        {activeTab === "style" ? (
          <StylePanel
            novelId={novelId}
            appliedStyleId={appliedStyleId}
            styles={styles}
          />
        ) : null}

        {activeTab === "reference" ? (
          <ReferencePanel novelId={novelId} references={references} />
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
        <ProgressPanel novelId={novelId} progress={progress} />
      </Modal>

      <Modal title="故事进展" description="记录故事整体进展" open={modalKey === "storyProgress"} onClose={() => setModalKey(null)}>
        <div className="stack">
          <textarea
            className="textarea modal-textarea"
            value={storyProgressContent}
            onChange={(e) => setStoryProgressDraft(e.target.value)}
            placeholder="记录故事的整体进展、关键转折、伏笔等..."
          />
          <div className="row row-between">
            <span className="muted">{storyProgressContent.length} / 30000 字</span>
            <button className="button" type="button" onClick={handleSaveStoryProgress}>
              {pending ? "保存中..." : "保存"}
            </button>
          </div>
        </div>
      </Modal>

      <Modal title="故事背景" description="描述故事的基础背景" open={modalKey === "storyBackground"} onClose={() => setModalKey(null)}>
        <div className="stack">
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
        </div>
      </Modal>

      <Modal title="世界设定" description="描述世界的设定" open={modalKey === "worldSetting"} onClose={() => setModalKey(null)}>
        <div className="stack">
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
        </div>
      </Modal>

      <Modal title="作品圣经" description="记录商业定位、读者承诺和写作禁忌" open={modalKey === "writingBible"} onClose={() => setModalKey(null)}>
        <div className="stack">
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
        </div>
      </Modal>

      <Modal title="大纲" description="写下故事的主要脉络，智能写作时会参考这里" open={modalKey === "outline"} onClose={() => setModalKey(null)}>
        <OutlinePanel novelId={novelId} outline={outline} outlineNodes={outlineNodes} />
      </Modal>

    </div>
  );
}

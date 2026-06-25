"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  updateStoryProgressAction,
  updateStoryBackgroundAction,
  updateWorldSettingAction,
} from "@/app/actions";
import { type AgentId, getDefaultEnabledAgents } from "@/agents/client";
import { OutlinePanel } from "@/features/outline/outline-panel";
import { ProgressPanel } from "@/features/progress/progress-panel";
import { ReferencePanel } from "@/features/references/reference-panel";
import { StylePanel } from "@/features/styles/style-panel";
import { AgentSelector, getDefaultSelectedAgents } from "@/features/writing/agent-selector";
import { WritingConversation } from "@/features/writing/writing-conversation";

type InspectorTabKey = "style" | "progress" | "storyProgress" | "storyBackground" | "worldSetting" | "outline" | "reference" | "smartWriting";

type InspectorTabsProps = {
  novelId: string;
  appliedStyleId: string | null;
  styles: Array<{
    id: string;
    name: string;
    portraitMarkdown: string | null;
    sourceType: string;
  }>;
  progress: {
    currentStage: string;
    currentGoal: string | null;
    currentConflict: string | null;
    nextMilestone: string | null;
  } | null;
  storyProgress: string | null;
  storyBackground: string | null;
  worldSetting: string | null;
  outline: {
    content: string;
  } | null;
  outlineNodes?: Array<{
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
  // 智能写作相关
  currentChapterId?: string;
  defaultWordCount?: number;
};

const TAB_ITEMS: Array<{ key: InspectorTabKey; label: string }> = [
  { key: "style", label: "文风" },
  { key: "progress", label: "进度" },
  { key: "smartWriting", label: "智能写作" },
  { key: "storyProgress", label: "故事进展" },
  { key: "storyBackground", label: "故事背景" },
  { key: "worldSetting", label: "世界设定" },
  { key: "outline", label: "大纲" },
  { key: "reference", label: "资料" },
];

export function InspectorTabs({
  novelId,
  appliedStyleId,
  styles,
  progress,
  storyProgress,
  storyBackground,
  worldSetting,
  outline,
  outlineNodes = [],
  references,
  currentChapterId,
  defaultWordCount = 4000,
}: InspectorTabsProps) {
  const [activeTab, setActiveTab] = useState<InspectorTabKey>("style");
  const [pending, startTransition] = useTransition();
  const router = useRouter();

  // 故事进展编辑状态
  const [storyProgressContent, setStoryProgressContent] = useState(storyProgress ?? "");

  // 故事背景编辑状态
  const [storyBackgroundContent, setStoryBackgroundContent] = useState(storyBackground ?? "");

  // 世界设定编辑状态
  const [worldSettingContent, setWorldSettingContent] = useState(worldSetting ?? "");

  // 智能写作状态
  const [selectedAgents, setSelectedAgents] = useState<AgentId[]>(() => getDefaultSelectedAgents());
  const [targetWordCount, setTargetWordCount] = useState(defaultWordCount);

  const handleSaveStoryProgress = () => {
    startTransition(async () => {
      await updateStoryProgressAction({
        novelId,
        content: storyProgressContent,
      });
      router.refresh();
    });
  };

  const handleSaveStoryBackground = () => {
    startTransition(async () => {
      await updateStoryBackgroundAction({
        novelId,
        content: storyBackgroundContent,
      });
      router.refresh();
    });
  };

  const handleSaveWorldSetting = () => {
    startTransition(async () => {
      await updateWorldSettingAction({
        novelId,
        content: worldSettingContent,
      });
      router.refresh();
    });
  };

  return (
    <div className="panel">
      <div className="panel-header stack">
        <div>
          <h2 className="title-md">信息面板</h2>
          <p className="muted">右侧内容切换为 Tab，减少同时展开的干扰。</p>
        </div>
        <div className="tabs">
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
        {activeTab === "style" ? (
          <StylePanel
            novelId={novelId}
            appliedStyleId={appliedStyleId}
            styles={styles}
          />
        ) : null}
        {activeTab === "progress" ? (
          <ProgressPanel novelId={novelId} progress={progress} />
        ) : null}
        {activeTab === "storyProgress" ? (
          <div className="stack">
            <div>
              <h3 className="title-md">故事进展</h3>
              <p className="muted">记录故事整体进展，最多3万字</p>
            </div>
            <textarea
              className="textarea"
              value={storyProgressContent}
              onChange={(e) => setStoryProgressContent(e.target.value)}
              placeholder="记录故事的整体进展、关键转折、伏笔等..."
              rows={15}
            />
            <div className="row row-between">
              <span className="muted">{storyProgressContent.length} / 30000 字</span>
              <button className="button" type="button" onClick={handleSaveStoryProgress}>
                {pending ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        ) : null}
        {activeTab === "storyBackground" ? (
          <div className="stack">
            <div>
              <h3 className="title-md">故事背景</h3>
              <p className="muted">描述故事的基础背景</p>
            </div>
            <textarea
              className="textarea"
              value={storyBackgroundContent}
              onChange={(e) => setStoryBackgroundContent(e.target.value)}
              placeholder="描述故事的基础背景，如时代背景、起始事件、核心冲突等..."
              rows={15}
            />
            <div className="row row-end">
              <button className="button" type="button" onClick={handleSaveStoryBackground}>
                {pending ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        ) : null}
        {activeTab === "worldSetting" ? (
          <div className="stack">
            <div>
              <h3 className="title-md">世界设定</h3>
              <p className="muted">描述世界的设定</p>
            </div>
            <textarea
              className="textarea"
              value={worldSettingContent}
              onChange={(e) => setWorldSettingContent(e.target.value)}
              placeholder="描述世界的设定，如世界类型、力量体系、世界规则、历史概述等..."
              rows={15}
            />
            <div className="row row-end">
              <button className="button" type="button" onClick={handleSaveWorldSetting}>
                {pending ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        ) : null}
        {activeTab === "outline" ? (
          <OutlinePanel novelId={novelId} outline={outline} outlineNodes={outlineNodes} />
        ) : null}
        {activeTab === "reference" ? (
          <ReferencePanel novelId={novelId} references={references} />
        ) : null}
        {activeTab === "smartWriting" ? (
          <div className="stack">
            <div>
              <h3 className="title-md">智能写作</h3>
              <p className="muted">多 Agent 协作生成正文内容</p>
            </div>
            {!currentChapterId ? (
              <p className="muted">请先选择一个章节</p>
            ) : (
              <>
                {/* <AgentSelector
                  selectedAgents={selectedAgents}
                  onChange={setSelectedAgents}
                  targetWordCount={targetWordCount}
                  onWordCountChange={setTargetWordCount}
                /> */}
                <WritingConversation
                  novelId={novelId}
                  chapterId={currentChapterId}
                  selectedAgents={selectedAgents}
                  targetWordCount={targetWordCount}
                  onComplete={() => router.refresh()}
                />
              </>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}

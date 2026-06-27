/**
 * Context builder tests
 *
 * 验证 Agent 间调用 brief 和用户根请求会进入目标 Agent 的当前任务上下文。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildActiveTaskContext, buildConversationHistoryText, buildSummaryIndex } from "../context-builder";
import type { AgentMessage, WritingState } from "../state";

function createState(overrides: Partial<WritingState> = {}): WritingState {
  return {
    taskId: "task-1",
    userId: "user-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    targetWordCount: 2000,
    phase: "active",
    userMessage: "@编辑 先评审大纲，不行让剧情修改，改完你再审核，写入前让我确认",
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: "剧情",
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData: {
      novelId: "novel-1",
      chapterId: "chapter-1",
      novelName: "遗产猎人",
      chapterTitle: "第一章",
      chapterContent: "",
      outlineSummary: "",
      outlineNodes: [],
      plotProgress: { currentStage: "开篇" },
      storyBackground: "",
      worldSetting: "",
      writingBible: null,
      storyProgress: "",
      characters: [],
      items: [],
      locations: [],
      factions: [],
      glossaries: [],
      foreshadowings: [],
      references: [],
      styleProfile: "",
    },
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    controlEvents: undefined,
    activeArtifactId: null,
    artifactMode: "none",
    reviewerAgent: null,
    reviserAgent: null,
    pendingArtifactRevision: null,
    artifactIteration: 0,
    maxArtifactIterations: 5,
    ...overrides,
  };
}

describe("buildActiveTaskContext", () => {
  it("includes root user request and pending Agent call brief", () => {
    const state = createState({
      pendingAgentCall: {
        fromAgent: "编辑",
        toAgent: "剧情",
        reason: "前十章商业留存不足，需要重构节奏",
        specificQuestion: "请按编辑意见重构前十章大纲，完成后交回编辑复审。",
        contentToRewrite: "第一章到第十章大纲",
        timestamp: 123,
      },
    });

    const text = buildActiveTaskContext(state);

    assert.match(text, /当前任务上下文/);
    assert.match(text, /根用户请求/);
    assert.match(text, /改完你再审核/);
    assert.match(text, /本轮直接任务/);
    assert.match(text, /前十章商业留存不足/);
    assert.match(text, /交回编辑复审/);
    assert.match(text, /第一章到第十章大纲/);
  });

  it("returns an empty string when there is no useful task context", () => {
    const state = createState({ userMessage: "", pendingAgentCall: null });
    assert.equal(buildActiveTaskContext(state), "");
  });

  it("labels active artifact context as draft instead of official fact", () => {
    const state = createState({
      userMessage: "",
      pendingAgentCall: null,
      activeArtifactId: "artifact-1",
    });

    const text = buildActiveTaskContext(state);

    assert.match(text, /当前待审核草案/);
    assert.match(text, /artifact-1/);
    assert.match(text, /不是正式设定/);
    assert.match(text, /不得把它当成已落库事实/);
  });
});

describe("buildConversationHistoryText", () => {
  it("renders Agent call messages instead of dropping them", () => {
    const history: AgentMessage[] = [
      {
        id: "call-1",
        agentId: "编辑",
        agentName: "网文编辑",
        content: "剧情顾问：请重构前十章大纲。",
        timestamp: 1,
        isCallMessage: true,
        callTarget: "剧情",
      },
    ];

    const text = buildConversationHistoryText(history);

    assert.match(text, /网文编辑/);
    assert.match(text, /调用/);
    assert.match(text, /剧情/);
    assert.match(text, /请重构前十章大纲/);
  });
});

describe("buildSummaryIndex", () => {
  it("renders approved beat plan as writing constraints", () => {
    const state = createState({
      novelData: {
        ...createState().novelData,
        approvedBeatPlan: {
          id: "plan-1",
          chapterGoal: "让主角发现第一条主线线索",
          mainPlotConnection: "接入遗产案主线",
          chapterAcceptanceCriteria: "章末形成继续追查的悬念",
          totalEstimatedWords: 2200,
          sceneBeats: [
            {
              order: 1,
              goal: "发现线索",
              conflict: "对手封锁现场",
              characters: ["主角", "对手"],
              foreshadowingRefs: ["玉简残片"],
              estimatedWords: 1200,
              acceptanceCriteria: "主角主动承担风险",
            },
          ],
        },
      },
    });

    const text = buildSummaryIndex(state.novelData);

    assert.match(text, /已批准章节计划/);
    assert.match(text, /让主角发现第一条主线线索/);
    assert.match(text, /发现线索/);
    assert.match(text, /玉简残片/);
  });
});

/**
 * Context builder tests
 *
 * 验证 Agent 间调用 brief 和用户根请求会进入目标 Agent 的当前任务上下文。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildActiveTaskContext, buildConversationHistoryText, buildOperationSummaryIndex, buildSummaryIndex } from "../context-builder";
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

  it("omits the current artifact producer body in reviewer mode and preserves other Agent output", () => {
    const longDraft = "正文".repeat(1000);
    const otherOutput = "编辑意见".repeat(300);
    const history: AgentMessage[] = [
      {
        id: "user-1",
        agentId: "设定",
        agentName: "用户",
        content: "",
        userMessage: "请审核这份正文草案",
        timestamp: 1,
      },
      {
        id: "writer-1",
        agentId: "写作",
        agentName: "作家",
        content: longDraft,
        agentOutput: {
          agentId: "写作",
          agentName: "作家",
          content: longDraft,
          insights: [],
          proactiveSuggestions: [],
        },
        timestamp: 2,
      },
      {
        id: "editor-1",
        agentId: "编辑",
        agentName: "网文编辑",
        content: otherOutput,
        agentOutput: {
          agentId: "编辑",
          agentName: "网文编辑",
          content: otherOutput,
          insights: [],
          proactiveSuggestions: [],
        },
        timestamp: 3,
      },
      {
        id: "call-2",
        agentId: "写作",
        agentName: "作家",
        content: "请校验当前草案",
        isCallMessage: true,
        callTarget: "校验",
        timestamp: 4,
      },
    ];

    const text = buildConversationHistoryText(history, {
      mode: "reviewer",
      activeArtifactId: "artifact-1",
      artifactProducerAgentId: "写作",
    });

    assert.match(text, /请审核这份正文草案/);
    assert.match(text, /artifact-1/);
    assert.match(text, /get_active_review_artifact/);
    assert.doesNotMatch(text, new RegExp(longDraft.slice(0, 100)));
    assert.equal(text.includes(otherOutput), true);
    assert.doesNotMatch(text, /历史输出已截断/);
    assert.match(text, /请校验当前草案/);
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

describe("buildOperationSummaryIndex", () => {
  it("uses outline profile for plan_chapter without unrelated lore sections", () => {
    const state = createState({
      currentOperation: {
        kind: "plan_chapter",
        targetType: "chapter",
        userGoal: "规划第一章",
        primaryAgent: "剧情",
        reviewers: ["编辑"],
        outputKind: "beat_plan",
        requiresArtifact: true,
        requiresUserApproval: true,
        confidence: 0.9,
        reasoning: "测试",
      },
      novelData: {
        ...createState().novelData,
        characters: [{ id: "c1", name: "纪寻", aliases: "", identity: "遗产猎人" } as WritingState["novelData"]["characters"][number]],
        factions: [{ id: "f1", name: "玄天宗", description: "宗门" } as WritingState["novelData"]["factions"][number]],
        outlineNodes: [{ id: "o1", title: "开篇", kind: "stage", status: "planned", content: "主角接任务" } as WritingState["novelData"]["outlineNodes"][number]],
        foreshadowings: [{ id: "fs1", name: "玉简残片", status: "active", plantedContent: "残片出现" } as WritingState["novelData"]["foreshadowings"][number]],
      },
    });

    const text = buildOperationSummaryIndex(state);

    assert.match(text, /角色索引/);
    assert.match(text, /大纲索引/);
    assert.match(text, /伏笔索引/);
    assert.doesNotMatch(text, /势力索引/);
  });

  it("uses lore profile for create_lore without outline sections", () => {
    const state = createState({
      currentOperation: {
        kind: "create_lore",
        targetType: "lore",
        userGoal: "补充门派设定",
        primaryAgent: "设定",
        reviewers: ["校验"],
        outputKind: "lore_proposal",
        requiresArtifact: true,
        requiresUserApproval: true,
        confidence: 0.9,
        reasoning: "测试",
      },
      novelData: {
        ...createState().novelData,
        factions: [{ id: "f1", name: "玄天宗", description: "宗门" } as WritingState["novelData"]["factions"][number]],
        outlineNodes: [{ id: "o1", title: "开篇", kind: "stage", status: "planned" } as WritingState["novelData"]["outlineNodes"][number]],
      },
    });

    const text = buildOperationSummaryIndex(state);

    assert.match(text, /势力索引/);
    assert.doesNotMatch(text, /大纲索引/);
  });

  it("adds artifact read hint in reviewer mode", () => {
    const state = createState({
      activeArtifactId: "artifact-1",
      currentOperation: {
        kind: "create_outline",
        targetType: "outline",
        userGoal: "创建大纲",
        primaryAgent: "剧情",
        reviewers: ["编辑"],
        outputKind: "outline_proposal",
        requiresArtifact: true,
        requiresUserApproval: true,
        confidence: 0.9,
        reasoning: "测试",
      },
    });

    const text = buildOperationSummaryIndex(state);

    assert.match(text, /待审核草案提示/);
    assert.match(text, /get_active_review_artifact/);
  });
});

/**
 * Control event processor tests
 *
 * 验证 controlEvents 已从 LangGraph 定义文件中抽离，并能在注入依赖下独立处理。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { extractArtifactOutputContent, processControlEvents } from "../control-event-processor";
import type { AgentControlEvent, AgentMessage, AgentOutput, CoreAgentId, NovelData } from "../state";
import type { GraphState } from "../graph-definition";
import type { PutUpdateItemTextBlockEvent } from "@/shared/contracts/agent-control";

function createOutput(): AgentOutput {
  return {
    agentId: "设定",
    agentName: "设定顾问",
    content: "## 设定更新建议\n\n建议新增角色张三。",
  };
}

function createNovelData(overrides: Partial<NovelData> = {}): NovelData {
  return {
    novelId: "novel-1",
    chapterId: "chapter-1",
    novelName: "测试小说",
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
    ...overrides,
  };
}

function createGraphState(): GraphState {
  return {
    taskId: "task-1",
    userId: "user-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    targetWordCount: 4000,
    phase: "active",
    userMessage: "审核草案",
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: "编辑",
    currentOperation: null,
    operationMode: "operation_graph",
    operationStep: "review_artifact",
    operationStage: "审核草案",
    chapterDraftTarget: null,
    agentOutputs: {},
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData: createNovelData(),
    runtime: { streamCallbacks: {}, eventCallbacks: {} },
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    eventCallbacks: {},
    qualityCheckId: null,
    controlEvents: undefined,
    artifactReview: {
      status: "reviewing",
      activeArtifactId: "artifact-1",
      reviewerAgent: "编辑",
      reviserAgent: null,
      pendingRevision: null,
      iteration: 1,
      maxIterations: 5,
    },
    activeArtifactId: "artifact-1",
    artifactMode: "review_loop",
    reviewerAgent: "编辑",
    reviserAgent: null,
    pendingArtifactRevision: null,
    artifactIteration: 1,
    maxArtifactIterations: 5,
  };
}

describe("processControlEvents", () => {
  it("extractArtifactOutputContent strips prose around unmarked outline drafts", () => {
    const raw = [
      "好的，我是剧情顾问。编辑已经把商业评审和修订brief交过来了，我现在先读取当前大纲的完整内容，然后按照六条修订需求产出修订稿。",
      "",
      "让我先查看当前系统中实际存在的大纲节点详情，了解完整的原大纲内容。",
      "",
      "我现在已经了解情况了。系统中存有之前的大纲内容，但编辑的六条修订需求并没有完全落实到位。我现在按照编辑的brief，逐条落实，产出完整的修订稿。",
      "",
      "# 《遗产猎人》前十章大纲（修订稿）",
      "",
      "---",
      "",
      "## 第一章 遗孤与遗产",
      "",
      "**核心事件：** 纪寻处理一处小型洞天崩溃后的扫尾工作。",
      "",
      "---",
      "",
      "以上为《遗产猎人》前十章大纲修订稿。请编辑审核。",
    ].join("\n");

    assert.equal(
      extractArtifactOutputContent(raw),
      [
        "# 《遗产猎人》前十章大纲（修订稿）",
        "",
        "---",
        "",
        "## 第一章 遗孤与遗产",
        "",
        "**核心事件：** 纪寻处理一处小型洞天崩溃后的扫尾工作。",
      ].join("\n")
    );
  });

  it("propose_updates 创建待审核 Artifact，不直接请求保存", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    let createdUpdates: unknown = null;

    const event: AgentControlEvent = {
      type: "propose_updates",
      summary: "新增角色张三",
      artifactKey: "character-zhangsan",
      updates: {
        characters: [
          { action: "create", name: "张三", personality: "果断", identity: "侠客" },
        ],
      },
    };

    const result = await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: {
            novelId: "novel-1",
            chapterId: "chapter-1",
            novelName: "测试小说",
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
        },
        activeAgent: "设定",
        output: createOutput(),
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        interrupt: (payload) => {
          throw new Error(`propose_updates 不应直接 interrupt: ${JSON.stringify(payload)}`);
        },
        createOrUpdateAgentUpdatesArtifact: async (input) => {
          createdUpdates = input.updates;
          return {
            id: "artifact-1",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey ?? null,
            kind: "agent_updates",
            status: "draft",
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: null,
            revision: 1,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
      }
    );

    assert.deepEqual(createdUpdates, event.updates);    assert.equal(result.activeArtifactId, "artifact-1");
    assert.equal(emitted[0].type, "artifact_submitted");
    assert.equal(emitted[0].payload.artifactId, "artifact-1");
  });

  it("begin_artifact_output 用可见正文创建文本型 ReviewArtifact", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    let createdContent = "";

    const event: AgentControlEvent = {
      type: "begin_artifact_output",
      kind: "outline_draft",
      artifactKey: "outline-long-draft",
      summary: "前十章大纲修改草案",
      reviewerAgent: "编辑",
      submitForReview: true,
    };

    const result = await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: {
            novelId: "novel-1",
            chapterId: "chapter-1",
            novelName: "测试小说",
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
        },
        activeAgent: "剧情",
        output: {
          agentId: "剧情",
          agentName: "剧情顾问",
          content: "第一章 遗孤与遗产\n\n主角发现遗产线索，并在章末遇到第一次反转。",
        },
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        createOrUpdateTextArtifact: async (input) => {
          createdContent = input.content;
          return {
            id: "artifact-text-1",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey ?? null,
            kind: input.kind,
            status: "under_review",
            title: null,
            summary: input.summary,
            payload: { kind: input.kind, content: input.content },
            diff: null,
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: 1,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
        now: () => 1357,
      }
    );

    assert.equal(createdContent, "第一章 遗孤与遗产\n\n主角发现遗产线索，并在章末遇到第一次反转。");
    assert.equal(result.activeArtifactId, "artifact-text-1");
    assert.ok(emitted.some((entry) => entry.type === "artifact_submitted"));
  });

  it("show_review_artifact emits a validated display event", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const event: AgentControlEvent = {
      type: "show_review_artifact",
      artifactId: "artifact-1",
      reason: "展示给用户确认",
    };

    await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: createNovelData(),
        },
        activeAgent: "设定",
        output: createOutput(),
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        findOpenReviewArtifact: async () => ({
          id: "artifact-1",
          novelId: "novel-1",
          chapterId: "chapter-1",
          taskId: "task-1",
          workflowRunId: null,
          artifactKey: "lore-draft",
          kind: "agent_updates",
          status: "awaiting_user",
          title: null,
          summary: "设定草案",
          payload: { kind: "agent_updates", updates: { characters: [] } },
          diff: [],
          createdByAgent: "设定",
          updatedByAgent: "设定",
          reviewerAgent: null,
          revision: 1,
          evaluations: [],
          createdAt: new Date(0).toISOString(),
          updatedAt: new Date(0).toISOString(),
        }),
      }
    );

    assert.equal(emitted[0].type, "review_artifact_requested");
    assert.equal(emitted[0].payload.artifactId, "artifact-1");
    assert.equal((emitted[0].payload.artifact as { status: string }).status, "awaiting_user");
  });

  it("show_review_artifact can target a draft created earlier in the same turn by artifactKey", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    let createdArtifact: Record<string, unknown> | null = null;
    const artifactKey = "character-zhangsan";
    const events: AgentControlEvent[] = [
      {
        type: "propose_updates",
        summary: "新增角色张三",
        artifactKey,
        updates: {
          characters: [
            { action: "create", name: "张三", personality: "果断", identity: "侠客" },
          ],
        },
      },
      {
        type: "show_review_artifact",
        artifactKey,
        reason: "请展示刚生成的设定草案。",
      },
    ];

    await processControlEvents(
      {
        events,
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: createNovelData(),
        },
        activeAgent: "设定",
        output: createOutput(),
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        createOrUpdateAgentUpdatesArtifact: async (input) => {
          createdArtifact = {
            id: "artifact-1",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey ?? null,
            kind: "agent_updates",
            status: "draft",
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: null,
            revision: 1,
            evaluations: [],
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
          return createdArtifact as any;
        },
        findOpenReviewArtifact: async (input) => {
          assert.equal(input.artifactKey, artifactKey);
          return createdArtifact as any;
        },
      }
    );

    assert.deepEqual(emitted.map((entry) => entry.type), ["artifact_submitted", "review_artifact_requested"]);
    assert.equal(emitted[1].payload.artifactId, "artifact-1");
    assert.equal((emitted[1].payload.artifact as { artifactKey: string }).artifactKey, artifactKey);
  });

  it("begin_artifact_output only saves text inside explicit artifact markers", async () => {
    let createdContent = "";

    const event: AgentControlEvent = {
      type: "begin_artifact_output",
      kind: "outline_draft",
      artifactKey: "outline-long-draft",
      summary: "前十章大纲修改草案",
      reviewerAgent: "编辑",
      submitForReview: true,
    };

    await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: {
            novelId: "novel-1",
            chapterId: "chapter-1",
            novelName: "测试小说",
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
        },
        activeAgent: "剧情",
        output: {
          agentId: "剧情",
          agentName: "剧情顾问",
          content: [
            "我会先提交一版大纲草案。",
            "",
            "ARTIFACT_OUTPUT_START",
            "第一章 遗孤与遗产",
            "",
            "主角发现遗产线索，并在章末遇到第一次反转。",
            "ARTIFACT_OUTPUT_END",
            "",
            "以上草稿已提交待审核，请编辑审阅。",
          ].join("\n"),
        },
        updatedHistory: [],
      },
      {
        emitEvent: () => undefined,
        createOrUpdateTextArtifact: async (input) => {
          createdContent = input.content;
          return {
            id: "artifact-text-1",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey ?? null,
            kind: input.kind,
            status: "under_review",
            title: null,
            summary: input.summary,
            payload: { kind: input.kind, content: input.content },
            diff: null,
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: 1,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
      }
    );

    assert.equal(
      createdContent,
      "第一章 遗孤与遗产\n\n主角发现遗产线索，并在章末遇到第一次反转。"
    );
  });


  it("submit_evaluation pass marks artifact awaiting user approval", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const event = {
      type: "submit_evaluation",
      artifactId: "artifact-1",
      artifactKey: "outline-revision-1",
      verdict: "pass",
      summary: "编辑复审通过，等待用户确认写入。",
    } as AgentControlEvent;

    const result = await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
        },
        graphState: createGraphState(),
        activeAgent: "编辑",
        output: {
          agentId: "编辑",
          agentName: "网文编辑",
          content: "## 复审通过\n\n可以提交给用户确认。",
        },
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        submitArtifactEvaluation: async (input) => ({
          id: input.artifactId,
          novelId: "novel-1",
          chapterId: "chapter-1",
          taskId: "task-1",
          workflowRunId: null,
          artifactKey: "outline-revision-1",
          kind: "agent_updates",
          status: "awaiting_user",
          title: null,
          summary: input.summary,
          payload: { kind: "agent_updates", updates: { outlineAdjustments: [] } },
          diff: [],
          createdByAgent: "剧情",
          updatedByAgent: "剧情",
          reviewerAgent: input.evaluatorAgent,
          revision: 1,
          evaluations: [],
          createdAt: new Date(0).toISOString(),
          updatedAt: new Date(0).toISOString(),
        }),
        markTaskAwaitingUserReview: async () => undefined,
        interrupt: (payload) => {
          assert.equal(payload.type, "user_input_required");
          assert.equal(payload.artifactId, "artifact-1");
          return { confirmed: true };
        },
      }
    );

    assert.equal(result.activeArtifactId, "artifact-1");    assert.ok(emitted.some((entry) => entry.type === "workflow_evaluation_submitted"));
    assert.ok(emitted.some((entry) => entry.type === "artifact_awaiting_user_approval"));
  });

  it("submit_evaluation pass emits user approval event before interrupt can stop execution", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const event = {
      type: "submit_evaluation",
      artifactId: "artifact-1",
      artifactKey: "outline-revision-1",
      verdict: "pass",
      summary: "editor review passed; wait for user approval",
    } as AgentControlEvent;

    await assert.rejects(
      () => processControlEvents(
        {
          events: [event],
          state: {
            taskId: "task-1",
            chapterId: "chapter-1",
            qualityCheckId: null,
          },
          graphState: createGraphState(),
          activeAgent: "编辑",
          output: {
            agentId: "编辑",
            agentName: "Editor",
            content: "Review passed. Please ask the user to approve the artifact.",
          },
          updatedHistory: [],
        },
        {
          emitEvent: (type, payload) => emitted.push({ type, payload }),
          submitArtifactEvaluation: async (input) => ({
            id: input.artifactId,
            novelId: "novel-1",
            chapterId: "chapter-1",
            taskId: "task-1",
            workflowRunId: null,
            artifactKey: "outline-revision-1",
            kind: "agent_updates",
            status: "awaiting_user",
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: { outlineAdjustments: [] } },
            diff: [],
            createdByAgent: "剧情",
            updatedByAgent: "剧情",
            reviewerAgent: input.evaluatorAgent,
            revision: 1,
            evaluations: [],
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          }),
          markTaskAwaitingUserReview: async () => undefined,
          interrupt: () => {
            throw new Error("interrupt stopped graph execution");
          },
        }
      ),
      /interrupt stopped graph execution/
    );

    assert.ok(emitted.some((entry) => entry.type === "workflow_evaluation_submitted"));
    assert.ok(emitted.some((entry) => entry.type === "artifact_awaiting_user_approval"));
  });

  it("submit_evaluation pass marks the current task as awaiting user review", async () => {
    const pendingActions: Array<{ taskId: string; artifactId: string }> = [];
    const event = {
      type: "submit_evaluation",
      artifactId: "artifact-1",
      artifactKey: "outline-revision-1",
      verdict: "pass",
      summary: "editor review passed; wait for user approval",
    } as AgentControlEvent;

    await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
        },
        graphState: createGraphState(),
        activeAgent: "编辑",
        output: {
          agentId: "编辑",
          agentName: "Editor",
          content: "Review passed. Please ask the user to approve the artifact.",
        },
        updatedHistory: [],
      },
      {
        emitEvent: () => undefined,
        submitArtifactEvaluation: async (input) => ({
          id: input.artifactId,
          novelId: "novel-1",
          chapterId: "chapter-1",
          taskId: "task-1",
          workflowRunId: null,
          artifactKey: "outline-revision-1",
          kind: "agent_updates",
          status: "awaiting_user",
          title: null,
          summary: input.summary,
          payload: { kind: "agent_updates", updates: { outlineAdjustments: [] } },
          diff: [],
          createdByAgent: "剧情",
          updatedByAgent: "剧情",
          reviewerAgent: input.evaluatorAgent,
          revision: 1,
          evaluations: [],
          createdAt: new Date(0).toISOString(),
          updatedAt: new Date(0).toISOString(),
        }),
        markTaskAwaitingUserReview: async (input) => {
          pendingActions.push(input);
        },
        interrupt: () => ({ confirmed: false }),
      }
    );

    assert.deepEqual(
      pendingActions.map(({ taskId, artifactId }) => ({ taskId, artifactId })),
      [{ taskId: "task-1", artifactId: "artifact-1" }]
    );
  });
});

describe("ReviewArtifact lifecycle routing", () => {
  it("update builder merges text and batched outline changes before reviewer routing", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const persisted: Array<{ summary: string; status: string; updates: unknown }> = [];

    const events: AgentControlEvent[] = [
      {
        type: "start_update_builder",
        summary: "批量重构大纲",
        artifactKey: "outline-builder-1",
        reviewerAgent: "编辑",
        submitForReview: true,
      },
      {
        type: "put_update_text_block",
        artifactKey: "outline-builder-1",
        section: "outlineContent",
      },
      {
        type: "append_update_batch",
        artifactKey: "outline-builder-1",
        updates: {
          outlineAdjustments: [
            { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage" },
          ],
        },
      },
      {
        type: "append_update_batch",
        artifactKey: "outline-builder-1",
        updates: {
          outlineAdjustments: [
            { action: "create", clientKey: "unit-1", parentKey: "stage-1", title: "遗产线索", kind: "plot_unit" },
            { action: "create", clientKey: "group-1", parentKey: "unit-1", title: "前三章", kind: "chapter_group" },
          ],
        },
      },
      {
        type: "put_update_item_text_blocks",
        artifactKey: "outline-builder-1",
        blocks: [
          {
            section: "outlineAdjustments",
            field: "content",
            targetKey: "unit-1",
            summary: "剧情单元长梗概",
          },
          {
            section: "outlineAdjustments",
            field: "content",
            targetKey: "group-1",
            summary: "前三章长梗概",
          },
        ],
      },
      {
        type: "finish_update_builder",
        artifactKey: "outline-builder-1",
        summary: "批量大纲草案构建完成",
        reviewerAgent: "编辑",
        submitForReview: true,
      },
    ];

    const result = await processControlEvents(
      {
        events,
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
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
        },
        activeAgent: "剧情",
        output: {
          agentId: "剧情",
          agentName: "剧情顾问",
          content: [
            "已分批提交大纲草案。",
            "ARTIFACT_OUTPUT_START",
            "全书总纲：纪寻从遗产任务中追查灵力衰退真相。",
            "ARTIFACT_OUTPUT_END",
            "ARTIFACT_OUTPUT_START",
            "剧情单元详细梗概：鹿溪镇暗流从职业困境、异常遗产、理事会遮掩三条线并进，把纪寻从底层任务推到主动追查。",
            "ARTIFACT_OUTPUT_END",
            "ARTIFACT_OUTPUT_START",
            "前三章详细梗概：第一章建立纪寻的遗产清理职业和低位处境，第二章让异常玉简牵出旧案线索，第三章用第一次小胜利和更大的追杀压力完成开篇钩子。",
            "ARTIFACT_OUTPUT_END",
          ].join("\n"),
        },
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        upsertUpdateBuilderArtifact: async (input) => {
          persisted.push({
            summary: input.summary,
            status: input.status,
            updates: input.updates,
          });
          return {
            id: "artifact-builder-1",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey,
            kind: "agent_updates",
            status: input.status,
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: persisted.length,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
        now: () => 3030,
      }
    );

    assert.equal(persisted.length, 1);
    assert.deepEqual(persisted[0].updates, {
      outlineContent: "全书总纲：纪寻从遗产任务中追查灵力衰退真相。",
      outlineAdjustments: [
        { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage" },
        {
          action: "create",
          clientKey: "unit-1",
          parentKey: "stage-1",
          title: "遗产线索",
          kind: "plot_unit",
          content: "剧情单元详细梗概：鹿溪镇暗流从职业困境、异常遗产、理事会遮掩三条线并进，把纪寻从底层任务推到主动追查。",
        },
        {
          action: "create",
          clientKey: "group-1",
          parentKey: "unit-1",
          title: "前三章",
          kind: "chapter_group",
          content: "前三章详细梗概：第一章建立纪寻的遗产清理职业和低位处境，第二章让异常玉简牵出旧案线索，第三章用第一次小胜利和更大的追杀压力完成开篇钩子。",
        },
      ],
    });
    assert.equal(persisted[0].status, "under_review");    assert.equal(result.activeArtifactId, "artifact-builder-1");
    assert.ok(emitted.some((entry) => entry.type === "artifact_submitted"));
  });

  it("update builder expands append_outline_tree before reviewer routing", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const persisted: Array<{ summary: string; status: string; updates: unknown }> = [];

    const events: AgentControlEvent[] = [
      {
        type: "start_update_builder",
        summary: "重构嵌套大纲树",
        artifactKey: "outline-tree-builder-1",
        reviewerAgent: "编辑",
        submitForReview: true,
      },
      {
        type: "put_update_text_block",
        artifactKey: "outline-tree-builder-1",
        section: "outlineContent",
      },
      {
        type: "append_outline_tree",
        artifactKey: "outline-tree-builder-1",
        summary: "第一阶段嵌套树",
        stages: [
          {
            title: "第一阶段 鹿溪镇暗流",
            plotUnits: [
              {
                title: "鹿溪镇的暗流",
                chapterGroups: [
                  {
                    title: "裂痕",
                  },
                ],
              },
            ],
          },
        ],
      },
      {
        type: "finish_update_builder",
        artifactKey: "outline-tree-builder-1",
        summary: "嵌套大纲树构建完成",
        reviewerAgent: "编辑",
        submitForReview: true,
      },
    ];

    const result = await processControlEvents(
      {
        events,
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: createNovelData({
            novelName: "遗产猎人",
            chapterTitle: "第一章",
          }),
        },
        activeAgent: "剧情",
        output: {
          agentId: "剧情",
          agentName: "剧情顾问",
          content: [
            "已提交嵌套大纲树草案。",
            "ARTIFACT_OUTPUT_START",
            "全书总纲：纪寻从遗产任务中追查灵力衰退真相。",
            "ARTIFACT_OUTPUT_END",
          ].join("\n"),
        },
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        upsertUpdateBuilderArtifact: async (input) => {
          persisted.push({
            summary: input.summary,
            status: input.status,
            updates: input.updates,
          });
          return {
            id: "artifact-tree-builder-1",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey,
            kind: "agent_updates",
            status: input.status,
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: persisted.length,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
        now: () => 4040,
      }
    );

    assert.equal(persisted.length, 1);
    assert.deepEqual(persisted[0].updates, {
      outlineContent: "全书总纲：纪寻从遗产任务中追查灵力衰退真相。",
      outlineAdjustments: [
        {
          action: "create",
          kind: "stage",
          title: "第一阶段 鹿溪镇暗流",
          clientKey: "outline-tree-builder-1-b0-s1",
        },
        {
          action: "create",
          kind: "plot_unit",
          title: "鹿溪镇的暗流",
          clientKey: "outline-tree-builder-1-b0-s1-u1",
          parentKey: "outline-tree-builder-1-b0-s1",
        },
        {
          action: "create",
          kind: "chapter_group",
          title: "裂痕",
          clientKey: "outline-tree-builder-1-b0-s1-u1-g1",
          parentKey: "outline-tree-builder-1-b0-s1-u1",
        },
      ],
    });
    assert.equal(persisted[0].status, "under_review");    assert.equal(result.activeArtifactId, "artifact-tree-builder-1");
    assert.ok(emitted.some((entry) => entry.type === "update_builder_outline_tree_appended"));
  });

  it("put_update_item_text_block emits ignored events for invalid item text writes", async () => {
    const cases: Array<{
      name: string;
      event: PutUpdateItemTextBlockEvent;
      content: string;
      reason: string;
    }> = [
      {
        name: "缺少 marker",
        event: {
          type: "put_update_item_text_block",
          artifactKey: "outline-builder-invalid-1",
          section: "outlineAdjustments",
          field: "content",
          targetKey: "group-1",
        },
        content: "这里没有 ARTIFACT_OUTPUT 标记块。",
        reason: "missing_marked_text",
      },
      {
        name: "找不到目标",
        event: {
          type: "put_update_item_text_block",
          artifactKey: "outline-builder-invalid-2",
          section: "outlineAdjustments",
          field: "content",
          targetKey: "missing-group",
        },
        content: ["ARTIFACT_OUTPUT_START", "长梗概", "ARTIFACT_OUTPUT_END"].join("\n"),
        reason: "target_item_not_found",
      },
      {
        name: "字段不允许",
        event: {
          type: "put_update_item_text_block",
          artifactKey: "outline-builder-invalid-3",
          section: "outlineAdjustments",
          field: "description",
          targetKey: "group-1",
        },
        content: ["ARTIFACT_OUTPUT_START", "长梗概", "ARTIFACT_OUTPUT_END"].join("\n"),
        reason: "field_not_allowed",
      },
    ];

    for (const item of cases) {
      const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];

      await processControlEvents(
        {
          events: [
            {
              type: "append_update_batch",
              artifactKey: item.event.artifactKey,
              updates: {
                outlineAdjustments: [
                  { action: "create", clientKey: "group-1", title: "前三章", kind: "chapter_group" },
                ],
              },
            },
            item.event,
          ],
          state: {
            taskId: "task-1",
            chapterId: "chapter-1",
            qualityCheckId: null,
            novelData: createNovelData({
              novelName: "遗产猎人",
              chapterTitle: "第一章",
            }),
          },
          activeAgent: "剧情",
          output: {
            agentId: "剧情",
            agentName: "剧情顾问",
            content: item.content,
          },
          updatedHistory: [],
        },
        {
          emitEvent: (type, payload) => emitted.push({ type, payload }),
          loadUpdateBuilderArtifactUpdates: async () => null,
          upsertUpdateBuilderArtifact: async (input) => ({
            id: `artifact-${item.event.artifactKey}`,
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey,
            kind: "agent_updates",
            status: input.status,
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: 1,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          }),
          now: () => 5050,
        }
      );

      assert.ok(
        emitted.some((entry) =>
          entry.type === "update_builder_text_ignored" &&
          entry.payload.reason === item.reason
        ),
        `${item.name} should emit ${item.reason}`
      );
    }
  });

  it("update builder filters sections by active agent permission", async () => {
    const persisted: Array<{ updates: unknown }> = [];

    await processControlEvents(
      {
        events: [
          {
            type: "append_update_batch",
            artifactKey: "lore-builder-1",
            summary: "批量设定",
            updates: {
              characters: [{ action: "create", name: "张三", identity: "侠客" }],
              outlineAdjustments: [
                { action: "update", nodeTitle: "第一章", content: "越界大纲修改" },
              ],
            },
          },
          {
            type: "finish_update_builder",
            artifactKey: "lore-builder-1",
            summary: "批量设定完成",
          },
        ],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: {
            novelId: "novel-1",
            chapterId: "chapter-1",
            novelName: "测试小说",
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
        },
        activeAgent: "设定",
        output: createOutput(),
        updatedHistory: [],
      },
      {
        emitEvent: () => undefined,
        loadUpdateBuilderArtifactUpdates: async () => null,
        upsertUpdateBuilderArtifact: async (input) => {
          persisted.push({ updates: input.updates });
          return {
            id: "artifact-builder-2",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey,
            kind: "agent_updates",
            status: input.status,
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: 1,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
      }
    );

    assert.deepEqual(persisted[0].updates, {
      characters: [{ action: "create", name: "张三", identity: "侠客" }],
    });
  });

  it("update builder filters persisted cross-turn draft updates before saving", async () => {
    const persisted: Array<{ updates: unknown }> = [];

    await processControlEvents(
      {
        events: [
          {
            type: "append_update_batch",
            artifactKey: "mixed-builder-1",
            updates: {
              characters: [{ action: "create", name: "张三", identity: "侠客" }],
            },
          },
          {
            type: "finish_update_builder",
            artifactKey: "mixed-builder-1",
            summary: "补充设定完成",
          },
        ],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
          novelData: createNovelData(),
        },
        activeAgent: "设定",
        output: createOutput(),
        updatedHistory: [],
      },
      {
        emitEvent: () => undefined,
        loadUpdateBuilderArtifactUpdates: async () => ({
          outlineAdjustments: [
            { action: "update", nodeTitle: "第一章", content: "旧草稿中的大纲修改" },
          ],
        }),
        upsertUpdateBuilderArtifact: async (input) => {
          persisted.push({ updates: input.updates });
          return {
            id: "artifact-builder-3",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey,
            kind: "agent_updates",
            status: input.status,
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: 1,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
      }
    );

    assert.deepEqual(persisted[0].updates, {
      characters: [{ action: "create", name: "张三", identity: "侠客" }],
    });
  });

  it("update builder keeps invalid cross-batch outline draft out of review", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const persisted: Array<{ status: string; updates: unknown }> = [];

    const result = await processControlEvents(
      {
        events: [
          {
            type: "append_update_batch",
            artifactKey: "outline-builder-invalid",
            updates: {
              outlineAdjustments: [
                { action: "create", clientKey: "unit-1", parentKey: "missing-stage", title: "孤立剧情单元", kind: "plot_unit" },
              ],
            },
          },
          {
            type: "finish_update_builder",
            artifactKey: "outline-builder-invalid",
            summary: "尝试完成非法大纲",
            reviewerAgent: "编辑",
            submitForReview: true,
          },
        ],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
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
        },
        activeAgent: "剧情",
        output: {
          agentId: "剧情",
          agentName: "剧情顾问",
          content: "尝试提交非法大纲。",
        },
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        loadUpdateBuilderArtifactUpdates: async () => null,
        upsertUpdateBuilderArtifact: async (input) => {
          persisted.push({ status: input.status, updates: input.updates });
          return {
            id: "artifact-builder-invalid",
            novelId: input.novelId,
            chapterId: input.chapterId ?? null,
            taskId: input.taskId ?? null,
            workflowRunId: null,
            artifactKey: input.artifactKey,
            kind: "agent_updates",
            status: input.status,
            title: null,
            summary: input.summary,
            payload: { kind: "agent_updates", updates: input.updates },
            diff: [],
            createdByAgent: input.agentId,
            updatedByAgent: input.agentId,
            reviewerAgent: input.reviewerAgent ?? null,
            revision: 1,
            createdAt: new Date(0).toISOString(),
            updatedAt: new Date(0).toISOString(),
          };
        },
      }
    );

    assert.equal(persisted[0].status, "draft");    assert.ok(emitted.some((entry) => entry.type === "update_builder_validation_failed"));
    assert.ok(!emitted.some((entry) => entry.type === "artifact_review_started"));
  });

  it("propose_updates with reviewerAgent routes the artifact to reviewer automatically", async () => {
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];

    const event: AgentControlEvent = {
      type: "propose_updates",
      summary: "调整前十章大纲节奏",
      artifactKey: "outline-commercial-revision",
      reviewerAgent: "编辑",
      updates: {
        outlineAdjustments: [
          { action: "update", nodeTitle: "第一章", content: "章末增加异常阵纹残片。" },
        ],
      },
    };

    const result = await processControlEvents(
      {
        events: [event],
        state: {
          taskId: "task-1",
          chapterId: "chapter-1",
          qualityCheckId: null,
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
        },
        activeAgent: "剧情",
        output: {
          agentId: "剧情",
          agentName: "剧情顾问",
          content: "## 修改完成\n\n已提交待审核草案。",
        },
        updatedHistory: [],
      },
      {
        emitEvent: (type, payload) => emitted.push({ type, payload }),
        createOrUpdateAgentUpdatesArtifact: async (input) => ({
          id: "artifact-review-1",
          novelId: input.novelId,
          chapterId: input.chapterId ?? null,
          taskId: input.taskId ?? null,
          workflowRunId: null,
          artifactKey: input.artifactKey ?? null,
          kind: "agent_updates",
          status: "under_review",
          title: null,
          summary: input.summary,
          payload: { kind: "agent_updates", updates: input.updates },
          diff: [],
          createdByAgent: input.agentId,
          updatedByAgent: input.agentId,
          reviewerAgent: input.reviewerAgent ?? null,
          revision: 1,
          createdAt: new Date(0).toISOString(),
          updatedAt: new Date(0).toISOString(),
        }),
        now: () => 2468,
      }
    );
    assert.equal(result.activeArtifactId, "artifact-review-1");
    assert.ok(emitted.some((entry) => entry.type === "artifact_submitted"));
  });
});

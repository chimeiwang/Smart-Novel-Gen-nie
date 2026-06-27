import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { AgentControlEvent, AgentOutput, WritingState } from "@/agents/graph/state";
import type { CreativeOperationKind } from "@/shared/contracts/creative-operation";
import type { AgentUpdates } from "@/shared/contracts/agent-updates";
import { executeCreativeOperation } from "../operation-executor";

function createState(kind: CreativeOperationKind): WritingState {
  return {
    taskId: "task-1",
    userId: "user-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    targetWordCount: 1200,
    phase: "active",
    userMessage: "测试",
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: "编辑",
    currentOperation: {
      kind,
      targetType: kind === "review_chapter" ? "chapter" : "lore",
      targetId: "chapter-1",
      userGoal: "测试",
      primaryAgent: kind === "review_chapter" ? "编辑" : "设定",
      reviewers: kind === "review_chapter" ? [] : ["校验"],
      outputKind: kind === "review_chapter" ? "review_report" : "lore_proposal",
      requiresArtifact: kind !== "review_chapter",
      requiresUserApproval: kind !== "review_chapter",
      confidence: 0.9,
      reasoning: "测试",
    },
    operationMode: "operation_graph",
    operationStage: null,
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData: { novelId: "novel-1", chapterId: "chapter-1" } as WritingState["novelData"],
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    eventCallbacks: undefined,
    qualityCheckId: null,
    controlEvents: undefined,
    activeArtifactId: null,
    artifactMode: "none",
    reviewerAgent: null,
    reviserAgent: null,
    pendingArtifactRevision: null,
    artifactIteration: 0,
    maxArtifactIterations: 5,
  };
}

describe("executeCreativeOperation control events", () => {
  it("emits artifact review events for agent-update operations with reviewerAgent", async () => {
    const output: AgentOutput = {
      agentId: "设定",
      agentName: "设定顾问",
      content: "设定草案已整理。",
      insights: [],
      proactiveSuggestions: [],
    };
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];

    const result = await executeCreativeOperation(createState("create_lore"), {
      runInternalAgent: async () => ({
        loreAdvisorOutput: output,
        activeAgent: "设定",
        controlEvents: [{
          type: "propose_updates",
          summary: "新增角色设定",
          updates: {
            characters: [{
              action: "create",
              name: "测试角色",
              fields: [{ field: "name", label: "名称", newValue: "测试角色" }],
            }],
          },
          reviewerAgent: "校验",
        }],
      }),
      emitEvent: (type, payload) => emitted.push({ type, payload }),
      createOrUpdateAgentUpdatesArtifact: async () => ({
        id: "artifact-1",
        novelId: "novel-1",
        chapterId: "chapter-1",
        taskId: "task-1",
        workflowRunId: null,
        artifactKey: "artifact-key",
        kind: "agent_updates",
        status: "under_review",
        title: null,
        summary: "新增角色设定",
        payload: {
          kind: "agent_updates",
          updates: {
            characters: [{
              action: "create",
              name: "测试角色",
              fields: [{ field: "name", label: "名称", newValue: "测试角色" }],
            }],
          },
        },
        diff: null,
        createdByAgent: "设定",
        updatedByAgent: "设定",
        reviewerAgent: "校验",
        revision: 1,
        evaluations: [],
        createdAt: new Date(0).toISOString(),
        updatedAt: new Date(0).toISOString(),
      }),
      now: () => 1000,
    });

    assert.equal(result.statePatch.activeArtifactId, "artifact-1");
    assert.ok(emitted.some((event) => event.type === "artifact_submitted"));
  });

  it("create_outline uses agent_updates artifacts for structured outline drafts", async () => {
    const state = createState("create_outline");
    state.currentOperation = {
      ...state.currentOperation!,
      kind: "create_outline",
      targetType: "outline",
      primaryAgent: "\u5267\u60c5",
      reviewers: ["\u7f16\u8f91"],
      outputKind: "outline_proposal",
      requiresArtifact: true,
      requiresUserApproval: true,
    };

    const output: AgentOutput = {
      agentId: "\u5267\u60c5",
      agentName: "剧情顾问",
      content: "结构化大纲草案已整理。",
      insights: [],
      proactiveSuggestions: [],
    };
    const capturedUpdates: AgentUpdates[] = [];

    const result = await executeCreativeOperation(state, {
      runInternalAgent: async () => ({
        plotAdvisorOutput: output,
        activeAgent: "\u5267\u60c5",
        controlEvents: [{
          type: "propose_updates",
          summary: "生成结构化大纲",
          updates: {
            outlineAdjustments: [
              {
                action: "create",
                clientKey: "stage-1",
                title: "第一卷 离乡",
                kind: "stage",
              },
              {
                action: "create",
                clientKey: "unit-1",
                parentKey: "stage-1",
                title: "假案引路",
                kind: "plot_unit",
              },
            ],
          },
          reviewerAgent: "\u7f16\u8f91",
        } satisfies AgentControlEvent],
      }),
      createOrUpdateAgentUpdatesArtifact: async (input) => {
        capturedUpdates.push(input.updates);
        return {
          id: "outline-artifact-1",
          novelId: input.novelId,
          chapterId: input.chapterId ?? null,
          taskId: input.taskId ?? null,
          workflowRunId: null,
          artifactKey: input.artifactKey ?? null,
          kind: "agent_updates",
          status: "under_review",
          title: null,
          summary: input.summary,
          payload: {
            kind: "agent_updates",
            updates: input.updates,
          },
          diff: null,
          createdByAgent: input.agentId,
          updatedByAgent: input.agentId,
          reviewerAgent: input.reviewerAgent ?? null,
          revision: 1,
          evaluations: [],
          createdAt: new Date(0).toISOString(),
          updatedAt: new Date(0).toISOString(),
        };
      },
    });

    assert.equal(capturedUpdates[0]?.outlineContent, undefined);
    assert.equal(capturedUpdates[0]?.outlineAdjustments?.length, 2);
    assert.equal(result.statePatch.activeArtifactId, "outline-artifact-1");
  });

  it("creates a structured beat plan artifact from submit_beat_plan", async () => {
    const state = createState("plan_chapter");
    state.currentOperation = {
      ...state.currentOperation!,
      kind: "plan_chapter",
      targetType: "chapter",
      primaryAgent: "剧情",
      reviewers: ["编辑"],
      outputKind: "beat_plan",
      requiresArtifact: true,
      requiresUserApproval: true,
    };

    const output: AgentOutput = {
      agentId: "剧情",
      agentName: "剧情顾问",
      content: "第一幕：主角发现线索。\n第二幕：反派制造阻碍。",
      insights: [],
      proactiveSuggestions: [],
    };
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];
    let textArtifactCalled = false;

    const result = await executeCreativeOperation(state, {
      runInternalAgent: async () => ({
        plotAdvisorOutput: output,
        activeAgent: "剧情",
        controlEvents: [{
          type: "submit_beat_plan",
          title: "第一章 Beat Plan",
          beatCount: 2,
          summary: "两幕推进主线。",
          chapterGoal: "让主角发现主线线索",
          sceneBeats: [
            {
              order: 1,
              goal: "主角发现线索",
              conflict: "线索被对手封锁",
              characters: ["主角"],
              estimatedWords: 1200,
              acceptanceCriteria: "主角主动追查",
            },
            {
              order: 2,
              goal: "对手制造阻碍",
              conflict: "主角必须付出代价保住线索",
              characters: ["主角", "对手"],
              estimatedWords: 1000,
              acceptanceCriteria: "章末形成追读悬念",
            },
          ],
        }],
      }),
      emitEvent: (type, payload) => emitted.push({ type, payload }),
      createOrUpdateBeatPlanArtifact: async (input) => ({
        id: "beat-plan-artifact-1",
        novelId: input.novelId,
        chapterId: input.chapterId ?? null,
        taskId: input.taskId ?? null,
        workflowRunId: null,
        artifactKey: input.artifactKey ?? null,
        kind: "beat_plan",
        status: "under_review",
        title: input.beatPlan.title,
        summary: input.summary,
        payload: {
          kind: "beat_plan",
          beatPlan: input.beatPlan,
        },
        diff: null,
        createdByAgent: input.agentId,
        updatedByAgent: input.agentId,
        reviewerAgent: input.reviewerAgent ?? null,
        revision: 1,
        evaluations: [],
        createdAt: new Date(0).toISOString(),
        updatedAt: new Date(0).toISOString(),
      }),
      createOrUpdateTextArtifact: async () => {
        textArtifactCalled = true;
        throw new Error("submit_beat_plan should not fall back to text artifacts");
      },
      now: () => 1000,
    });

    assert.equal(result.artifact?.id, undefined);
    assert.equal(result.statePatch.activeArtifactId, "beat-plan-artifact-1");
    assert.equal(textArtifactCalled, false);
    assert.ok(emitted.some((event) => event.type === "artifact_submitted"));
    assert.ok(emitted.some((event) => event.type === "beat_plan_submitted"));
  });

  it("does not interrupt inside executeOperation when operation reviewer passes an artifact", async () => {
    const state = createState("plan_chapter");
    state.currentOperation = {
      ...state.currentOperation!,
      kind: "plan_chapter",
      targetType: "chapter",
      primaryAgent: "\u5267\u60c5",
      reviewers: ["\u7f16\u8f91"],
      outputKind: "beat_plan",
      requiresArtifact: true,
      requiresUserApproval: true,
    };
    state.activeArtifactId = "artifact-1";
    state.pendingAgentCall = {
      fromAgent: "\u5267\u60c5",
      toAgent: "\u7f16\u8f91",
      reason: "review artifact",
      timestamp: 1000,
    };

    const output: AgentOutput = {
      agentId: "\u7f16\u8f91",
      agentName: "editor",
      content: "review passed",
      insights: [],
      proactiveSuggestions: [],
    };
    const emitted: Array<{ type: string; payload: Record<string, unknown> }> = [];

    const result = await executeCreativeOperation(state, {
      runInternalAgent: async () => ({
        editorOutput: output,
        activeAgent: "\u7f16\u8f91",
        controlEvents: [{
          type: "submit_evaluation",
          artifactId: "artifact-1",
          artifactKey: "beat-plan",
          verdict: "pass",
          summary: "ready for user approval",
        }],
      }),
      emitEvent: (type, payload) => emitted.push({ type, payload }),
      submitArtifactEvaluation: async (input) => ({
        id: input.artifactId,
        novelId: "novel-1",
        chapterId: "chapter-1",
        taskId: "task-1",
        workflowRunId: null,
        artifactKey: "beat-plan",
        kind: "beat_plan",
        status: "awaiting_user",
        title: null,
        summary: input.summary,
        payload: {
          kind: "beat_plan",
          beatPlan: {
            title: "第一章 Beat Plan",
            summary: "主角发现线索并进入案件。",
            chapterGoal: "让主角进入主线案件",
            sceneBeats: [
              {
                order: 1,
                goal: "发现线索",
                characters: ["主角"],
                acceptanceCriteria: "主角主动追查",
              },
            ],
          },
        },
        diff: null,
        createdByAgent: "\u5267\u60c5",
        updatedByAgent: "\u5267\u60c5",
        reviewerAgent: input.evaluatorAgent,
        revision: 1,
        evaluations: [],
        createdAt: new Date(0).toISOString(),
        updatedAt: new Date(0).toISOString(),
      }),
      markTaskAwaitingUserReview: async () => undefined,
      interrupt: () => {
        throw new Error("executeOperation should not interrupt directly");
      },
    });

    assert.equal(result.statePatch.activeArtifactId, "artifact-1");
    assert.equal(result.statePatch.reviserAgent, null);
    assert.equal(result.statePatch.reviewerAgent, "\u7f16\u8f91");
    assert.equal(result.statePatch.controlEvents, undefined);
    assert.ok(emitted.some((event) => event.type === "artifact_awaiting_user_approval"));
  });
});

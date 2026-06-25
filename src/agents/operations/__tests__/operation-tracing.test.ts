import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  createOperationTraceMetadata,
  hasNextReviewer,
  readEvaluationEvent,
  runOperationAgentWithLifecycle,
  selectCurrentReviewer,
} from "../operation-graph";
import type { GraphState } from "@/agents/graph/graph-definition";

function createState(): GraphState {
  return {
    taskId: "task-1",
    userId: "user-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    targetWordCount: 1200,
    phase: "active",
    userMessage: "继续写本章",
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: "写作",
    currentOperation: {
      kind: "write_chapter",
      targetType: "chapter",
      targetId: "chapter-1",
      userGoal: "继续写本章",
      primaryAgent: "写作",
      reviewers: ["编辑"],
      outputKind: "chapter_text",
      requiresArtifact: true,
      requiresUserApproval: true,
      confidence: 0.9,
      reasoning: "测试创作操作追踪元数据",
    },
    operationMode: "operation_graph",
    operationStage: "执行创作操作",
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData: { novelId: "novel-1", chapterId: "chapter-1" } as GraphState["novelData"],
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    eventCallbacks: undefined,
    nextAgent: null,
    callChainDepth: 0,
    qualityCheckId: null,
    controlEvents: undefined,
    activeArtifactId: "artifact-1",
    artifactMode: "review_loop",
    reviewerAgent: "编辑",
    reviserAgent: null,
    artifactIteration: 1,
    maxArtifactIterations: 5,
  };
}

describe("operation tracing", () => {
  it("builds stable LangSmith metadata for operation stages", () => {
    const metadata = createOperationTraceMetadata(createState(), "review_artifact");

    assert.equal(metadata.taskId, "task-1");
    assert.equal(metadata.userId, "user-1");
    assert.equal(metadata.novelId, "novel-1");
    assert.equal(metadata.chapterId, "chapter-1");
    assert.equal(metadata.operationKind, "write_chapter");
    assert.equal(metadata.operationLabel, "生成正文草案");
    assert.equal(metadata.operationStage, "review_artifact");
    assert.equal(metadata.primaryAgent, "写作");
    assert.equal(metadata.activeAgent, "写作");
    assert.equal(metadata.activeArtifactId, "artifact-1");
    assert.equal(metadata.artifactIteration, 1);
    assert.equal(metadata.service, "novel-writer");
  });
});

describe("operation agent lifecycle events", () => {
  it("emits agent_start and agent_done around operation graph internal agent execution", async () => {
    const events: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const state = {
      ...createState(),
      eventCallbacks: {
        "写作": (type: string, payload: Record<string, unknown>) => {
          events.push({ type, payload });
        },
      },
    };

    const result = await runOperationAgentWithLifecycle(
      state,
      "写作",
      undefined,
      async () => ({
        writerOutput: {
          agentId: "写作",
          content: "第一段正文。",
          insights: [],
          proactiveSuggestions: [],
        },
      })
    );

    assert.equal(result.writerOutput?.content, "第一段正文。");
    assert.deepEqual(events.map((event) => event.type), ["agent_start", "agent_done"]);
    assert.equal(events[0].payload.agentId, "写作");
    assert.equal(events[0].payload.agentName, "作家");
    assert.equal(events[1].payload.agentId, "写作");
    assert.equal(events[1].payload.content, "第一段正文。");
    assert.equal(events[1].payload.hasOutput, true);
    assert.equal(typeof events[1].payload.durationMs, "number");
  });
});

describe("operation review routing helpers", () => {
  it("selects reviewers in configured order instead of stopping after the first reviewer", () => {
    const state = createState();
    const reviewers = ["校验", "编辑"] as const;

    assert.equal(selectCurrentReviewer({ ...state, reviewerAgent: null }, [...reviewers]), "校验");
    assert.equal(hasNextReviewer({ ...state, reviewerAgent: "校验" }, [...reviewers]), true);
    assert.equal(selectCurrentReviewer({ ...state, reviewerAgent: "校验" }, [...reviewers]), "编辑");
    assert.equal(hasNextReviewer({ ...state, reviewerAgent: "编辑" }, [...reviewers]), false);
    assert.equal(selectCurrentReviewer({ ...state, reviewerAgent: "编辑" }, [...reviewers]), null);
  });

  it("prefers structured submit_evaluation control events over prose inference", () => {
    const evaluation = readEvaluationEvent({
      controlEvents: [{
        type: "submit_evaluation",
        verdict: "revise",
        summary: "节奏还需要压缩。",
        requiredChanges: "删除重复铺垫。",
        artifactKey: "artifact-key",
        artifactId: "artifact-1",
      }],
    });

    assert.deepEqual(evaluation, {
      verdict: "revise",
      summary: "节奏还需要压缩。",
      requiredChanges: "删除重复铺垫。",
    });
  });
});

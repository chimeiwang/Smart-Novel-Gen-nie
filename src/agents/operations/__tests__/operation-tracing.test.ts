import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  createOperationTraceMetadata,
  decideReviewOutcome,
  OPERATION_PATCH_ROUTES,
  OPERATION_REVIEW_ROUTES,
  readEvaluationEvent,
  requireStructuredEvaluation,
  routeAfterPatch,
  routeAfterReview,
  routeReviewWorkers,
  runOperationAgentWithLifecycle,
} from "../operation-graph";
import type { GraphState } from "@/agents/graph/graph-definition";
import type { ArtifactReviewResult } from "@/agents/graph/state";
import { createDefaultArtifactReviewState, patchArtifactReviewState } from "@/agents/graph/state";

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
    operationStep: "execute_operation",
    operationStage: "执行创作操作",
    chapterDraftTarget: null,
    agentOutputs: {},
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "",
    pendingUpdates: null,
    novelData: { novelId: "novel-1", chapterId: "chapter-1" } as GraphState["novelData"],
    runtime: { streamCallbacks: {}, eventCallbacks: undefined },
    pendingAgentCall: null,
    errorMessage: null,
    streamCallbacks: {},
    eventCallbacks: undefined,
    qualityCheckId: null,
    controlEvents: undefined,
    artifactReview: createDefaultArtifactReviewState({
      status: "reviewing",
      activeArtifactId: "artifact-1",
      reviewerAgent: "编辑",
      iteration: 1,
    }),
    activeArtifactId: "artifact-1",
    artifactMode: "review_loop",
    reviewerAgent: "编辑",
    reviewWorkerAgent: null,
    artifactReviewResults: [],
    reviserAgent: null,
    pendingArtifactRevision: null,
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
    assert.equal(metadata.service, "inkforge");
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
  it("dispatches configured reviewers through LangGraph Send", () => {
    const state = createState();
    const destinations = routeReviewWorkers({
      ...state,
      currentOperation: {
        ...state.currentOperation!,
        reviewers: ["校验", "编辑"],
      },
      ...patchArtifactReviewState(state, { reviewerAgent: null }),
    });

    assert.equal(Array.isArray(destinations), true);
    if (!Array.isArray(destinations)) throw new Error("expected Send destinations");
    assert.deepEqual(destinations.map((send) => send.node), ["reviewArtifactWorker", "reviewArtifactWorker"]);
    assert.deepEqual(destinations.map((send) => send.args.reviewWorkerAgent), ["校验", "编辑"]);
  });

  it("maps successful review merge to the user decision branch", () => {
    const destination = routeAfterReview({
      ...createState(),
      ...patchArtifactReviewState(createState(), { reviewerAgent: "编辑", reviserAgent: null, iteration: 1 }),
      currentOperation: {
        ...createState().currentOperation!,
        reviewers: ["校验", "编辑"],
      },
    });

    assert.equal(destination, "awaitUserDecision");
    assert.equal(destination in OPERATION_REVIEW_ROUTES, true);
  });

  it("routes revise+patch to the artifact patch node", () => {
    const destination = routeAfterReview({
      ...createState(),
      ...patchArtifactReviewState(createState(), {
        reviewerAgent: "校验",
        reviserAgent: null,
        pendingRevision: {
        summary: "只需修正时间线措辞。",
        revisionMode: "patch",
        patches: [{ kind: "text_replace", find: "前天", replace: "今天" }],
        },
      }),
      currentOperation: {
        ...createState().currentOperation!,
        reviewers: ["校验", "编辑"],
      },
    });

    assert.equal(destination, "applyArtifactPatch");
    assert.equal(destination in OPERATION_REVIEW_ROUTES, true);
  });

  it("routes patch success to the next reviewer", () => {
    const destination = routeAfterPatch({
      ...createState(),
      ...patchArtifactReviewState(createState(), { reviewerAgent: "校验", reviserAgent: null }),
      currentOperation: {
        ...createState().currentOperation!,
        reviewers: ["校验", "编辑"],
      },
    });

    assert.equal(destination, "reviewArtifact");
    assert.equal(destination in OPERATION_PATCH_ROUTES, true);
  });

  it("routes patch failure fallback to rewrite", () => {
    const destination = routeAfterPatch({
      ...createState(),
      ...patchArtifactReviewState(createState(), { reviewerAgent: "校验", reviserAgent: "写作", iteration: 1 }),
    });

    assert.equal(destination, "reviseArtifact");
    assert.equal(destination in OPERATION_PATCH_ROUTES, true);
  });

  it("does not let a pass result override another reviewer revision", () => {
    const base = {
      artifactId: "artifact-1",
      operationKind: "write_chapter",
      iteration: 1,
      output: null,
      structured: true,
    } satisfies Partial<ArtifactReviewResult>;

    const outcome = decideReviewOutcome([
      {
        ...base,
        reviewer: "校验",
        verdict: "pass",
        summary: "一致性通过。",
      },
      {
        ...base,
        reviewer: "编辑",
        verdict: "revise",
        summary: "章末钩子不足。",
        requiredChanges: "重写章末追读钩子。",
        revisionMode: "rewrite",
      },
    ] as ArtifactReviewResult[]);

    assert.equal(outcome.verdict, "revise");
    assert.equal(outcome.revisionMode, "rewrite");
    assert.match(outcome.requiredChanges ?? "", /章末追读钩子/);
  });

  it("prefers structured submit_evaluation control events over prose inference", () => {
    const evaluation = readEvaluationEvent({
      controlEvents: [{
        type: "submit_evaluation",
        verdict: "revise",
        summary: "节奏还需要压缩。",
        requiredChanges: "删除重复铺垫。",
        revisionMode: "patch",
        patches: [{ kind: "text_replace", find: "重复铺垫", replace: "关键线索" }],
        artifactKey: "artifact-key",
        artifactId: "artifact-1",
      }],
    });

    assert.deepEqual(evaluation, {
      verdict: "revise",
      summary: "节奏还需要压缩。",
      requiredChanges: "删除重复铺垫。",
      revisionMode: "patch",
      patches: [{ kind: "text_replace", find: "重复铺垫", replace: "关键线索" }],
    });
  });

  it("blocks review routing when reviewer omits submit_evaluation", () => {
    const evaluation = requireStructuredEvaluation(null, {
      validatorOutput: {
        agentId: "校验",
        agentName: "校验员",
        content: "校验报告：存在大纲偏差，建议返工。",
        insights: [],
        proactiveSuggestions: [],
      },
    }, "校验", createState());

    assert.equal(evaluation.verdict, "block");
    assert.match(evaluation.summary, /没有调用 submit_evaluation/);
    assert.match(evaluation.summary, /原始报告摘要/);
  });
});

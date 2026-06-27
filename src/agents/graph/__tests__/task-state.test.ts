import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { deserializeGraphStateSnapshot } from "../graph-state-snapshot";
import { buildAwaitingUserReviewTaskUpdate } from "../task-state";
import type { GraphState } from "../graph-definition";

function createState(): GraphState {
  return {
    taskId: "task-1",
    userId: "user-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    targetWordCount: 4000,
    phase: "active",
    userMessage: "写正文",
    pendingUserResponse: false,
    conversationHistory: [],
    activeAgent: "写作",
    currentOperation: {
      kind: "write_chapter",
      targetType: "chapter",
      primaryAgent: "写作",
      confidence: 0.9,
      userGoal: "写正文",
      outputKind: "chapter_text",
      requiresArtifact: true,
      requiresUserApproval: true,
      reasoning: "测试",
      reviewers: ["校验"],
    },
    operationMode: "operation_graph",
    operationStage: "审核草案",
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
    eventCallbacks: {},
    qualityCheckId: null,
    controlEvents: undefined,
    activeArtifactId: "artifact-1",
    artifactMode: "review_loop",
    reviewerAgent: "校验",
    reviserAgent: null,
    pendingArtifactRevision: null,
    artifactIteration: 1,
    maxArtifactIterations: 5,
  };
}

describe("task-state awaiting user review update", () => {
  it("stores a recoverable graph snapshot for the awaiting-review interrupt point", () => {
    const update = buildAwaitingUserReviewTaskUpdate({
      artifactId: "artifact-1",
      state: createState(),
      operationStage: "等待用户决策",
    });

    assert.equal(update.phase, "awaiting_user_review");
    assert.equal(update.generatedContent, "artifact-1");
    assert.equal(typeof update.conversationHistory, "string");
    assert.equal(typeof update.graphStateJson, "string");

    const snapshot = deserializeGraphStateSnapshot(update.graphStateJson);
    assert.ok(snapshot);
    assert.equal(snapshot.phase, "awaiting_user_review");
    assert.equal(snapshot.pendingUserResponse, true);
    assert.equal(snapshot.activeArtifactId, "artifact-1");
    assert.equal(snapshot.generatedContent, "artifact-1");
    assert.equal(snapshot.operationStage, "等待用户决策");
  });
});

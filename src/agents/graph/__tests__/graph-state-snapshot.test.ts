import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  deserializeGraphStateSnapshot,
  rehydrateGraphStateFromSnapshot,
  serializeGraphStateSnapshot,
} from "../graph-state-snapshot";
import type { GraphState } from "../graph-definition";

function createState(): GraphState {
  return {
    taskId: "task-1",
    userId: "user-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    targetWordCount: 4000,
    phase: "awaiting_user_review",
    userMessage: "继续写",
    pendingUserResponse: true,
    conversationHistory: [
      {
        id: "msg-1",
        agentId: "写作",
        agentName: "作家",
        content: "草案已生成",
        timestamp: 1,
      },
    ],
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
      reasoning: "测试恢复",
      reviewers: ["校验", "编辑"],
    },
    operationMode: "operation_graph",
    operationStage: "等待用户决策",
    chapterDraftTarget: null,
    loreAdvisorOutput: null,
    plotAdvisorOutput: null,
    writerOutput: null,
    validatorOutput: null,
    editorOutput: null,
    generatedContent: "artifact-1",
    pendingUpdates: null,
    novelData: { novelId: "novel-1", chapterId: "chapter-1" } as GraphState["novelData"],
    pendingAgentCall: {
      fromAgent: "编辑",
      toAgent: "写作",
      reason: "返工",
      timestamp: 1,
    },
    errorMessage: null,
    streamCallbacks: {
      写作: () => undefined,
    },
    eventCallbacks: {
      写作: () => undefined,
    },
    qualityCheckId: "check-1",
    controlEvents: undefined,
    activeArtifactId: "artifact-1",
    artifactMode: "review_loop",
    reviewerAgent: "编辑",
    reviserAgent: null,
    pendingArtifactRevision: null,
    artifactIteration: 1,
    maxArtifactIterations: 5,
  };
}

describe("graph state snapshots", () => {
  it("serializes recoverable GraphState without runtime callbacks or stale novelData", () => {
    const serialized = serializeGraphStateSnapshot(createState());
    const parsed = JSON.parse(serialized);

    assert.equal(parsed.taskId, "task-1");
    assert.equal(parsed.phase, "awaiting_user_review");
    assert.equal(parsed.activeArtifactId, "artifact-1");
    assert.equal(parsed.operationStage, "等待用户决策");
    assert.equal(parsed.streamCallbacks, undefined);
    assert.equal(parsed.eventCallbacks, undefined);
    assert.equal(parsed.novelData, undefined);
  });

  it("rehydrates snapshot with fresh novelData and runtime callbacks", () => {
    const snapshot = deserializeGraphStateSnapshot(serializeGraphStateSnapshot(createState()));
    assert.ok(snapshot);

    const rehydrated = rehydrateGraphStateFromSnapshot(snapshot, {
      userMessage: "审批通过",
      novelData: { novelId: "novel-1", chapterId: "chapter-1", novelName: "新上下文" } as GraphState["novelData"],
      streamCallbacks: { 写作: () => undefined },
      eventCallbacks: { 写作: () => undefined },
    });

    assert.equal(rehydrated.userMessage, "审批通过");
    assert.equal(rehydrated.currentOperation?.kind, "write_chapter");
    assert.equal(rehydrated.operationStage, "等待用户决策");
    assert.equal(rehydrated.novelData.novelName, "新上下文");
    assert.equal(typeof rehydrated.streamCallbacks["写作"], "function");
    assert.equal(typeof rehydrated.eventCallbacks?.["写作"], "function");
  });

  it("returns null for malformed snapshots instead of throwing", () => {
    assert.equal(deserializeGraphStateSnapshot("{bad json"), null);
    assert.equal(deserializeGraphStateSnapshot(JSON.stringify({ taskId: 123 })), null);
  });
});

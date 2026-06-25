import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { resolveLoadedSessionRecoveryState } from "../session-task-state";

describe("session recovery state", () => {
  it("restores operation status and awaiting artifact state from a loaded session task", () => {
    assert.deepEqual(
      resolveLoadedSessionRecoveryState({
        id: "task-1",
        phase: "awaiting_user_review",
        updatedAt: "2026-06-19T00:00:00.000Z",
        hasAwaitingReviewArtifact: true,
        currentOperation: {
          kind: "write_chapter",
          targetType: "chapter",
          primaryAgent: "写作",
          confidence: 0.8,
          userGoal: "写正文",
          outputKind: "chapter_text",
          requiresArtifact: true,
          requiresUserApproval: true,
          reasoning: "测试恢复",
          reviewers: ["校验", "编辑"],
        },
        operationStage: "等待用户决策",
        activeArtifactId: "artifact-1",
      }),
      {
        taskId: "task-1",
        phase: "recording",
        shouldRefreshAwaitingReviewArtifact: true,
        currentOperation: {
          kind: "write_chapter",
          targetType: "chapter",
          primaryAgent: "写作",
          confidence: 0.8,
          userGoal: "写正文",
          outputKind: "chapter_text",
          requiresArtifact: true,
          requiresUserApproval: true,
          reasoning: "测试恢复",
          reviewers: ["校验", "编辑"],
        },
        operationStage: "等待用户决策",
        activeArtifactId: "artifact-1",
      }
    );
  });

  it("clears operation status when no task is available", () => {
    assert.deepEqual(resolveLoadedSessionRecoveryState(null), {
      taskId: null,
      phase: "idle",
      shouldRefreshAwaitingReviewArtifact: false,
      currentOperation: null,
      operationStage: null,
      activeArtifactId: null,
    });
  });
});

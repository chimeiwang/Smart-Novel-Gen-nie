import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { resolveLoadedSessionTaskState } from "../session-task-state";

describe("session task state", () => {
  it("restores review mode for awaiting user review tasks", () => {
    assert.deepEqual(
      resolveLoadedSessionTaskState({
        id: "task-1",
        phase: "awaiting_user_review",
        updatedAt: "2026-06-19T00:00:00.000Z",
        hasAwaitingReviewArtifact: true,
        currentOperation: null,
        operationStage: null,
        activeArtifactId: "artifact-1",
      }),
      {
        taskId: "task-1",
        phase: "recording",
        shouldRefreshAwaitingReviewArtifact: true,
      }
    );
  });

  it("restores discussing mode for active tasks", () => {
    assert.deepEqual(
      resolveLoadedSessionTaskState({
        id: "task-2",
        phase: "active",
        updatedAt: "2026-06-19T00:00:00.000Z",
        hasAwaitingReviewArtifact: false,
        currentOperation: null,
        operationStage: null,
        activeArtifactId: null,
      }),
      {
        taskId: "task-2",
        phase: "discussing",
        shouldRefreshAwaitingReviewArtifact: false,
      }
    );
  });

  it("clears task state when no task is available", () => {
    assert.deepEqual(resolveLoadedSessionTaskState(null), {
      taskId: null,
      phase: "idle",
      shouldRefreshAwaitingReviewArtifact: false,
    });
  });

  it("does not expose completed tasks as resume handles", () => {
    assert.deepEqual(
      resolveLoadedSessionTaskState({
        id: "task-completed",
        phase: "completed",
        updatedAt: "2026-06-19T00:00:00.000Z",
        hasAwaitingReviewArtifact: false,
        currentOperation: null,
        operationStage: null,
        activeArtifactId: null,
      }),
      {
        taskId: null,
        phase: "idle",
        shouldRefreshAwaitingReviewArtifact: false,
      }
    );
  });
});

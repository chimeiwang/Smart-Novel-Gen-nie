import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { WritingTaskPhase } from "@prisma/client";

import {
  selectCurrentSessionTask,
  selectCurrentSessionTaskFromSession,
  selectLastSessionTask,
} from "../session-task";

function task(input: {
  id: string;
  phase: WritingTaskPhase;
  minutesAgo: number;
  generatedContent?: string | null;
}) {
  return {
    id: input.id,
    phase: input.phase,
    updatedAt: new Date(Date.UTC(2026, 5, 19, 10, input.minutesAgo, 0)),
    generatedContent: input.generatedContent ?? null,
  };
}

describe("selectCurrentSessionTask", () => {
  it("prefers awaiting review tasks so a selected session can restore its artifact", () => {
    const selected = selectCurrentSessionTask([
      task({ id: "completed-task", phase: "completed", minutesAgo: 1 }),
      task({
        id: "review-task",
        phase: "awaiting_user_review",
        minutesAgo: 0,
        generatedContent: "artifact-1",
      }),
      task({ id: "active-task", phase: "active", minutesAgo: 2 }),
    ]);

    assert.deepEqual(selected, {
      id: "review-task",
      phase: "awaiting_user_review",
      updatedAt: "2026-06-19T10:00:00.000Z",
      hasAwaitingReviewArtifact: true,
      currentOperation: null,
      operationStage: null,
      activeArtifactId: "artifact-1",
    });
  });

  it("selects active tasks when there is no pending review", () => {
    const selected = selectCurrentSessionTask([
      task({ id: "completed-task", phase: "completed", minutesAgo: 1 }),
      task({ id: "active-task", phase: "active", minutesAgo: 0 }),
    ]);

    assert.equal(selected?.id, "active-task");
    assert.equal(selected?.hasAwaitingReviewArtifact, false);
  });

  it("returns null when no task is available", () => {
    assert.equal(selectCurrentSessionTask([]), null);
  });

  it("does not treat completed tasks as resumable", () => {
    assert.equal(
      selectCurrentSessionTask([
        task({ id: "completed-task", phase: "completed", minutesAgo: 0 }),
      ]),
      null
    );
  });

  it("selects only from explicitly bound session tasks", () => {
    const selected = selectCurrentSessionTaskFromSession({
      tasks: [
        task({
          id: "bound-review",
          phase: "awaiting_user_review",
          minutesAgo: 0,
          generatedContent: "artifact-1",
        }),
      ],
    });

    assert.equal(selected?.id, "bound-review");
  });

  it("keeps the latest terminal task as read-only history", () => {
    const selected = selectLastSessionTask([
      task({ id: "completed-task", phase: "completed", minutesAgo: 0 }),
      task({ id: "older-error", phase: "error", minutesAgo: 1 }),
    ]);

    assert.equal(selected?.id, "completed-task");
  });
});

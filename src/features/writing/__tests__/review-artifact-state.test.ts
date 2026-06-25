import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyOptimisticReviewArtifactDecision,
  attachReviewArtifactToConversation,
  attachReviewArtifactToLastMessage,
  clearReviewArtifactFromMessages,
  resolveReviewArtifactActionTaskId,
  resolveTerminalStreamPhase,
  resolveReviewArtifactTaskId,
  resolveVisibleReviewArtifact,
  shouldRefreshAwaitingReviewArtifact,
} from "../review-artifact-state";

describe("review artifact state", () => {
  it("keeps an active review artifact visible even when no message could receive it", () => {
    const artifact = { id: "artifact-1", status: "awaiting_user" };

    assert.deepEqual(attachReviewArtifactToLastMessage([], artifact), []);
    assert.equal(resolveVisibleReviewArtifact(artifact, []), artifact);
  });

  it("creates a local placeholder message when restoring an artifact into an empty conversation", () => {
    const artifact = { id: "artifact-1", status: "awaiting_user" };

    assert.deepEqual(
      attachReviewArtifactToConversation([], artifact, () => ({
        id: "placeholder",
        reviewArtifact: null,
      })),
      [
        {
          id: "placeholder",
          reviewArtifact: artifact,
        },
      ]
    );
  });

  it("falls back to the last message review artifact when there is no active artifact", () => {
    const artifact = { id: "artifact-2", status: "awaiting_user" };
    const messages = attachReviewArtifactToLastMessage([{}], artifact);

    assert.equal(resolveVisibleReviewArtifact(null, messages), artifact);
  });

  it("refreshes awaiting artifacts after a stream ends when none is visible", () => {
    assert.equal(
      shouldRefreshAwaitingReviewArtifact({
        eventType: "done",
        hasTaskId: true,
        visibleArtifactStatus: null,
      }),
      true
    );
  });

  it("does not refresh awaiting artifacts without a current task id", () => {
    assert.equal(
      shouldRefreshAwaitingReviewArtifact({
        eventType: "done",
        hasTaskId: false,
        visibleArtifactStatus: null,
      }),
      false
    );
  });

  it("does not refresh when an awaiting artifact is already visible", () => {
    assert.equal(
      shouldRefreshAwaitingReviewArtifact({
        eventType: "done",
        hasTaskId: true,
        visibleArtifactStatus: "awaiting_user",
      }),
      false
    );
  });

  it("keeps the UI in review mode when a terminal stream event arrives for an awaiting artifact", () => {
    assert.equal(
      resolveTerminalStreamPhase({
        visibleArtifactStatus: "awaiting_user",
        completedPhase: "completed",
        awaitingReviewPhase: "recording",
      }),
      "recording"
    );
  });

  it("marks the UI completed when a terminal stream event has no awaiting artifact", () => {
    assert.equal(
      resolveTerminalStreamPhase({
        visibleArtifactStatus: null,
        completedPhase: "completed",
        awaitingReviewPhase: "recording",
      }),
      "completed"
    );
  });

  it("uses the artifact task id when no current task id is available", () => {
    assert.equal(
      resolveReviewArtifactTaskId(null, { taskId: "task-from-artifact" }),
      "task-from-artifact"
    );
  });

  it("keeps the current task id when it is already available", () => {
    assert.equal(
      resolveReviewArtifactTaskId("current-task", { taskId: "task-from-artifact" }),
      "current-task"
    );
  });

  it("uses the artifact task id for review actions", () => {
    assert.equal(
      resolveReviewArtifactActionTaskId("current-task", { taskId: "task-from-artifact" }),
      "task-from-artifact"
    );
  });

  it("can display an inspected artifact without attaching it to messages", () => {
    const artifact = { id: "artifact-1", status: "awaiting_user" };
    const messages = [{ id: "message-1", reviewArtifact: null }];

    assert.equal(resolveVisibleReviewArtifact(artifact, messages), artifact);
    assert.deepEqual(messages, [{ id: "message-1", reviewArtifact: null }]);
  });

  it("marks an approving artifact as applying optimistically", () => {
    assert.deepEqual(
      applyOptimisticReviewArtifactDecision(
        { id: "artifact-1", status: "awaiting_user" },
        { artifactId: "artifact-1", decision: "approve" }
      ),
      { id: "artifact-1", status: "applying", optimisticStatus: "applying" }
    );
  });

  it("ignores optimistic decisions for other artifacts", () => {
    const artifact = { id: "artifact-1", status: "awaiting_user" };
    assert.equal(
      applyOptimisticReviewArtifactDecision(
        artifact,
        { artifactId: "artifact-2", decision: "discard" }
      ),
      artifact
    );
  });

  it("clears applied or deleted artifact references from messages", () => {
    assert.deepEqual(
      clearReviewArtifactFromMessages(
        [
          { reviewArtifact: { id: "artifact-1" } },
          { reviewArtifact: { id: "artifact-2" } },
        ],
        "artifact-1"
      ),
      [
        { reviewArtifact: null },
        { reviewArtifact: { id: "artifact-2" } },
      ]
    );
  });
});

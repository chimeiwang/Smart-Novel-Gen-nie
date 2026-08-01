import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyOptimisticReviewArtifactDecision,
  attachReviewArtifactToConversation,
  attachReviewArtifactToLastMessage,
  clearReviewArtifactFromMessages,
  createReviewStateEpoch,
  isTerminalReviewArtifact,
  resolveReviewArtifactActionTaskId,
  resolveReviewArtifactTaskId,
  resolveVisibleReviewArtifact,
} from "../review-artifact-state";

type TestArtifact = {
  id: string;
  taskId?: string | null;
  artifactKey?: string | null;
  revision?: number;
  status: string;
};

type TestMessage = {
  id: string;
  reviewArtifact: TestArtifact | null;
};

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

  it("creates a new message for a new artifact instead of attaching to the last message", () => {
    const artifact = { id: "artifact-2", artifactKey: "chapter-6", status: "awaiting_user" };
    const messages = attachReviewArtifactToConversation<TestMessage, TestArtifact>([{ id: "message-1", reviewArtifact: null }], artifact, () => ({
      id: "placeholder",
      reviewArtifact: null,
    }));

    assert.equal(messages.length, 2);
    assert.equal(messages[0].reviewArtifact, null);
    assert.equal(messages[1].reviewArtifact, artifact);
  });

  it("updates an existing artifact message instead of duplicating it", () => {
    const first = { id: "artifact-1", artifactKey: "chapter-5", revision: 1, status: "awaiting_user" };
    const second = { id: "artifact-1", artifactKey: "chapter-5", revision: 2, status: "awaiting_user" };
    const messages = attachReviewArtifactToConversation<TestMessage, TestArtifact>([{ id: "message-1", reviewArtifact: first }], second, () => ({
      id: "placeholder",
      reviewArtifact: null,
    }));

    assert.equal(messages.length, 1);
    assert.equal(messages[0].reviewArtifact, second);
  });

  it("matches artifact messages by stable artifactKey when the id changes", () => {
    const first = { id: "artifact-1", artifactKey: "chapter-5", revision: 1, status: "awaiting_user" };
    const second = { id: "artifact-2", artifactKey: "chapter-5", revision: 2, status: "awaiting_user" };
    const messages = attachReviewArtifactToConversation<TestMessage, TestArtifact>([{ id: "message-1", reviewArtifact: first }], second, () => ({
      id: "placeholder",
      reviewArtifact: null,
    }));

    assert.equal(messages.length, 1);
    assert.equal(messages[0].reviewArtifact, second);
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

  it("只清理权威终态所属任务及其临时草案", () => {
    const transientArtifactIds = new Set(["artifact-without-task"]);

    assert.equal(
      isTerminalReviewArtifact(
        { id: "artifact-by-task", taskId: "task-1" },
        "task-1",
        transientArtifactIds,
      ),
      true,
    );
    assert.equal(
      isTerminalReviewArtifact(
        { id: "artifact-without-task" },
        "task-1",
        transientArtifactIds,
      ),
      true,
    );
    assert.equal(
      isTerminalReviewArtifact(
        { id: "artifact-other-task", taskId: "task-2" },
        "task-1",
        transientArtifactIds,
      ),
      false,
    );
  });

  it("终态清理会让所有在途草案读取失效", () => {
    const epoch = createReviewStateEpoch();
    const staleRequest = epoch.capture();

    assert.equal(epoch.isCurrent(staleRequest), true);
    epoch.invalidate();
    assert.equal(epoch.isCurrent(staleRequest), false);
    assert.equal(epoch.isCurrent(epoch.capture()), true);
  });
});

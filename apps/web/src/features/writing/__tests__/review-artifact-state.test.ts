import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyOptimisticReviewArtifactDecision,
  attachReviewArtifactToConversation,
  attachReviewArtifactToLastMessage,
  clearReviewArtifactFromMessages,
  createReviewStateEpoch,
  isTerminalReviewArtifact,
  resolveReviewArtifactExecutionRunId,
  resolveReviewArtifactActionTaskId,
  resolveReviewArtifactTaskId,
  resolveSelectedUpdateRefsForDecision,
  resolveVisibleReviewArtifact,
} from "../review-artifact-state";

type TestArtifact = {
  id: string;
  taskId?: string | null;
  workflowRunId?: string | null;
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
      resolveReviewArtifactTaskId(null, {
        engineVersion: 1,
        taskId: "task-from-artifact",
        workflowRunId: null,
      }),
      "task-from-artifact"
    );
  });

  it("Artifact 归属覆盖不一致的当前任务，禁止跨 Run 猜测", () => {
    assert.equal(
      resolveReviewArtifactTaskId("current-task", {
        engineVersion: 1,
        taskId: "task-from-artifact",
        workflowRunId: null,
      }),
      "task-from-artifact"
    );
  });

  it("uses the artifact task id for review actions", () => {
    assert.equal(
      resolveReviewArtifactActionTaskId("current-task", {
        engineVersion: 1,
        taskId: "task-from-artifact",
        workflowRunId: null,
      }),
      "task-from-artifact"
    );
  });

  it("V2 Artifact 优先使用 workflowRunId", () => {
    const artifact = { engineVersion: 2 as const, workflowRunId: "run-v2", taskId: null };
    assert.equal(resolveReviewArtifactTaskId(null, artifact), "run-v2");
    assert.equal(resolveReviewArtifactActionTaskId("legacy-current", artifact), "run-v2");
    assert.equal(
      isTerminalReviewArtifact(
        { id: "artifact-v2", engineVersion: 2, workflowRunId: "run-v2", taskId: null },
        "run-v2",
        new Set(),
      ),
      true,
    );
  });

  it("拒绝 engineVersion 与 taskId/workflowRunId 不一致的 Artifact", () => {
    assert.equal(resolveReviewArtifactExecutionRunId({
      engineVersion: 1,
      taskId: null,
      workflowRunId: "run-v2",
    }), null);
    assert.equal(resolveReviewArtifactExecutionRunId({
      engineVersion: 2,
      taskId: "task-v1",
      workflowRunId: null,
    }), null);
    assert.equal(resolveReviewArtifactExecutionRunId({
      engineVersion: 2,
      taskId: "task-v1",
      workflowRunId: "run-v2",
    }), null);
    assert.equal(resolveReviewArtifactActionTaskId("current-task", {
      engineVersion: 2,
      taskId: "task-v1",
      workflowRunId: null,
    }), null);
  });

  it("仅为 verified 的精确 V2 agent_updates 批准原样保留部分选择", () => {
    const refs = [
      { section: "characters", index: 3 },
      { section: "outlineContent" },
    ];
    const artifact = {
      engineVersion: 2 as const,
      kind: "agent_updates",
      sourceBindingStatus: "verified",
      detailLoaded: true,
      payload: { kind: "agent_updates", updates: { characters: [] } },
    };

    assert.equal(
      resolveSelectedUpdateRefsForDecision(artifact, "approve", refs),
      refs,
    );
    assert.deepEqual(
      resolveSelectedUpdateRefsForDecision(artifact, "approve", []),
      [],
    );
    assert.equal(
      resolveSelectedUpdateRefsForDecision(artifact, "approve", undefined),
      null,
    );
    assert.equal(
      resolveSelectedUpdateRefsForDecision(artifact, "revise", refs),
      null,
    );
  });

  it("V2 部分选择身份不完整时明确拒绝，不能静默改成全选", () => {
    const refs = [{ section: "characters", index: 0 }];
    const base = {
      engineVersion: 2 as const,
      kind: "agent_updates",
      sourceBindingStatus: "verified",
      detailLoaded: true,
      payload: { kind: "agent_updates", updates: { characters: [] } },
    };
    const invalidArtifacts = [
      { ...base, detailLoaded: false },
      { ...base, sourceBindingStatus: "not_yet_supported" },
      { ...base, kind: "chapter_draft" },
      { ...base, payload: { ...base.payload, kind: "chapter_draft" } },
      { ...base, payload: { kind: "agent_updates", updates: null } },
    ];

    for (const artifact of invalidArtifacts) {
      assert.throws(
        () => resolveSelectedUpdateRefsForDecision(artifact, "approve", refs),
        /不能提交部分选择/,
      );
    }
  });

  it("V1 部分选择保持原行为且不增加来源状态门禁", () => {
    const refs = [{ section: "characters", index: 1 }];
    assert.equal(
      resolveSelectedUpdateRefsForDecision(
        {
          engineVersion: 1,
          kind: "agent_updates",
          payload: { kind: "agent_updates", updates: {} },
        },
        "approve",
        refs,
      ),
      refs,
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
        {
          id: "artifact-by-task",
          engineVersion: 1,
          taskId: "task-1",
          workflowRunId: null,
        },
        "task-1",
        transientArtifactIds,
      ),
      true,
    );
    assert.equal(
      isTerminalReviewArtifact(
        {
          id: "artifact-without-task",
          engineVersion: 1,
          taskId: null,
          workflowRunId: null,
        },
        "task-1",
        transientArtifactIds,
      ),
      true,
    );
    assert.equal(
      isTerminalReviewArtifact(
        {
          id: "artifact-other-task",
          engineVersion: 1,
          taskId: "task-2",
          workflowRunId: null,
        },
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

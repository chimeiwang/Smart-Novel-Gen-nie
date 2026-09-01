/**
 * ReviewArtifact 契约测试。
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/review-artifact.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  assertReviewArtifactStatusTransition,
  canTransitionReviewArtifactStatus,
  ReviewArtifactDecisionSchema,
  ReviewArtifactDtoSchema,
  ReviewArtifactKindSchema,
  ReviewArtifactPayloadSchema,
  ReviewArtifactStatusSchema,
} from "../review-artifact";

describe("ReviewArtifact contract", () => {
  it("状态集合保持小而明确", () => {
    assert.deepEqual(ReviewArtifactStatusSchema.options, [
      "draft",
      "under_review",
      "awaiting_user",
      "applying",
      "applied",
    ]);
  });

  it("丢弃是用户动作，不是持久化状态", () => {
    assert.equal(ReviewArtifactDecisionSchema.safeParse("discard").success, true);
    assert.equal(ReviewArtifactStatusSchema.safeParse("discarded").success, false);
  });

  it("第一期支持 AgentUpdates 草案", () => {
    assert.equal(ReviewArtifactKindSchema.safeParse("agent_updates").success, true);
    assert.equal(
      ReviewArtifactPayloadSchema.safeParse({
        kind: "agent_updates",
        updates: {
          outlineAdjustments: [
            { action: "update", nodeTitle: "第一章", content: "强化开篇钩子" },
          ],
        },
      }).success,
      true
    );
  });

  it("支持长文本产物草案，不要求正文进入 tool arguments", () => {
    assert.equal(ReviewArtifactKindSchema.safeParse("outline_draft").success, true);
    assert.equal(
      ReviewArtifactPayloadSchema.safeParse({
        kind: "outline_draft",
        content: "第一章 遗孤与遗产\n\n主角发现遗产线索，并在章末遇到第一次反转。",
      }).success,
      true
    );
  });

  it("正文草案可以声明应用时创建下一章", () => {
    assert.equal(
      ReviewArtifactPayloadSchema.safeParse({
        kind: "chapter_draft",
        content: "第二章正文草案",
        target: {
          mode: "new_next_chapter",
          afterChapterId: "chapter-1",
          title: "第 2 章",
        },
      }).success,
      true
    );
  });

  it("Artifact DTO 必须显式携带与 Run 归属一致的 engineVersion", () => {
    const base = {
      id: "artifact-1",
      novelId: "novel-1",
      chapterId: "chapter-1",
      artifactKey: "chapter-1:selection",
      kind: "outline_draft",
      status: "awaiting_user",
      title: "候选",
      summary: "摘要",
      payload: { kind: "outline_draft", content: "候选内容" },
      diff: null,
      createdByAgent: null,
      updatedByAgent: null,
      reviewerAgent: null,
      revision: 1,
      createdAt: "2026-09-01T12:00:00Z",
      updatedAt: "2026-09-01T12:00:00Z",
    };
    assert.equal(ReviewArtifactDtoSchema.safeParse({
      ...base,
      engineVersion: 1,
      taskId: "task-1",
      workflowRunId: null,
    }).success, true);
    assert.equal(ReviewArtifactDtoSchema.safeParse({
      ...base,
      engineVersion: 2,
      taskId: null,
      workflowRunId: "run-2",
    }).success, true);
    assert.equal(ReviewArtifactDtoSchema.safeParse({
      ...base,
      engineVersion: 2,
      taskId: "task-1",
      workflowRunId: null,
    }).success, false);
    assert.equal(ReviewArtifactDtoSchema.safeParse({
      ...base,
      taskId: "task-1",
      workflowRunId: null,
    }).success, false);
  });

  it("只允许明确的草案状态流转", () => {
    assert.equal(canTransitionReviewArtifactStatus("awaiting_user", "draft"), true);
    assert.equal(canTransitionReviewArtifactStatus("awaiting_user", "under_review"), true);
    assert.equal(canTransitionReviewArtifactStatus("awaiting_user", "applying"), true);
    assert.equal(canTransitionReviewArtifactStatus("applying", "applied"), true);
    assert.equal(canTransitionReviewArtifactStatus("applied", "awaiting_user"), false);
    assert.throws(
      () => assertReviewArtifactStatusTransition("applied", "awaiting_user"),
      /不能从/
    );
  });
});

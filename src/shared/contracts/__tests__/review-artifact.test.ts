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

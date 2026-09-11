import assert from "node:assert/strict";
import test from "node:test";

import { scriptReviewPresentation } from "../production/script-review-presentation";

test("revise 即使 findings 为空，也展示待核对结论、摘要和所有修改要求", () => {
  const review = scriptReviewPresentation({ review: { decision: "revise", summary: "交信后的角色状态尚不连贯", requiredChanges: ["核对顾舟是否已持有信", "说明回忆发生在交信之前"], findings: [] }, reviewFindings: [] });
  assert.equal(review.label, "仍有待核对项");
  assert.equal(review.requiresReview, true);
  assert.equal(review.summary, "交信后的角色状态尚不连贯");
  assert.deepEqual(review.requiredChanges, ["核对顾舟是否已持有信", "说明回忆发生在交信之前"]);
  assert.deepEqual(review.findings, []);
});

test("null 或缺失 review 只表示尚无审阅结果，旧 findings 不冒充完整结论", () => {
  const finding = { code: "continuity" as const, sceneId: null, lineId: null, message: "核对回忆时间" };
  const review = scriptReviewPresentation({ review: null, reviewFindings: [finding] });
  assert.equal(review.label, "尚无审阅结果");
  assert.equal(review.summary, null);
  assert.deepEqual(review.findings, [finding]);
  assert.equal(scriptReviewPresentation({ reviewFindings: [] }).label, "尚无审阅结果");
});

test("完整结论优先于旧 findings，只有明确 pass 才展示 AI 审阅通过", () => {
  const review = scriptReviewPresentation({ review: { decision: "pass", summary: "本轮承接与对白已核对", requiredChanges: [], findings: [] }, reviewFindings: [{ code: "continuity", sceneId: null, lineId: null, message: "旧轮次问题" }] });
  assert.equal(review.label, "已通过 AI 审阅");
  assert.equal(review.requiresReview, false);
  assert.equal(review.summary, "本轮承接与对白已核对");
  assert.deepEqual(review.findings, []);
});

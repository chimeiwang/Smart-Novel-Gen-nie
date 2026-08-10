import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { normalizeReviewArtifactDiff } from "../review-artifact-diff";

describe("ReviewArtifact diff 归一化", () => {
  it("把 Core 的单对象 selection diff 与普通数组 diff 分开处理", () => {
    const selectionDiff = {
      type: "selection" as const,
      mode: "replace_selection",
      resourceType: "chapter_content",
      resourceId: "chapter-1",
      selectionStart: 2,
      selectionEnd: 4,
      selectedText: "旧文",
      replacement: "新文",
      before: "前缀旧文后缀",
      after: "前缀新文后缀",
      prefix: "前缀",
      suffix: "后缀",
    };

    const normalized = normalizeReviewArtifactDiff(selectionDiff, [
      { section: "characters", action: "update", name: "不应使用", fields: [] },
    ]);

    assert.deepEqual(normalized.selectionDiff, selectionDiff);
    assert.deepEqual(normalized.updateDiff, []);
    assert.equal(normalized.selectionDiff?.after, "前缀新文后缀");
  });

  it("保留普通 update diff 数组路径", () => {
    const updates = [{ section: "characters", action: "update", name: "角色", fields: [] }];
    const normalized = normalizeReviewArtifactDiff(updates, null);
    assert.deepEqual(normalized.selectionDiff, null);
    assert.deepEqual(normalized.updateDiff, updates);
  });
});

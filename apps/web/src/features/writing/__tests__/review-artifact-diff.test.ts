import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  describeUpdateDiffValue,
  normalizeReviewArtifactDiff,
} from "../review-artifact-diff";

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
    const updates = [{
      section: "大纲节点",
      action: "update",
      name: "第一卷",
      fields: [
        { field: "order", label: "顺序", oldValue: "1", newValue: "2" },
        {
          field: "linkedChapterId",
          label: "关联章节",
          oldValue: "chapter-1",
          newValue: "chapter-2",
        },
        {
          field: "sourceUrl",
          label: "来源地址",
          newValue: "https://example.com/source",
        },
        { field: "content", label: "内容", oldValue: "旧内容", newValue: "" },
        { field: "parentId", label: "父节点", oldValue: "parent-1" },
      ],
    }];
    const normalized = normalizeReviewArtifactDiff(updates, null);
    assert.deepEqual(normalized.selectionDiff, null);
    assert.deepEqual(normalized.updateDiff, updates);
  });

  it("区分未设置、空字符串、仅空白和真实原文", () => {
    assert.deepEqual(describeUpdateDiffValue(undefined, "未提供"), {
      text: "未提供",
      isPlaceholder: true,
    });
    assert.deepEqual(describeUpdateDiffValue(null, "未提供"), {
      text: "未设置（null）",
      isPlaceholder: true,
    });
    assert.deepEqual(describeUpdateDiffValue("", "未设置（null）"), {
      text: "空字符串",
      isPlaceholder: true,
    });
    assert.deepEqual(describeUpdateDiffValue(" \n", "未设置（null）"), {
      text: "仅空白文本：\" \\n\"",
      isPlaceholder: true,
    });
    assert.deepEqual(describeUpdateDiffValue(" 原文 \n", "未设置（null）"), {
      text: " 原文 \n",
      isPlaceholder: false,
    });
  });
});

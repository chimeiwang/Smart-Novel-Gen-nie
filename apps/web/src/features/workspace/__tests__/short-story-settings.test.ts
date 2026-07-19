import assert from "node:assert/strict";
import test from "node:test";

import { buildWritingBibleTargetUpdate } from "../short-story/short-story-settings";

test("修正目标字数时完整保留现有作品圣经创作字段", () => {
  const request = buildWritingBibleTargetUpdate({
    id: "bible-1",
    storyLengthProfile: "short_medium",
    targetTotalWordCount: 5_000,
    genre: "悬疑",
    targetReaders: "成年读者",
    coreSellingPoint: "身份交换",
    readerPromise: "结尾兑现",
    appealModel: "谜题推进",
    taboo: "不使用梦境解谜",
    comparableTitles: "示例作品",
    notes: "保留冷峻语气",
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-01T00:00:00Z",
  }, 20_000);

  assert.deepEqual(request, {
    targetTotalWordCount: 20_000,
    genre: "悬疑",
    targetReaders: "成年读者",
    coreSellingPoint: "身份交换",
    readerPromise: "结尾兑现",
    appealModel: "谜题推进",
    taboo: "不使用梦境解谜",
    comparableTitles: "示例作品",
    notes: "保留冷峻语气",
  });
  assert.equal("storyLengthProfile" in request, false);
});

test("清空篇幅参考时显式提交 null 并保留作品圣经字段", () => {
  const request = buildWritingBibleTargetUpdate({
    id: "bible-1",
    storyLengthProfile: "short_medium",
    targetTotalWordCount: 20_000,
    genre: "悬疑",
    targetReaders: null,
    coreSellingPoint: null,
    readerPromise: null,
    appealModel: null,
    taboo: null,
    comparableTitles: null,
    notes: null,
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-01T00:00:00Z",
  }, null);

  assert.equal(request.targetTotalWordCount, null);
  assert.equal(request.genre, "悬疑");
});

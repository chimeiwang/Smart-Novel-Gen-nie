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


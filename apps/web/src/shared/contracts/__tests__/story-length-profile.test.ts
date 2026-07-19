import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  STORY_LENGTH_PROFILE_CONFIG,
  formatStoryLengthProfile,
  normalizeStoryLengthProfile,
} from "../story-length-profile";

describe("story length profile contract", () => {
  it("不会把缺失或未知篇幅静默当成长篇", () => {
    assert.equal(normalizeStoryLengthProfile("short_medium"), "short_medium");
    assert.equal(normalizeStoryLengthProfile("bad-value"), null);
    assert.equal(normalizeStoryLengthProfile(null), null);
  });

  it("中短篇范围固定为 6000 到 80000 且不携带固定章节数量", () => {
    assert.deepEqual(STORY_LENGTH_PROFILE_CONFIG.short_medium.targetWords, [6_000, 80_000]);
    assert.deepEqual(STORY_LENGTH_PROFILE_CONFIG.long_serial.targetWords, [300_000, 1_000_000]);
    assert.equal("chapterCount" in STORY_LENGTH_PROFILE_CONFIG.short_medium, false);
    assert.equal("plotUnits" in STORY_LENGTH_PROFILE_CONFIG.short_medium, false);
    assert.equal("chapterWords" in STORY_LENGTH_PROFILE_CONFIG.short_medium, false);
  });

  it("展示篇幅和目标字数时不附加固定章节数量", () => {
    assert.match(formatStoryLengthProfile("short_medium", 80_000), /中短篇/);
    assert.match(formatStoryLengthProfile("short_medium", 80_000), /80000/);
    assert.match(formatStoryLengthProfile("long_serial", null), /长篇连载/);
    assert.doesNotMatch(formatStoryLengthProfile("short_medium", 80_000), /章/);
  });
});

import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  STORY_LENGTH_PROFILE_CONFIG,
  formatStoryLengthProfile,
  normalizeStoryLengthProfile,
} from "../story-length-profile";

describe("story length profile contract", () => {
  it("normalizes unknown values to long serial", () => {
    assert.equal(normalizeStoryLengthProfile("short_medium"), "short_medium");
    assert.equal(normalizeStoryLengthProfile("bad-value"), "long_serial");
    assert.equal(normalizeStoryLengthProfile(null), "long_serial");
  });

  it("keeps novella and long serial planning ranges distinct", () => {
    assert.deepEqual(STORY_LENGTH_PROFILE_CONFIG.short_medium.targetWords, [30_000, 100_000]);
    assert.deepEqual(STORY_LENGTH_PROFILE_CONFIG.short_medium.chapterCount, [8, 25]);
    assert.deepEqual(STORY_LENGTH_PROFILE_CONFIG.long_serial.targetWords, [300_000, 1_000_000]);
    assert.deepEqual(STORY_LENGTH_PROFILE_CONFIG.long_serial.chapterCount, [80, 300]);
  });

  it("formats target word count for Agent context", () => {
    assert.match(formatStoryLengthProfile("short_medium", 80_000), /中短篇/);
    assert.match(formatStoryLengthProfile("short_medium", 80_000), /80000/);
    assert.match(formatStoryLengthProfile("long_serial", null), /长篇连载/);
  });
});

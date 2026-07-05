import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  HistoricalWritingTaskPhaseSchema,
  ResumableWritingTaskPhaseSchema,
  WritingSessionRecoveryStateSchema,
} from "../writing-session";

describe("writing session recovery contract", () => {
  it("separates resumable phases from historical phases", () => {
    assert.equal(ResumableWritingTaskPhaseSchema.safeParse("awaiting_user_review").success, true);
    assert.equal(ResumableWritingTaskPhaseSchema.safeParse("completed").success, false);
    assert.equal(HistoricalWritingTaskPhaseSchema.safeParse("completed").success, true);
    assert.equal(HistoricalWritingTaskPhaseSchema.safeParse("active").success, false);
  });

  it("accepts an empty new-session recovery state", () => {
    assert.equal(WritingSessionRecoveryStateSchema.safeParse({
      currentTask: null,
      lastTask: null,
    }).success, true);
  });
});

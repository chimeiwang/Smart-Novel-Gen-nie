import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { getWritingNextActions, WRITING_SHORTCUT_ACTIONS } from "../product-actions";

describe("writing product actions", () => {
  it("prioritizes unresolved artifacts before generating more work", () => {
    const actions = getWritingNextActions({
      chapterStatus: "drafting",
      wordCount: 0,
      awaitingArtifactCount: 2,
      hasApprovedBeatPlan: false,
      hasOpenConsistencyCheck: false,
    });

    assert.equal(actions[0].kind, "open_artifacts");
    assert.equal(actions[1].kind, "plan_beat");
  });

  it("uses approved chapter plans as the next writing entry", () => {
    const actions = getWritingNextActions({
      chapterStatus: "drafting",
      wordCount: 0,
      awaitingArtifactCount: 0,
      hasApprovedBeatPlan: true,
      hasOpenConsistencyCheck: false,
    });

    assert.equal(actions[0].kind, "write_draft");
  });

  it("does not expose removed lore synchronization actions", () => {
    const snapshots = [
      {
        chapterStatus: "completed",
        wordCount: 3000,
        awaitingArtifactCount: 0,
        hasApprovedBeatPlan: true,
        hasOpenConsistencyCheck: false,
      },
      {
        chapterStatus: "drafting",
        wordCount: 0,
        awaitingArtifactCount: 0,
        hasApprovedBeatPlan: false,
        hasOpenConsistencyCheck: false,
      },
    ];

    assert.equal(
      WRITING_SHORTCUT_ACTIONS.some((action) => String(action.kind) === "sync_lore"),
      false,
    );
    for (const snapshot of snapshots) {
      assert.equal(
        getWritingNextActions(snapshot).some((action) => String(action.kind) === "sync_lore"),
        false,
      );
    }
  });
});

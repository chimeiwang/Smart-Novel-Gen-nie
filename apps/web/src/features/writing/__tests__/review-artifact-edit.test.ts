import assert from "node:assert/strict";
import test from "node:test";

import { isChapterWritingReviewArtifact } from "../review-artifact-edit";

test("仅现有章节正文草案开放完整正文编辑", () => {
  assert.equal(isChapterWritingReviewArtifact("chapter_draft", {
    operation: "write_chapter", target: { mode: "existing_chapter", chapterId: "c1" },
  }), true);
  for (const payload of [
    null, {}, { operation: "write_chapter" },
    { operation: "write_chapter", target: { mode: "new_next_chapter" } },
    { operation: "rewrite_chapter_selection", target: { mode: "replace_selection" } },
    { operation: "plan_chapter", target: { mode: "existing_chapter" } },
  ]) {
    assert.equal(isChapterWritingReviewArtifact("chapter_draft", payload), false);
  }
  assert.equal(isChapterWritingReviewArtifact("beat_plan", {
    operation: "write_chapter", target: { mode: "existing_chapter" },
  }), false);
});

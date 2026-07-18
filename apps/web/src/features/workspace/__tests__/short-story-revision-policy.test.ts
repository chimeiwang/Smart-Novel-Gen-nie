import assert from "node:assert/strict";
import test from "node:test";

import {
  canRestoreOutlineRevision,
  shouldLoadOutlineRevisions,
} from "../short-story/short-story-revision-policy";

test("revision 列表和详情只属于大纲 pane", () => {
  assert.equal(shouldLoadOutlineRevisions("outline", true), true);
  assert.equal(shouldLoadOutlineRevisions("draft", true), false);
  assert.equal(shouldLoadOutlineRevisions("formal", true), false);
  assert.equal(shouldLoadOutlineRevisions("outline", false), false);
});

test("只有等待用户确认的大纲才能恢复历史版本", () => {
  assert.equal(canRestoreOutlineRevision({ pane: "outline", status: "awaiting_user" }), true);
  assert.equal(canRestoreOutlineRevision({ pane: "outline", status: "draft" }), false);
  assert.equal(canRestoreOutlineRevision({ pane: "outline", status: "under_review" }), false);
  assert.equal(canRestoreOutlineRevision({ pane: "outline", status: "applying" }), false);
  assert.equal(canRestoreOutlineRevision({ pane: "outline", status: "applied" }), false);
  assert.equal(canRestoreOutlineRevision({ pane: "draft", status: "awaiting_user" }), false);
  assert.equal(canRestoreOutlineRevision({ pane: "formal", status: "awaiting_user" }), false);
});

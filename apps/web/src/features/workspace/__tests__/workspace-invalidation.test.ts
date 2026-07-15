import assert from "node:assert/strict";
import test from "node:test";

import {
  dispatchWorkspaceInvalidation,
  subscribeWorkspaceInvalidation,
} from "../workspace-invalidation";

test("只把同一小说的失效分组交给订阅者", () => {
  const received: string[][] = [];
  const unsubscribe = subscribeWorkspaceInvalidation("novel-1", (groups) => {
    received.push(groups);
  });

  dispatchWorkspaceInvalidation("novel-2", ["lore"]);
  dispatchWorkspaceInvalidation("novel-1", ["lore", "planning"]);
  unsubscribe();
  dispatchWorkspaceInvalidation("novel-1", ["resources"]);

  assert.deepEqual(received, [["lore", "planning"]]);
});

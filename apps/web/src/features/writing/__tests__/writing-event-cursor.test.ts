import assert from "node:assert/strict";
import test from "node:test";

import { createWritingEventCursors } from "../writing-event-cursor";

test("keeps the last event id per task", () => {
  const cursors = createWritingEventCursors();
  cursors.update("task-1", "event-4");
  cursors.update("task-2", "event-2");

  assert.deepEqual(cursors.headers("task-1"), { "Last-Event-ID": "event-4" });
  assert.deepEqual(cursors.headers("task-2"), { "Last-Event-ID": "event-2" });
});

test("reuses one parser state for each task", () => {
  const cursors = createWritingEventCursors();

  assert.equal(cursors.state("task-1"), cursors.state("task-1"));
  assert.notEqual(cursors.state("task-1"), cursors.state("task-2"));
});

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

test("V2 snapshot atomically resets event id and sequence", () => {
  const cursors = createWritingEventCursors();
  cursors.state("run-1").lastSequence = 9;
  cursors.update("run-1", "9");

  cursors.resetToSnapshot("run-1", 3);
  assert.deepEqual(cursors.headers("run-1"), { "Last-Event-ID": "3" });
  assert.equal(cursors.state("run-1").lastSequence, 3);

  cursors.resetToSnapshot("run-1", 0);
  assert.deepEqual(cursors.headers("run-1"), {});
  assert.equal(cursors.state("run-1").lastSequence, 0);
});

test("服务端拒绝 cursor 后可清空并从 snapshot 重建", () => {
  const cursors = createWritingEventCursors();
  cursors.resetToSnapshot("run-1", 12);

  cursors.clear("run-1");

  assert.deepEqual(cursors.headers("run-1"), {});
  assert.equal(cursors.state("run-1").lastSequence, 0);
});

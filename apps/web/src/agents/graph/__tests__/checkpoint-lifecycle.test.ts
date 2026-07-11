import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  CheckpointCleanupScheduler,
  type CheckpointCleanupTimerApi,
} from "../checkpoint-lifecycle";

type FakeHandle = ReturnType<typeof setTimeout>;

function createFakeTimers() {
  let nextId = 0;
  const callbacks = new Map<number, () => void>();
  const handles = new Map<FakeHandle, number>();
  const timerApi: CheckpointCleanupTimerApi = {
    setTimeout(callback) {
      const id = ++nextId;
      const handle = { unref() {} } as FakeHandle;
      callbacks.set(id, callback);
      handles.set(handle, id);
      return handle;
    },
    clearTimeout(handle) {
      const id = handles.get(handle);
      if (id !== undefined) callbacks.delete(id);
    },
  };

  return {
    timerApi,
    runNext() {
      const entry = callbacks.entries().next().value as [number, () => void] | undefined;
      if (!entry) return false;
      callbacks.delete(entry[0]);
      entry[1]();
      return true;
    },
  };
}

describe("CheckpointCleanupScheduler", () => {
  it("replaces an existing TTL and runs cleanup once", async () => {
    const fake = createFakeTimers();
    const scheduler = new CheckpointCleanupScheduler(fake.timerApi);
    const cleaned: string[] = [];
    const cleanup = async (threadId: string) => {
      cleaned.push(threadId);
    };

    scheduler.schedule({ threadId: "task-1", ttlMs: 100, cleanup });
    scheduler.schedule({ threadId: "task-1", ttlMs: 200, cleanup });

    assert.equal(scheduler.has("task-1"), true);
    assert.equal(fake.runNext(), true);
    await Promise.resolve();
    assert.deepEqual(cleaned, ["task-1"]);
    assert.equal(scheduler.has("task-1"), false);
    assert.equal(fake.runNext(), false);
  });

  it("cancels cleanup when a task resumes", () => {
    const fake = createFakeTimers();
    const scheduler = new CheckpointCleanupScheduler(fake.timerApi);
    scheduler.schedule({ threadId: "task-2", ttlMs: 100, cleanup: async () => undefined });

    assert.equal(scheduler.cancel("task-2"), true);
    assert.equal(scheduler.has("task-2"), false);
    assert.equal(fake.runNext(), false);
  });

  it("does not schedule a non-positive TTL", () => {
    const fake = createFakeTimers();
    const scheduler = new CheckpointCleanupScheduler(fake.timerApi);
    scheduler.schedule({ threadId: "task-3", ttlMs: 0, cleanup: async () => undefined });

    assert.equal(scheduler.has("task-3"), false);
  });
});

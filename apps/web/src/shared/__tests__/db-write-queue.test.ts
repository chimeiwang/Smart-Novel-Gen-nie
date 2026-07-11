import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  BoundedDbWriteQueue,
  enqueueDbWrite,
  waitForDbWriteQueueIdle,
} from "../lib/db-write-queue";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

describe("BoundedDbWriteQueue", () => {
  it("runs queued writes sequentially when concurrency is 1", async () => {
    const queue = new BoundedDbWriteQueue({ maxSize: 10, concurrency: 1 });
    const events: string[] = [];

    queue.enqueue(async () => {
      events.push("a:start");
      await sleep(10);
      events.push("a:end");
    });
    queue.enqueue(async () => {
      events.push("b:start");
      await sleep(1);
      events.push("b:end");
    });

    await queue.onIdle();

    assert.deepEqual(events, ["a:start", "a:end", "b:start", "b:end"]);
    assert.equal(queue.getStats().completed, 2);
  });

  it("drops new writes after the bounded capacity is full", async () => {
    const queue = new BoundedDbWriteQueue({ maxSize: 3, concurrency: 1 });
    let releaseFirstTask!: () => void;
    const firstTaskStarted = new Promise<void>((resolve) => {
      queue.enqueue(async () => {
        resolve();
        await new Promise<void>((release) => {
          releaseFirstTask = release;
        });
      });
    });

    await firstTaskStarted;

    const acceptedSecond = queue.enqueue(async () => {});
    const acceptedThird = queue.enqueue(async () => {});
    const acceptedFourth = queue.enqueue(async () => {});

    releaseFirstTask();
    await queue.onIdle();

    assert.equal(acceptedSecond, true);
    assert.equal(acceptedThird, true);
    assert.equal(acceptedFourth, false);
    assert.equal(queue.getStats().dropped, 1);
    assert.equal(queue.getStats().completed, 3);
  });

  it("uses a default total capacity of 100 writes", async () => {
    const queue = new BoundedDbWriteQueue();
    let releaseFirstTask!: () => void;
    const firstTaskStarted = new Promise<void>((resolve) => {
      queue.enqueue(async () => {
        resolve();
        await new Promise<void>((release) => {
          releaseFirstTask = release;
        });
      });
    });

    await firstTaskStarted;

    for (let index = 0; index < 99; index += 1) {
      assert.equal(queue.enqueue(async () => {}), true);
    }

    assert.equal(queue.enqueue(async () => {}), false);

    releaseFirstTask();
    await queue.onIdle();

    assert.equal(queue.getStats().dropped, 1);
    assert.equal(queue.getStats().completed, 100);
  });

  it("uses a default concurrency of 3 writes", async () => {
    const queue = new BoundedDbWriteQueue();
    let active = 0;
    let maxActive = 0;
    let releaseTasks!: () => void;
    const releaseSignal = new Promise<void>((resolve) => {
      releaseTasks = resolve;
    });
    const allStarted = new Promise<void>((resolve) => {
      let started = 0;
      for (let index = 0; index < 3; index += 1) {
        queue.enqueue(async () => {
          active += 1;
          maxActive = Math.max(maxActive, active);
          started += 1;
          if (started === 3) resolve();
          await releaseSignal;
          active -= 1;
        });
      }
    });

    await allStarted;
    releaseTasks();
    await queue.onIdle();

    assert.equal(maxActive, 3);
  });

  it("records a failed write and continues processing later writes", async () => {
    const errors: string[] = [];
    const queue = new BoundedDbWriteQueue({
      maxSize: 10,
      concurrency: 1,
      onError: (error) => errors.push(error instanceof Error ? error.message : String(error)),
    });
    const completed: string[] = [];

    queue.enqueue(async () => {
      throw new Error("db is temporarily unavailable");
    });
    queue.enqueue(async () => {
      completed.push("next");
    });

    await queue.onIdle();

    assert.deepEqual(errors, ["db is temporarily unavailable"]);
    assert.deepEqual(completed, ["next"]);
    assert.equal(queue.getStats().failed, 1);
    assert.equal(queue.getStats().completed, 1);
  });

  it("exposes a shared helper for non-critical write tasks", async () => {
    const events: string[] = [];

    const accepted = enqueueDbWrite(async () => {
      events.push("shared-helper");
    }, "test-helper");

    await waitForDbWriteQueueIdle();

    assert.equal(accepted, true);
    assert.deepEqual(events, ["shared-helper"]);
  });
});

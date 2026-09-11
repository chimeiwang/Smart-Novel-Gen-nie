import assert from "node:assert/strict";
import { test } from "node:test";

import { startTaskPolling } from "../task-polling";

const settle = () => new Promise<void>((resolve) => setImmediate(resolve));

test("任务连续处于活跃状态时持续读取，终态停止", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let reads = 0;
  const stop = startTaskPolling(async () => ++reads < 3, (error) => assert.fail(String(error)), 10);
  for (let index = 0; index < 5; index += 1) {
    context.mock.timers.tick(10);
    await settle();
  }
  assert.equal(reads, 3);
  stop();
});

test("临时读取失败后可继续观察，不重叠执行", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let reads = 0;
  let errors = 0;
  const stop = startTaskPolling(async () => {
    reads += 1;
    if (reads === 1) throw new Error("暂时断网");
    return false;
  }, () => { errors += 1; }, 10);
  context.mock.timers.tick(10);
  await settle();
  context.mock.timers.tick(10);
  await settle();
  assert.equal(reads, 2);
  assert.equal(errors, 1);
  stop();
});

test("离开时中止在途读取，迟到结果不再安排下一次轮询", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let signal: AbortSignal | undefined;
  let finish: ((active: boolean) => void) | undefined;
  let reads = 0;
  const stop = startTaskPolling(async (currentSignal) => {
    signal = currentSignal;
    reads += 1;
    return new Promise<boolean>((resolve) => { finish = resolve; });
  }, (error) => assert.fail(String(error)), 10);
  context.mock.timers.tick(10);
  stop();
  assert.equal(signal?.aborted, true);
  finish?.(true);
  await settle();
  context.mock.timers.tick(100);
  assert.equal(reads, 1);
});

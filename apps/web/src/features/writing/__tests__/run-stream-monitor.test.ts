import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { monitorRunStream } from "../run-stream-monitor";

type Outcome = { state: "running" | "succeeded" };

describe("写作事件流恢复", () => {
  it("reader 异常后先读取权威状态，再用原游标重新连接", async () => {
    const cursors = { value: "42-0" };
    const openedWith: string[] = [];
    const outcomes: Outcome[] = [
      { state: "running" },
      { state: "succeeded" },
    ];
    let consumeCount = 0;

    await monitorRunStream<Outcome>({
      open: async () => {
        openedWith.push(cursors.value);
        return {} as Response;
      },
      consume: async () => {
        consumeCount += 1;
        if (consumeCount === 1) {
          throw new TypeError("代理断开连接");
        }
        return false;
      },
      readOutcome: async () => outcomes.shift() ?? { state: "succeeded" },
      handleOutcome: () => undefined,
      shouldClose: (outcome) => outcome.state === "succeeded",
      wait: async () => undefined,
    });

    assert.deepEqual(openedWith, ["42-0", "42-0"]);
    assert.equal(consumeCount, 2);
  });

  it("首次连接失败不会把仍在运行的任务直接置错", async () => {
    const handled: Outcome[] = [];
    let opens = 0;

    await monitorRunStream<Outcome>({
      open: async () => {
        opens += 1;
        if (opens === 1) throw new TypeError("连接失败");
        return {} as Response;
      },
      consume: async () => false,
      readOutcome: async () => (
        opens === 1 ? { state: "running" } : { state: "succeeded" }
      ),
      handleOutcome: (outcome) => handled.push(outcome),
      shouldClose: (outcome) => outcome.state === "succeeded",
      wait: async () => undefined,
    });

    assert.equal(opens, 2);
    assert.deepEqual(handled, [
      { state: "running" },
      { state: "succeeded" },
    ]);
  });

  it("连接失败同时收到取消信号时统一抛出 AbortError", async () => {
    const controller = new AbortController();

    await assert.rejects(
      monitorRunStream<Outcome>({
        open: async () => {
          controller.abort();
          throw new TypeError("连接同时断开");
        },
        consume: async () => false,
        readOutcome: async () => ({ state: "running" }),
        handleOutcome: () => undefined,
        shouldClose: () => false,
        signal: controller.signal,
        wait: async () => undefined,
      }),
      (error: unknown) => error instanceof DOMException && error.name === "AbortError",
    );
  });
});

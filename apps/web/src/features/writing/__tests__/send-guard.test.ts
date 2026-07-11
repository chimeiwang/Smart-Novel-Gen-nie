import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createAsyncActionGuard } from "../send-guard";

describe("writing send guard", () => {
  it("blocks duplicate async actions before React state can update", async () => {
    const guard = createAsyncActionGuard();
    let calls = 0;
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });

    const first = guard.run(async () => {
      calls += 1;
      await pending;
      return "first";
    });
    const second = guard.run(async () => {
      calls += 1;
      return "second";
    });

    assert.equal(second, undefined);
    assert.equal(calls, 1);

    release();
    assert.equal(await first, "first");
  });

  it("allows another action after the first one settles", async () => {
    const guard = createAsyncActionGuard();

    assert.equal(await guard.run(async () => "first"), "first");
    assert.equal(await guard.run(async () => "second"), "second");
  });
});

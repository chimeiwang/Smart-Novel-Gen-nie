import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { shouldPersistOptimisticWritingMessage } from "../message-persistence";

describe("writing message persistence", () => {
  it("does not persist workflow-owned optimistic messages from the client", () => {
    assert.equal(
      shouldPersistOptimisticWritingMessage({
        role: "user",
        content: "继续写",
        persist: false,
      }),
      false
    );
  });

  it("persists normal client-created messages by default", () => {
    assert.equal(
      shouldPersistOptimisticWritingMessage({
        role: "system",
        content: "内容已采纳",
      }),
      true
    );
  });
});

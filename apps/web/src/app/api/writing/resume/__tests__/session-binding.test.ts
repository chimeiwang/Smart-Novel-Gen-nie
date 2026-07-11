import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { validateResumeSessionBinding } from "../session-binding";

describe("validateResumeSessionBinding", () => {
  it("allows resume when the task is bound to the selected writing session", () => {
    assert.equal(
      validateResumeSessionBinding({
        requestedWritingSessionId: "session-1",
        taskWritingSessionId: "session-1",
      }),
      null
    );
  });

  it("rejects resume when the selected session does not own the task", () => {
    assert.equal(
      validateResumeSessionBinding({
        requestedWritingSessionId: "session-1",
        taskWritingSessionId: "session-2",
      }),
      "当前任务不属于所选写作会话"
    );
  });

  it("rejects resume for an unbound legacy task when a session id was supplied", () => {
    assert.equal(
      validateResumeSessionBinding({
        requestedWritingSessionId: "session-1",
        taskWritingSessionId: null,
      }),
      "当前任务不属于所选写作会话"
    );
  });

  it("skips binding validation when the client did not supply a writing session id", () => {
    assert.equal(
      validateResumeSessionBinding({
        requestedWritingSessionId: null,
        taskWritingSessionId: "session-1",
      }),
      null
    );
  });
});

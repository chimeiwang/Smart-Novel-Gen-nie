import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { getResumeMode } from "../resume-policy";

describe("getResumeMode", () => {
  it("uses interrupt resume when checkpoint has pending next nodes and message is not an explicit Agent command", () => {
    assert.equal(
      getResumeMode({
        hasPendingCheckpoint: true,
        hasGraphStateSnapshot: false,
        userMessage: "确认保存",
      }),
      "interrupt_resume"
    );
  });

  it("starts a fresh graph when user explicitly invokes an Agent", () => {
    assert.equal(
      getResumeMode({
        hasPendingCheckpoint: true,
        hasGraphStateSnapshot: true,
        userMessage: "@编辑 重新评审",
      }),
      "fresh"
    );
  });

  it("uses a persisted graph state snapshot when there is no pending checkpoint", () => {
    assert.equal(
      getResumeMode({
        hasPendingCheckpoint: false,
        hasGraphStateSnapshot: true,
        userMessage: "继续",
      }),
      "snapshot_resume"
    );
  });

  it("starts a fresh graph when there is no pending checkpoint or snapshot", () => {
    assert.equal(
      getResumeMode({
        hasPendingCheckpoint: false,
        hasGraphStateSnapshot: false,
        userMessage: "继续",
      }),
      "fresh"
    );
  });
});

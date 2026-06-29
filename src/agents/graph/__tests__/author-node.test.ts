import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { shouldBlockForMissingApprovedBeatPlan } from "../nodes/author-node";
import type { WritingState } from "../state";

function createInput(overrides: Partial<Pick<WritingState, "currentOperation" | "novelData" | "userMessage">> = {}) {
  return {
    currentOperation: {
      kind: "write_chapter",
    } as WritingState["currentOperation"],
    novelData: {
      approvedBeatPlan: null,
    } as WritingState["novelData"],
    userMessage: "请基于已批准章节计划生成本章正文草案",
    ...overrides,
  };
}

describe("approved Beat Plan preGuard", () => {
  it("blocks an explicit approved Beat Plan request when no plan exists", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput()), true);
  });

  it("allows ordinary writing requests without an approved Beat Plan", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({ userMessage: "请生成本章正文草案" })), false);
  });

  it("does not mistake an explicit Beat Plan opt-out for a requirement", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({ userMessage: "不需要 Beat Plan，直接生成本章正文草案" })), false);
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({ userMessage: "即使没有已批准章节计划也继续写" })), false);
  });

  it("allows the explicit request when an approved Beat Plan exists", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({
      novelData: {
        approvedBeatPlan: { id: "plan-1" },
      } as WritingState["novelData"],
    })), false);
  });

  it("does not block unrelated operations", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({
      currentOperation: { kind: "review_chapter" } as WritingState["currentOperation"],
    })), false);
  });
});

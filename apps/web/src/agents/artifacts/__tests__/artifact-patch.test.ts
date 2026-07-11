import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { applyEvaluationPatchesToPayload } from "../artifact-service";

describe("artifact patch", () => {
  it("applies a unique text replacement to text artifacts", () => {
    const result = applyEvaluationPatchesToPayload({
      payload: { kind: "chapter_draft", content: "老钱说，前天接了个活。" },
      patches: [{ kind: "text_replace", find: "前天接了个活", replace: "今天接了个活" }],
    });

    assert.equal(result.success, true);
    if (result.success) {
      assert.deepEqual(result.payload, {
        kind: "chapter_draft",
        content: "老钱说，今天接了个活。",
      });
    }
  });

  it("rejects text replacement when the target is missing", () => {
    const result = applyEvaluationPatchesToPayload({
      payload: { kind: "chapter_draft", content: "老钱今天接了个活。" },
      patches: [{ kind: "text_replace", find: "前天接了个活", replace: "今天接了个活" }],
    });

    assert.equal(result.success, false);
  });

  it("rejects text replacement when the target is ambiguous", () => {
    const result = applyEvaluationPatchesToPayload({
      payload: { kind: "chapter_draft", content: "前天接了个活。前天接了个活。" },
      patches: [{ kind: "text_replace", find: "前天接了个活", replace: "今天接了个活" }],
    });

    assert.equal(result.success, false);
  });

  it("merges agent_updates patches into agent update artifacts", () => {
    const result = applyEvaluationPatchesToPayload({
      payload: {
        kind: "agent_updates",
        updates: {
          characters: [{ action: "update", name: "老钱", age: "四十多岁" }],
        },
      },
      patches: [{
        kind: "agent_updates_merge",
        updates: {
          characterExperiences: [{ action: "create", characterName: "老钱", content: "今天接了一个临时活。" }],
        },
      }],
    });

    assert.equal(result.success, true);
    if (result.success && result.payload.kind === "agent_updates") {
      assert.equal(result.payload.updates.characters?.length, 1);
      assert.equal(result.payload.updates.characterExperiences?.length, 1);
    }
  });
});

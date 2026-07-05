import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildEditorSystemPrompt } from "../nodes/editor-node";

describe("编辑返工提示词", () => {
  it("keeps patch limited to tiny text fixes and sends scene-level changes to rewrite", () => {
    const prompt = buildEditorSystemPrompt();

    assert.match(prompt, /patch 只用于错别字/);
    assert.match(prompt, /新增场景/);
    assert.match(prompt, /revisionMode=rewrite/);
  });
});

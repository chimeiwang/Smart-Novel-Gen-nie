import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { buildNewModeSystemAppendix } from "../agent-runner";

describe("AgentRunner prompt appendix", () => {
  it("keeps write_chapter appendix short and free of outline/update-builder rules", () => {
    const appendix = buildNewModeSystemAppendix("write_chapter");

    assert.ok(appendix.length < 500);
    assert.match(appendix, /不要输出 JSON/);
    assert.doesNotMatch(appendix, /结构化大纲/);
    assert.doesNotMatch(appendix, /outlineContent/);
    assert.doesNotMatch(appendix, /append_outline_tree/);
    assert.doesNotMatch(appendix, /put_update_text_block/);
  });

  it("adds outline/update-builder rules only for agent update operations", () => {
    const appendix = buildNewModeSystemAppendix("create_outline");

    assert.match(appendix, /结构化大纲/);
    assert.match(appendix, /outlineContent/);
    assert.match(appendix, /append_outline_tree/);
  });
});

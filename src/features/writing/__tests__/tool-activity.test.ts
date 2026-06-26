import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { getToolActivityLabel, isVisibleToolActivity } from "../tool-activity";

describe("writing tool activity", () => {
  it("returns Chinese labels for known tools", () => {
    assert.equal(getToolActivityLabel("get_novel_info"), "查询作品信息");
    assert.equal(getToolActivityLabel("list_outline_summary"), "查询大纲摘要");
    assert.equal(getToolActivityLabel("get_character_detail"), "读取角色详情");
  });

  it("falls back to the raw tool name", () => {
    assert.equal(getToolActivityLabel("unknown_tool"), "unknown_tool");
  });

  it("hides control tools", () => {
    assert.equal(isVisibleToolActivity("submit_evaluation"), false);
    assert.equal(isVisibleToolActivity("submit_quality_report"), false);
    assert.equal(isVisibleToolActivity("propose_updates"), false);
    assert.equal(isVisibleToolActivity("get_novel_info"), true);
  });
});

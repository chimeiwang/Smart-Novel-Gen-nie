import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  countVisibleToolCalls,
  getToolActivityLabel,
  getToolActivitySummary,
  isVisibleToolActivity,
} from "../tool-activity";

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

  it("counts visible calls without counting results or control tools", () => {
    assert.equal(countVisibleToolCalls([
      { toolName: "get_novel_info" },
      { toolName: "get_novel_info", resultSummary: "已读取作品信息" },
      { toolName: "submit_evaluation" },
      { toolName: "get_character_detail" },
    ]), 2);
  });

  it("formats completed and failed summaries", () => {
    assert.equal(getToolActivitySummary("done", 2), "已完成 · 工具调用 2 次");
    assert.equal(getToolActivitySummary("done", 0), "已完成 · 未调用工具");
    assert.equal(getToolActivitySummary("error", 1), "未完成 · 工具调用 1 次");
  });
});

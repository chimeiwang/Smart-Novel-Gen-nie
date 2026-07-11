/**
 * Agent tool summary tests.
 *
 * 运行方式：npx tsx --test src/agents/lib/__tests__/tools.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { summarizeToolArgs, summarizeToolResult } from "../tools";

describe("agent tool summaries", () => {
  it("keeps empty tool arguments out of user-facing activity", () => {
    assert.equal(summarizeToolArgs({}), "无参数");
  });

  it("summarizes novel info without exposing full context", () => {
    const summary = summarizeToolResult("get_novel_info", JSON.stringify({
      novelName: "遗产猎人",
      chapterTitle: "第一章 遗孤与遗产",
      worldSetting: "很长的世界观正文",
    }));

    assert.equal(summary, "作品《遗产猎人》 · 当前章《第一章 遗孤与遗产》");
  });

  it("summarizes available data counts", () => {
    const summary = summarizeToolResult("list_available_data", JSON.stringify({
      characters: 5,
      factions: 2,
      locations: 0,
      outlineNodes: 8,
      foreshadowings: 2,
      hasStyleProfile: true,
    }));

    assert.equal(summary, "可用资料：角色5、势力2、大纲8、伏笔2、文风画像");
  });

  it("summarizes named array results", () => {
    const summary = summarizeToolResult("list_characters_summary", JSON.stringify([
      { name: "纪寻" },
      { name: "玉虚子" },
      { name: "栾城" },
      { name: "苏棠" },
    ]));

    assert.equal(summary, "读取 4 个角色：纪寻、玉虚子、栾城等");
  });
});

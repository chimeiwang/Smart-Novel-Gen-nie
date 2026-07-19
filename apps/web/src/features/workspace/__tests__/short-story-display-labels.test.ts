import assert from "node:assert/strict";
import test from "node:test";

import {
  formatShortStoryOperation,
  formatShortStoryPhase,
  formatShortStoryVerdict,
  formatShortStoryVersion,
} from "../short-story/short-story-display-labels";

test("中短篇操作使用面向用户的中文名称", () => {
  assert.equal(formatShortStoryOperation("develop_short_outline"), "生成完整大纲");
  assert.equal(formatShortStoryOperation("write_short_story"), "生成完整初稿");
});

test("中短篇任务阶段使用中文且未知值不会泄漏内部枚举", () => {
  assert.equal(formatShortStoryPhase("idle"), "待开始");
  assert.equal(formatShortStoryPhase("active"), "处理中");
  assert.equal(formatShortStoryPhase("waiting_call"), "等待模型响应");
  assert.equal(formatShortStoryPhase("waiting_user"), "等待用户确认");
  assert.equal(formatShortStoryPhase("awaiting_user_review"), "等待用户确认");
  assert.equal(formatShortStoryPhase("completed"), "已完成");
  assert.equal(formatShortStoryPhase("error"), "运行失败");
  assert.equal(formatShortStoryPhase("future_internal_phase"), "状态未知");
});

test("中短篇审核结论和版本号使用中文", () => {
  assert.equal(formatShortStoryVerdict("pass"), "通过");
  assert.equal(formatShortStoryVerdict("revise"), "需修改");
  assert.equal(formatShortStoryVerdict("block"), "未通过");
  assert.equal(formatShortStoryVersion(11), "版本 11");
});

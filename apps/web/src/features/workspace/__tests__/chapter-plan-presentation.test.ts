import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { formatChapterBeatPlanMeta } from "../../chapters/chapter-plan-presentation";

describe("章节计划展示", () => {
  it("非当前章节没有已批准计划时返回空展示", () => {
    assert.equal(
      formatChapterBeatPlanMeta(null, { isCurrentChapter: false }),
      null,
    );
  });

  it("当前章节没有已批准计划时显示未确认提示", () => {
    assert.equal(
      formatChapterBeatPlanMeta(null, { isCurrentChapter: true }),
      "未确认章节计划",
    );
  });

  it("已批准计划继续显示场景数和预计字数", () => {
    assert.equal(
      formatChapterBeatPlanMeta(
        { sceneCount: 3, totalEstimatedWords: 2400 },
        { isCurrentChapter: false },
      ),
      "章节计划 3 场 · 2400 字",
    );
  });
});

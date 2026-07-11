import { describe, it } from "node:test";
import assert from "node:assert/strict";

import type { NovelData } from "@/agents/graph/state";
import { buildUpdateDiffs } from "../artifact-diff";

function makeNovelData(overrides: Partial<NovelData> = {}): NovelData {
  return {
    novelId: "novel-1",
    chapterId: "chapter-1",
    chapters: [{ id: "chapter-1", title: "第一章", content: "", order: 1 }],
    novelName: "测试小说",
    chapterTitle: "第一章",
    chapterContent: "",
    outlineSummary: "",
    outlineNodes: [],
    plotProgress: { currentStage: "未设置" },
    storyBackground: "",
    worldSetting: "",
    writingBible: null,
    storyProgress: "",
    characters: [],
    items: [],
    locations: [],
    factions: [],
    glossaries: [],
    foreshadowings: [],
    references: [],
    styleProfile: "",
    ...overrides,
  };
}

describe("artifact diff", () => {
  it("uses existing character fields as old values for update diffs", () => {
    const novelData = makeNovelData({
      characters: [{
        id: "character-1",
        name: "纪寻",
        personality: "旧性格",
        coreDesire: "旧目标",
        currentStatus: "active",
      }],
    });

    const diffs = buildUpdateDiffs({
      characters: [{
        action: "update",
        id: "character-1",
        name: "纪寻",
        personality: "新性格",
        coreDesire: "新目标",
      }],
    }, novelData);

    assert.equal(diffs[0].action, "update");
    assert.deepEqual(
      diffs[0].fields.map((field) => [field.field, field.oldValue, field.newValue]),
      [
        ["personality", "旧性格", "新性格"],
        ["coreDesire", "旧目标", "新目标"],
      ]
    );
  });

  it("does not treat create diffs as modifications when a same-name entity exists", () => {
    const novelData = makeNovelData({
      characters: [{
        id: "character-1",
        name: "纪寻",
        personality: "旧性格",
        currentStatus: "active",
      }],
    });

    const diffs = buildUpdateDiffs({
      characters: [{
        action: "create",
        name: "纪寻",
        personality: "新角色性格",
      }],
    }, novelData);

    assert.equal(diffs[0].action, "create");
    assert.deepEqual(
      diffs[0].fields.map((field) => [field.field, field.oldValue, field.newValue]),
      [
        ["name", undefined, "纪寻"],
        ["personality", undefined, "新角色性格"],
      ]
    );
  });

  it("matches character experience updates from nested character data", () => {
    const novelData = makeNovelData({
      characters: [{
        id: "character-1",
        name: "纪寻",
        currentStatus: "active",
        experiences: [{
          id: "experience-1",
          characterId: "character-1",
          chapterId: "chapter-1",
          content: "旧经历",
          order: 1,
        }],
      }],
    });

    const diffs = buildUpdateDiffs({
      characterExperiences: [{
        action: "update",
        id: "experience-1",
        characterId: "character-1",
        content: "新经历",
        order: 2,
      }],
    }, novelData);

    assert.deepEqual(
      diffs[0].fields.map((field) => [field.field, field.oldValue, field.newValue]),
      [
        ["content", "旧经历", "新经历"],
        ["order", "1", "2"],
      ]
    );
  });
});

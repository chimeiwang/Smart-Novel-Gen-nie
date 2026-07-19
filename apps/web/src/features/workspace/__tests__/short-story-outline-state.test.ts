import assert from "node:assert/strict";
import test from "node:test";

import {
  appendOutlineItem,
  createEditableOutlineSections,
  moveOutlineItem,
  removeOutlineItem,
  serializeOutlineSections,
  updateOutlineItem,
} from "../short-story/short-story-outline-state";

const sections = [
  { id: "opening", title: "开端", events: "陌生人敲门" },
  { id: "turn", title: "转折", events: "主人公认出暗号" },
  { id: "ending", title: "结局", events: "两人交换身份" },
];

test("按稳定 ID 移动分节而不重建或改写其他节", () => {
  const moved = moveOutlineItem(sections, "turn", "up");

  assert.deepEqual(moved.map((section) => section.id), ["turn", "opening", "ending"]);
  assert.equal(moved[0], sections[1]);
  assert.equal(moved[1], sections[0]);
  assert.equal(moved[2], sections[2]);
  assert.deepEqual(moveOutlineItem(sections, "opening", "up"), sections);
});

test("新增、修改和删除都以稳定 ID 定位，不依赖第 N 节索引", () => {
  const added = appendOutlineItem(sections, () => ({
    id: "afterword",
    title: "余波",
    events: "身份交换留下新的难题",
  }));
  const updated = updateOutlineItem(added, "turn", (section) => ({
    ...section,
    events: "主人公认出暗号，但故意装作不知",
  }));
  const removed = removeOutlineItem(updated, "opening");

  assert.deepEqual(removed.map((section) => section.id), ["turn", "ending", "afterword"]);
  assert.equal(removed[0].events, "主人公认出暗号，但故意装作不知");
  assert.equal(removed[1], sections[2]);
});

test("最后一个分节不能被删除", () => {
  const only = [sections[0]];
  assert.deepEqual(removeOutlineItem(only, "opening"), only);
});

test("新增节使用本地 key，但保存时不把临时 key 当成服务端稳定 ID", () => {
  const editable = createEditableOutlineSections(sections);
  const withNewSection = [
    ...editable,
    {
      key: "client-temp-1",
      persistedId: null,
      title: "余波",
      events: "身份交换留下新的难题",
    },
  ];
  const serialized = serializeOutlineSections(withNewSection);

  assert.equal(editable[0].key, "opening");
  assert.equal(editable[0].persistedId, "opening");
  assert.equal(serialized[0].id, "opening");
  assert.equal(Object.hasOwn(serialized[3], "id"), false);
});

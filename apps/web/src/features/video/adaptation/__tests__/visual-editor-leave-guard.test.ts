import assert from "node:assert/strict";
import { test } from "node:test";

import { registerVisualEditor, visualEditorLeaveState } from "../visual-editor-leave-guard";

test("切换视觉项目只保护视觉输入，关闭整张设定卡同时保护文字草稿", () => {
  const text = registerVisualEditor("text", { novelId: "novel-a", dirty: true, busy: false, scope: "text" });
  const visual = registerVisualEditor("visual", { novelId: "novel-a", dirty: false, busy: false, scope: "visual" });
  try {
    assert.equal(visualEditorLeaveState("novel-a", "visual"), "clear");
    assert.equal(visualEditorLeaveState("novel-a"), "dirty");
    assert.equal(visualEditorLeaveState("novel-b"), "clear");
  } finally { text(); visual(); }
  assert.equal(visualEditorLeaveState("novel-a"), "clear");
});

test("保存中的编辑器优先阻止卸载，其他窗口的干净编辑器不解除保护", () => {
  const clean = registerVisualEditor("clean", { novelId: "novel", dirty: false, busy: false });
  const saving = registerVisualEditor("saving", { novelId: "novel", dirty: true, busy: true });
  const references = registerVisualEditor("references", { novelId: "novel", dirty: true, busy: false, scope: "references" });
  try {
    assert.equal(visualEditorLeaveState("novel"), "busy");
    assert.equal(visualEditorLeaveState("novel", "references"), "dirty");
    saving();
    assert.equal(visualEditorLeaveState("novel"), "dirty");
    references();
    assert.equal(visualEditorLeaveState("novel"), "clear");
  } finally { clean(); saving(); references(); }
});

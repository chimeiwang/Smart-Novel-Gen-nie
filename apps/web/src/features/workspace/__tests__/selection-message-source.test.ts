import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("历史用户消息读取选区来源快照而不是把选区正文作为上下文", async () => {
  const source = await readFile(new URL("../../writing/writing-conversation.tsx", import.meta.url), "utf8");
  assert.match(source, /selectionPreview: selectionPreview\(attachment\.selectedText\)/);
  assert.match(source, /getSelectionMessageSource\(msg\.metadata\)/);
  assert.match(source, /selection-message-source/);
  assert.match(source, /selectionSource\.selectionPreview/);
});

test("选区异步捕获在清理后不能复活，重新选择有明确来源提示", async () => {
  const source = await readFile(new URL("../workspace-shell.tsx", import.meta.url), "utf8");
  assert.match(source, /selectionGenerationRef/);
  assert.match(source, /selectionGenerationRef\.current !== generation/);
  assert.match(source, /onClick=\{clearTransientSelection\}>取消/);
  assert.doesNotMatch(source, /onClick=\{\(\) => setTransientSelection\(null\)\}>取消/);
  assert.match(source, /已移除，请在来源处重新选择/);
  assert.doesNotMatch(source, /isSelectionAttachmentStale\(attachment, input\)/);
});

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

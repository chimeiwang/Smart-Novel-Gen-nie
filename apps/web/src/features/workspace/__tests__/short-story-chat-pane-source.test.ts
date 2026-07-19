import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const componentUrl = new URL(
  "../short-story/short-story-chat-pane.tsx",
  import.meta.url,
);

test("中短篇右栏只承载可新建和续接的会话", async () => {
  const source = await readFile(componentUrl, "utf8");

  assert.match(source, /历史对话/);
  assert.match(source, /开始新对话/);
  assert.match(source, /writing\/sessions/);
  assert.match(source, /versionReferences/);
  assert.doesNotMatch(source, /作品信息/);
  assert.doesNotMatch(source, /版本历史/);
  assert.doesNotMatch(source, /编辑审核/);
});


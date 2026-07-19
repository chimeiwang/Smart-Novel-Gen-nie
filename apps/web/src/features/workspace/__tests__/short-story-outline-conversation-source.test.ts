import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("改纲对话组件呈现用户原话、版本结果和连续修改入口", async () => {
  const componentUrl = new URL(
    "../short-story/short-story-outline-conversation.tsx",
    import.meta.url,
  );
  const source = await readFile(componentUrl, "utf8");

  assert.match(source, /改纲对话/);
  assert.match(source, /你的修改要求/);
  assert.match(source, /完整大纲结果/);
  assert.match(source, /发送修改要求/);
  assert.match(source, /onSelectRevision/);
  assert.match(source, /readOnlyReason/);
  assert.match(source, /尚未提出修改要求/);
});

test("改纲对话组件把最新消息滚动到可见区域", async () => {
  const componentUrl = new URL(
    "../short-story/short-story-outline-conversation.tsx",
    import.meta.url,
  );
  const source = await readFile(componentUrl, "utf8");

  assert.match(source, /scrollIntoView/);
  assert.match(source, /entries\.length/);
});

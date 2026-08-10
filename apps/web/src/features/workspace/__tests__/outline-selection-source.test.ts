import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("总纲选区附件使用 Outline.id 作为 resourceId", async () => {
  const source = await readFile(new URL("../../outline/outline-panel.tsx", import.meta.url), "utf8");
  assert.match(source, /onSelect=\{\(event\) => \{[\s\S]{0,500}resourceType: "outline_content"[\s\S]{0,180}resourceId: outline!?\.id/);
  assert.doesNotMatch(source, /onSelect=\{\(event\) => \{[\s\S]{0,500}resourceType: "outline_content"[\s\S]{0,180}resourceId: novelId/);
});

test("切换节点或新建节点会清理未附加选区", async () => {
  const source = await readFile(new URL("../../outline/outline-panel.tsx", import.meta.url), "utf8");
  assert.match(source, /const handleSelectNode[\s\S]{0,180}clearTransientSelection\(\)/);
  assert.match(source, /const handleNewNode[\s\S]{0,180}clearTransientSelection\(\)/);
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("工作区外壳常驻挂载三类主要面板", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = await readFile(shellUrl, "utf8");

  assert.match(source, /"AI 创作"/);
  assert.match(source, /"阅读与小修"/);
  assert.match(source, /"创作资料"/);
  assert.match(source, /history\.replaceState/);
  assert.match(source, /<SmartWritingPanel/);
  assert.match(source, /<ChapterEditor/);
  assert.match(source, /<SidebarTabs/);
  assert.match(source, /hidden=\{activeView !== "library"\}/);
  assert.doesNotMatch(source, /key=\{activeView\}/);
});

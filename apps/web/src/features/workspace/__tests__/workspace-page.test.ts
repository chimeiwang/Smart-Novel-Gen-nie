import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("工作区 SSR 只请求轻量 bootstrap", async () => {
  const pageUrl = new URL("../../../app/workspace/[novelId]/page.tsx", import.meta.url);
  const source = await readFile(pageUrl, "utf8");

  assert.match(source, /\/workspace\/bootstrap/);
  assert.doesNotMatch(source, /"\/api\/v1\/novels\/\{novel_id\}\/workspace"/);
  assert.doesNotMatch(source, /workspace\.(characters|items|outlineNodes|references|styles)/);
});

test("工作区页面解析视图并委托给客户端外壳", async () => {
  const pageUrl = new URL("../../../app/workspace/[novelId]/page.tsx", import.meta.url);
  const source = await readFile(pageUrl, "utf8");

  assert.match(source, /import \{ WorkspaceShell \}/);
  assert.match(source, /parseWorkspaceView\(view\)/);
  assert.match(source, /<WorkspaceShell/);
  assert.match(source, /bootstrap=\{workspace\}/);
  assert.match(source, /currentUser=\{currentUser\}/);
  assert.doesNotMatch(source, /<ChapterEditor/);
  assert.doesNotMatch(source, /<SmartWritingPanel/);
  assert.doesNotMatch(source, /<SidebarTabs/);
});

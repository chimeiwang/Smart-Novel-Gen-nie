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
  assert.match(source, /workspace-editor-pane" hidden=\{activeView !== "reading"\}/);
  assert.doesNotMatch(source, /key=\{activeView\}/);
});

test("工作区外壳跟随服务端视图和浏览器历史", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = await readFile(shellUrl, "utf8");

  assert.match(source, /useEffect\([\s\S]*initialView/);
  assert.match(source, /addEventListener\("popstate"/);
  assert.match(source, /removeEventListener\("popstate"/);
  assert.match(source, /parseWorkspaceViewFromSearch\(window\.location\.search\)/);
  assert.match(source, /const handlePopState = async \(\) => \{[\s\S]*commitWorkspaceViewChange/);
  assert.match(source, /activeViewRef/);
  assert.match(source, /popstateTransitionRef/);
  assert.match(source, /catch \(error\) \{[\s\S]*history\.replaceState/);
});

test("studio 使用单一宽主画布，窄桌面可滚动降级", async () => {
  const cssUrl = new URL("../../../app/globals.css", import.meta.url);
  const source = await readFile(cssUrl, "utf8");

  assert.doesNotMatch(source, /workspace-shell-main\[data-view="studio"\][\s\S]{0,160}1\.05fr/);
  assert.match(source, /@media \(max-width: 999px\)/);
  assert.match(source, /workspace-page[\s\S]{0,100}overflow: auto/);
});

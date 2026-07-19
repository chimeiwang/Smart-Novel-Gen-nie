import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("中短篇三栏由第三方分栏组件提供拖动与最大宽度约束", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const layoutUrl = new URL("../short-story/short-story-resizable-layout.tsx", import.meta.url);
  const cssUrl = new URL("../short-story/short-story-workspace.css", import.meta.url);
  const [workspace, layout, css] = await Promise.all([
    readFile(workspaceUrl, "utf8"),
    readFile(layoutUrl, "utf8").catch(() => ""),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(workspace, /<ShortStoryResizableLayout[\s\S]*novelId=\{novel\.id\}/);
  assert.match(layout, /from "react-resizable-panels"/);
  assert.match(layout, /<Group[\s\S]*orientation="horizontal"[\s\S]*onLayoutChanged=/);
  assert.match(layout, /if \(!meta\.isUserInteraction\) return/);
  assert.match(layout, /SHORT_STORY_PANEL_CONSTRAINTS\.workflow\.maxSize/);
  assert.match(layout, /SHORT_STORY_PANEL_CONSTRAINTS\.chat\.maxSize/);
  assert.match(layout, /panels\.at\(-1\)/);
  assert.match(layout, /<Separator[^>]*className="short-story-panel-separator"/);
  assert.doesNotMatch(layout, /onPointer|onMouse|addEventListener/);
  assert.doesNotMatch(css, /\.short-story-grid\s*\{[^}]*grid-template-columns/);
});

test("隐藏的旧操作区不能被 panel 的 flex 样式重新显示", async () => {
  const cssUrl = new URL("../short-story/short-story-workspace.css", import.meta.url);
  const css = await readFile(cssUrl, "utf8");

  assert.match(
    css,
    /\.short-story-review-rail\[hidden\]\s*{\s*display:\s*none;/,
  );
});

test("中短篇新对话输入区保持紧凑，只有消息区占用剩余高度", async () => {
  const chatUrl = new URL("../short-story/short-story-chat-pane.tsx", import.meta.url);
  const cssUrl = new URL("../short-story/short-story-workspace.css", import.meta.url);
  const [chat, css] = await Promise.all([
    readFile(chatUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(
    css,
    /\.short-story-chat-pane\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;/,
  );
  assert.doesNotMatch(css, /\.short-story-chat-pane\s*\{[^}]*grid-template-rows/);
  assert.match(css, /\.short-story-chat-messages\s*\{[^}]*flex:\s*1;[^}]*min-height:\s*0;/);
  assert.match(chat, /className="short-story-chat-actions"[\s\S]*className="button primary"/);
  assert.match(css, /\.short-story-chat-actions\s*\{[^}]*justify-content:\s*flex-end;/);
});

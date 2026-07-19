import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("中短篇三栏在常见桌面宽度保持同一行", async () => {
  const cssUrl = new URL("../short-story/short-story-workspace.css", import.meta.url);
  const css = await readFile(cssUrl, "utf8");

  assert.match(
    css,
    /@media \(max-width: 1439px\)[\s\S]*?grid-template-columns:\s*220px minmax\(0, 1fr\) 340px/,
  );
  assert.doesNotMatch(
    css,
    /@media \(max-width: 1439px\)[\s\S]*?\.short-story-grid[\s\S]*?overflow-x:\s*auto/,
  );
});

test("隐藏的旧操作区不能被 panel 的 flex 样式重新显示", async () => {
  const cssUrl = new URL("../short-story/short-story-workspace.css", import.meta.url);
  const css = await readFile(cssUrl, "utf8");

  assert.match(
    css,
    /\.short-story-review-rail\[hidden\]\s*{\s*display:\s*none;/,
  );
});

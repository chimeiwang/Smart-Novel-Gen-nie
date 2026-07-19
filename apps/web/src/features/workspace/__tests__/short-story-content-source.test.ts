import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("中短篇正文完整渲染且画布可滚动到底部", async () => {
  const componentUrl = new URL("../short-story/short-story-content.tsx", import.meta.url);
  const cssUrl = new URL("../short-story/short-story-workspace.css", import.meta.url);
  const [componentSource, cssSource] = await Promise.all([
    readFile(componentUrl, "utf8"),
    readFile(cssUrl, "utf8"),
  ]);

  assert.match(componentSource, /\{content\}/);
  assert.doesNotMatch(componentSource, /slice\(|substring\(|line-clamp|WebkitLineClamp/);
  assert.match(cssSource, /\.short-story-content[\s\S]{0,240}white-space:\s*pre-wrap/);
  assert.match(cssSource, /\.short-story-main-canvas[\s\S]{0,240}overflow:\s*auto/);
});

test("大纲编辑模型没有固定节数和分节字数", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const outlineStateUrl = new URL("../short-story/short-story-outline-state.ts", import.meta.url);
  const source = `${await readFile(workspaceUrl, "utf8")}\n${await readFile(outlineStateUrl, "utf8")}`;

  assert.doesNotMatch(source, /sectionWordCount|estimatedWords|fixedSection|固定节数|每节字数/);
});

test("中短篇草稿与正式正文统一使用前端字数统计函数", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /import \{ countTextLength \} from "@\/shared\/lib\/word-count"/);
  assert.match(source, /countTextLength\(draftPayload\?\.content \?\? ""\)/);
  assert.match(source, /countTextLength\(currentChapter\?\.content \?\? ""\)/);
  assert.doesNotMatch(source, /实际 \{draftPayload\.metadata\.actualWordCount\} 字/);
});

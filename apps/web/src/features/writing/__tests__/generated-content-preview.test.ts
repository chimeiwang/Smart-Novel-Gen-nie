import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const PREVIEW_SELECTOR = ".writing-chat .preview-content";

function extractGeneratedContentPreview(source: string): string {
  return source.match(
    /\{generatedContent\s*&&\s*\(\s*(<div className="preview-section">[\s\S]*?<\/div>)\s*\)\}\s*\{chapterTargetPrompt\s*\?\s*\(/,
  )?.[1] ?? "";
}

function findCssRuleBodies(source: string, selector: string): string[] {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rulePattern = new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`, "g");

  return Array.from(source.matchAll(rulePattern), (match) => match[1]);
}

test("正文预览直接渲染并统计完整 generatedContent", async () => {
  const source = await readFile(new URL("../writing-conversation.tsx", import.meta.url), "utf8");
  const previewSection = extractGeneratedContentPreview(source);

  assert.notEqual(previewSection, "", "未提取到 generatedContent 正文预览块");
  assert.match(previewSection, /<ParagraphText\s+text=\{generatedContent\}\s*\/>/);
  assert.match(previewSection, /countTextLength\(generatedContent\)/);
});

for (const [name, path] of [
  ["会话样式", "../writing-conversation.css"],
  ["全局样式", "../../../app/globals.css"],
] as const) {
  test(`${name}允许滚动查看完整正文预览`, async () => {
    const source = await readFile(new URL(path, import.meta.url), "utf8");
    const previewRules = findCssRuleBodies(source, PREVIEW_SELECTOR);

    assert.ok(previewRules.length > 0, `${name}缺少正文预览样式块`);
    for (const rule of previewRules) {
      assert.match(rule, /max-height:\s*min\(56vh,\s*640px\)/);
      assert.match(rule, /overflow-y:\s*auto/);
      assert.doesNotMatch(rule, /max-height:\s*150px/);
      assert.doesNotMatch(rule, /overflow:\s*hidden/);
    }
    assert.doesNotMatch(source, /\.writing-chat\s+\.preview-content::after\s*\{/);
  });
}

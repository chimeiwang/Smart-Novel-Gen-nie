import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const PREVIEW_SELECTOR = ".writing-chat .preview-content";
const PREVIEW_MASK_SELECTOR = ".writing-chat .preview-content::after";

function findCssRuleBodies(source: string, selector: string): string[] {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const rulePattern = new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`, "g");

  return Array.from(source.matchAll(rulePattern), (match) => match[1]);
}

test("正文预览直接渲染并统计完整 generatedContent", async () => {
  const source = await readFile(new URL("../writing-conversation.tsx", import.meta.url), "utf8");

  assert.match(source, /<ParagraphText\s+text=\{generatedContent\}\s*\/>/);
  assert.match(source, /countTextLength\(generatedContent\)/);
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
      assert.doesNotMatch(rule, /overflow:\s*hidden/);
    }
    assert.equal(findCssRuleBodies(source, PREVIEW_MASK_SELECTOR).length, 0);
  });
}

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("章节编辑器按质量展示 helper 判定已处理和无效结果", async () => {
  const editorUrl = new URL("../chapter-editor.tsx", import.meta.url);
  const source = await readFile(editorUrl, "utf8");

  assert.match(source, /from "\.\/quality-presentation"/);
  assert.match(source, /isHandledQualityCheck\(check\)/);
  assert.match(source, /getQualityCheckPresentationState\(check\)/);
  assert.match(source, /结果无效/);
  assert.doesNotMatch(
    source,
    /check\.status === "completed" \|\| check\.status === "skipped"/,
  );
});

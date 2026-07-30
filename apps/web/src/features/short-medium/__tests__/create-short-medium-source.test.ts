import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("中短篇创建表单提交素材类型、完整素材和稳定请求标识", async () => {
  const source = await readFile(
    new URL("../../projects/create-novel-modal.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /sourceKind/);
  assert.match(source, /sourceText/);
  assert.match(source, /clientRequestId/);
  assert.match(source, /灵感/);
  assert.match(source, /开头/);
  assert.match(source, /结尾/);
  assert.match(source, /简略大纲/);
});

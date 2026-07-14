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

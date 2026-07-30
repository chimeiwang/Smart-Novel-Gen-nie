import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("版本抽屉展示完整 Diff，不做固定条数或字符串截断", async () => {
  const source = await readFile(
    new URL("../short-version-drawer.tsx", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(source, /\.slice\(/);
  assert.doesNotMatch(source, /\.substring\(/);
  assert.doesNotMatch(source, /\.substr\(/);
  assert.match(source, /diff\.blocks\.map/);
  assert.match(source, /block\.oldText/);
  assert.match(source, /block\.newText/);
});

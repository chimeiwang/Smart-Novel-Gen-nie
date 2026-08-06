import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("章节进展保存使用进展自身版本并接收服务端新版本", async () => {
  const editorUrl = new URL("../chapter-editor.tsx", import.meta.url);
  const source = await readFile(editorUrl, "utf8");

  assert.match(source, /chapterProgress:\s*\{[\s\S]{0,100}content:\s*string;[\s\S]{0,100}updatedAt:\s*string;[\s\S]{0,50}\}\s*\|\s*null/);
  assert.match(source, /useState\(\s*chapterProgress\?\.updatedAt\s*\?\?\s*null/);
  assert.match(source, /body:\s*\{\s*content:\s*progressContent,\s*expectedUpdatedAt:\s*progressUpdatedAt\s*\}/);
  assert.match(source, /setProgressUpdatedAt\(response\.updatedAt\)/);
});

test("质量运行复用未确认请求号且状态更新携带检查版本", async () => {
  const editorUrl = new URL("../chapter-editor.tsx", import.meta.url);
  const source = await readFile(editorUrl, "utf8");

  assert.match(source, /qualityRunClientRequestIdsRef\s*=\s*useRef<Record<string,\s*string>>/);
  assert.match(source, /qualityRunClientRequestIdsRef\.current\[check\.id\]\s*\?\?\s*createClientRequestId\(\)/);
  assert.match(source, /body:\s*\{\s*clientRequestId\s*\}/);
  assert.match(source, /body:\s*\{\s*status,\s*resetResult:\s*status\s*===\s*"pending",\s*expectedUpdatedAt:\s*check\.updatedAt\s*\}/);
});

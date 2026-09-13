import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../writing-conversation.tsx", import.meta.url), "utf8");

test("兼容回退的普通新任务发送旧图输入，不能调用已关闭的耐久自然入口", () => {
  const start = source.slice(source.indexOf("const startDiscussionInternal ="), source.indexOf("const handleStartDiscussion ="));
  assert.match(start, /selectedAgents,/);
  assert.match(start, /userMessage,/);
  assert.match(start, /clientRequestId: createClientRequestId\(\)/);
  assert.match(start, /buildSelectionRunRequest/);
  assert.doesNotMatch(start, /buildNaturalRunRequest|inputMode: "natural"/);
});

test("旧图回退仍通过草案决定与权威任务回读，不直接写正文或大纲", () => {
  assert.match(source, /handleArtifactDecision/);
  assert.match(source, /expectedRevision/);
  assert.match(source, /\/api\/v1\/writing\/runs/);
  assert.match(source, /\/api\/v1\/review-artifacts/);
  assert.doesNotMatch(source, /browserApi\.(?:PUT|PATCH)\("\/api\/v1\/(?:chapters|outlines)/);
});

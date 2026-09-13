import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("草案三种决策都携带当前修订号", async () => {
  const conversationUrl = new URL("../writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(
    source,
    /body:\s*\{[\s\S]{0,180}clientRequestId:\s*createClientRequestId\(\),[\s\S]{0,100}expectedRevision:\s*artifact\.revision,[\s\S]{0,100}decision,/,
  );
  assert.match(source, /handleArtifactDecision\(\s*artifact,\s*"approve"/);
  assert.match(source, /handleArtifactDecision\(artifact,\s*"revise"/);
  assert.match(source, /handleArtifactDecision\(artifact,\s*"discard"/);
});

test("V1 草案决定显式声明引擎，V2 候选不会偷偷走 V1", async () => {
  const conversationUrl = new URL("../writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /type ReviewArtifactData\s*=\s*\{[\s\S]{0,100}engineVersion:\s*1\s*\|\s*2/);
  assert.match(source, /engineVersion:\s*artifact\.engineVersion/);
  assert.match(source, /resolveReviewArtifactActionTaskId\([\s\S]{0,220}artifact/);
  assert.match(source, /if \(artifact\.engineVersion !== 1\)/);
  assert.match(source, /当前兼容页面不能继续，请开始新对话/);
  assert.match(source, /accepted\.engineVersion !== 1/);
  assert.doesNotMatch(source, /createWorkflowRunUiState|processStream\(next\.runId/);
});

test("V1 结构化候选仍展示完整大纲差异并要求审核决定", async () => {
  const source = await readFile(new URL("../writing-conversation.tsx", import.meta.url), "utf8");
  assert.match(source, /artifact\.payload\.updates\.outline\?\.length/);
  assert.match(source, /artifact\.payload\.updates\.outlineAdjustments\?\.length/);
  assert.match(source, /renderUpdatesPreviewCard\(\{ \.\.\.\(artifact\.payload\?\.updates \?\? \{\}\)/);
  assert.match(source, /expectedRevision:\s*artifact\.revision/);
});

test("V1 草案托盘按会话任务读取完整详情并按版本合并", async () => {
  const conversationUrl = new URL("../writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /"\/api\/v1\/writing\/tasks\/\{task_id\}\/artifact"/);
  assert.match(source, /Promise\.allSettled\(taskIds\.map/);
  assert.match(source, /mergeActionableReviewArtifacts/);
  assert.match(source, /artifactTrayArtifacts\.map/);
});

test("V1 全文编辑与选区替换字段互斥", async () => {
  const source = await readFile(new URL("../writing-conversation.tsx", import.meta.url), "utf8");
  assert.match(source, /editedContent:\s*decision\s*===\s*"approve"\s*&&\s*!selectionArtifact/);
  assert.match(source, /editedReplacement:\s*decision\s*===\s*"approve"\s*&&\s*selectionArtifact/);
  assert.match(source, /readOnly=\{!awaitingUser\s*\|\|\s*actionLocked\}/);
  assert.match(source, /if \(artifact\.engineVersion !== 1\)/);
});

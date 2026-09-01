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

test("V2 草案决定显式声明引擎并继续观察同一个 Run", async () => {
  const conversationUrl = new URL("../writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /type ReviewArtifactData\s*=\s*\{[\s\S]{0,100}engineVersion:\s*1\s*\|\s*2/);
  assert.match(source, /engineVersion:\s*artifact\.engineVersion/);
  assert.match(source, /resolveReviewArtifactActionTaskId\([\s\S]{0,120}artifact,/);
  assert.doesNotMatch(source, /engineVersion:\s*isV2Artifact\s*\?/);
  assert.match(source, /accepted\.engineVersion\s*===\s*2/);
  assert.match(source, /createWorkflowRunUiState\(accepted\)/);
  assert.match(source, /processStream\(next\.runId,\s*streamScope\)/);
  assert.match(
    source,
    /selectedUpdateRefs:\s*!isV2Artifact\s*&&\s*decision\s*===\s*"approve"/,
  );
});

test("草案列表只承载摘要且详情按精确 revision 去重缓存", async () => {
  const conversationUrl = new URL("../writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /query:\s*\{\s*revision\s*\}/);
  assert.match(source, /"If-None-Match":\s*cached\.etag/);
  assert.match(source, /result\.response\.status\s*===\s*304/);
  assert.match(source, /reviewArtifactDetailRequestsRef\.current\.get\(cacheKey\)/);
  assert.match(source, /result\.response\.status\s*===\s*403\s*\|\|\s*result\.response\.status\s*===\s*404/);
  assert.match(source, /detailLoaded:\s*false/);
  assert.match(source, /detailLoaded:\s*true/);
});

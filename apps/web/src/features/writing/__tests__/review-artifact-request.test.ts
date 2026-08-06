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

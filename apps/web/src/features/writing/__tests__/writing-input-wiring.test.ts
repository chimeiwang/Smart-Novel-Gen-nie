import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../writing-conversation.tsx", import.meta.url), "utf8");

test("普通发送使用三分流，普通新消息不得落入旧 resume", () => {
  const send = source.slice(source.indexOf("const handleSendMessage ="), source.indexOf("const openArtifactTray ="));
  assert.match(send, /writingInputDisposition/);
  assert.match(send, /buildClarificationRequest/);
  assert.match(send, /\/clarification/);
  assert.match(send, /handleArtifactDecision/);
  assert.match(send, /startDiscussionInternal/);
  assert.doesNotMatch(send, /\/resume/);
  assert.doesNotMatch(send, /\.trim\(\)/);
  const start = source.slice(source.indexOf("const startDiscussionInternal ="), source.indexOf("const handleStartDiscussion ="));
  assert.match(start, /buildNaturalRunRequest/);
  assert.doesNotMatch(start, /selectedAgents,/);
});

test("澄清与明确草案返工可输入，未知完成事件沿既有监控回读", () => {
  assert.match(source, /workflowEventRequiresSnapshotRefresh\(workflowRunRef\.current, event\)/);
  assert.match(source, /requiresSnapshotRead \|\| workflowRunShouldStopObservation/);
  assert.match(source, /inputDisposition === "blocked"/);
  assert.match(source, /workflowRun\.clarification\.prompt/);
  assert.match(source, /setRevisionArtifact\(artifact\)/);
  assert.match(source, /继续旧任务/);
});

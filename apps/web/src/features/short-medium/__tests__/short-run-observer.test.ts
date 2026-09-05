import assert from "node:assert/strict";
import { it } from "node:test";
import type { components } from "@inkforge/api-client";

import { observeShortV2Run } from "../short-run-observer";

type V2Run = components["schemas"]["WritingRunV2Response"];
const initial: V2Run = {
  engineVersion: 2, runId: "short-run-1", taskId: "short-run-1", workflow: "short_medium",
  chapterId: null, commandId: null, commandStatus: null, operation: "generate_outline",
  status: "pending", activeSteps: [], lastEventSequence: 1, revision: 1,
};
const completed: V2Run = {
  ...initial, status: "completed", lastEventSequence: 8, revision: 3, candidateVersionId: "real-candidate",
  artifact: { artifactId: "real-candidate", artifactRevision: 1, status: "awaiting_user", actionable: false },
};
function stream(complete = true): Response {
  const snapshot = {
    protocolVersion: "2.0", engineVersion: 2, runId: initial.runId, baseSequence: 7,
    snapshot: { workflow: "short_medium", operation: "generate_outline", status: "running", activeSteps: [],
      lastEventSequence: 7, revision: 2, artifact: null, error: null, currentStep: null, cancelRequestedAt: null },
  };
  const event = { protocolVersion: "2.0", engineVersion: 2, runId: initial.runId, sequence: 8,
    eventType: "completed", occurredAt: "2026-09-05T08:00:00Z", payload: { outcomeType: "short_candidate", resultId: "event-only-id" } };
  return new Response(`event: run_snapshot\ndata: ${JSON.stringify(snapshot)}\n\n`
    + (complete ? `id: 8\nevent: completed\ndata: ${JSON.stringify(event)}\n\n` : ""));
}

it("V2完成事件只触发精确GET，不把事件中的ID当候选", async () => {
  let reads = 0;
  const result = await observeShortV2Run(initial, {
    open: async () => stream(), readRun: async () => { reads++; return completed; },
    signal: new AbortController().signal,
  });
  assert.equal(reads, 1);
  assert.equal(result.engineVersion, 2);
  if (result.engineVersion === 2) assert.equal(result.candidateVersionId, "real-candidate");
});

it("断线保留snapshot数字游标，重新连接后仍回读权威终态", async () => {
  const headers: Headers[] = [];
  let reads = 0;
  const result = await observeShortV2Run(initial, {
    open: async (value) => { headers.push(new Headers(value)); return stream(headers.length > 1); },
    readRun: async () => ++reads === 1 ? { ...initial, status: "running" } : completed,
    wait: async () => {}, signal: new AbortController().signal,
  });
  assert.equal(headers.length, 2);
  assert.equal(headers[0].get("Last-Event-ID"), null);
  assert.equal(headers[1].get("Last-Event-ID"), "7");
  assert.equal(result.engineVersion, 2);
  if (result.engineVersion === 2) assert.equal(result.status, "completed");
});

it("引擎或Run身份变化时不能展示结果，也不发送取消请求", async () => {
  await assert.rejects(observeShortV2Run(initial, {
    open: async () => stream(), readRun: async () => ({ ...completed, runId: "wrong-run" }),
    signal: new AbortController().signal,
  }), /身份发生变化/);
});

it("已完成的启动重放仍GET精确结果而不重复打开事件流", async () => {
  const result = await observeShortV2Run(completed, {
    open: async () => { throw new Error("不应重新打开事件流"); }, readRun: async () => completed,
    signal: new AbortController().signal,
  });
  assert.equal(result, completed);
});

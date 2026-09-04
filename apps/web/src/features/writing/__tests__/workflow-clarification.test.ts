import assert from "node:assert/strict";
import test from "node:test";

import { parseSseEvent, WorkflowRunSnapshotSchema } from "@/shared/contracts/sse-events";
import { applyWorkflowStreamEvent, createWorkflowRunUiState, workflowEventRequiresSnapshotRefresh, workflowRunStatusTitle, type WorkflowRunV2Response } from "../workflow-run-ui";

function snapshot() {
  return {
    workflow: "long_serial", operation: null, status: "waiting_user" as const,
    activeSteps: [], currentStep: null, lastEventSequence: 4, revision: 3, artifact: null, error: null,
    clarification: { clarificationCode: "uncertain", prompt: "  规划还是正文？\r\n  ", decisionStepId: "decision-1" },
  };
}

test("澄清snapshot保留完整问题并可从刷新恢复，旧省略字段仍合法", () => {
  const value = snapshot();
  assert.deepEqual(WorkflowRunSnapshotSchema.parse(value).clarification, value.clarification);
  const { clarification: omitted, ...legacy } = value;
  assert.ok(omitted);
  assert.equal(WorkflowRunSnapshotSchema.safeParse(legacy).success, true);
  const state = createWorkflowRunUiState({ ...value, engineVersion: 2, runId: "run-1", taskId: "run-1", chapterId: "c1", commandId: null, commandStatus: null });
  assert.equal(state.clarification?.prompt, value.clarification.prompt);
  assert.equal(workflowRunStatusTitle(state), "需要你补充信息");
});

test("问题按Unicode码点限制且不去空格换行，不允许草案与澄清并存", () => {
  for (const prompt of ["😀".repeat(2000), "  问题\r\n  ", "\u001c"]) {
    const value = snapshot();
    value.clarification.prompt = prompt;
    assert.equal(WorkflowRunSnapshotSchema.parse(value).clarification?.prompt, prompt);
  }
  for (const changed of [
    { status: "running" },
    { artifact: { artifactId: "a1", artifactRevision: 1, status: "draft", actionable: false } },
    { clarification: { ...snapshot().clarification, prompt: " \ufeff\u0085" } },
    { clarification: { ...snapshot().clarification, prompt: "😀".repeat(2001) } },
  ]) assert.equal(WorkflowRunSnapshotSchema.safeParse({ ...snapshot(), ...changed }).success, false);
});

test("未知完成控制Step要求回读，不能盲清问题或制造Artifact", () => {
  const state = createWorkflowRunUiState({ ...snapshot(), engineVersion: 2, runId: "run-1", taskId: "run-1", chapterId: "c1", commandId: null, commandStatus: null });
  const event = parseSseEvent({
    type: "workflow_event", protocolVersion: "2.0", engineVersion: 2,
    runId: "run-1", sequence: 5, occurredAt: "2026-09-04T08:00:00Z", eventType: "step_finished",
    payload: { stepId: "answer-1", fencingToken: 1, status: "completed", errorCode: null },
  });
  assert.ok(event && event.type === "workflow_event");
  assert.equal(workflowEventRequiresSnapshotRefresh(state, event), true);
  const observed = applyWorkflowStreamEvent(state, event)!;
  assert.equal(observed.status, "waiting_user");
  assert.deepEqual(observed.clarification, state.clarification);
  assert.equal(observed.artifact, null);
  const authoritative: WorkflowRunV2Response = { ...snapshot(), engineVersion: 2, runId: "run-1", taskId: "run-1", chapterId: "c1", commandId: null, commandStatus: null, status: "running", clarification: null, revision: 4, lastEventSequence: 6 };
  assert.equal(createWorkflowRunUiState(authoritative).clarification, null);
});

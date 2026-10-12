import assert from "node:assert/strict";
import test from "node:test";

import { buildClarificationRequest, buildNaturalRunRequest, writingInputDisposition } from "../writing-input";
import { createWorkflowRunUiState, type WorkflowRunV2Response } from "../workflow-run-ui";

function waiting(): WorkflowRunV2Response {
  return {
    engineVersion: 2, runId: "run-1", taskId: "run-1", chapterId: "chapter-1",
    workflow: "long_serial", operation: null, status: "waiting_user", activeSteps: [], currentStep: null,
    lastEventSequence: 4, revision: 3, artifact: null, error: null, commandId: null, commandStatus: null,
    clarification: { clarificationCode: "uncertain", prompt: "  规划还是正文？\r\n  ", decisionStepId: "decision-1" },
  };
}

test("普通新消息不因遗留taskId恢复旧Run，且构造闭合自然请求", () => {
  assert.equal(writingInputDisposition({ run: null, legacyTaskId: "legacy-task" }), "new_run");
  const base = { novelId: "n1", chapterId: "c1", writingSessionId: "s1", targetWordCount: 4000, userInstruction: "  完整要求\r\n  " };
  const first = buildNaturalRunRequest({ ...base, clientRequestId: "new-message-00001" });
  const next = buildNaturalRunRequest({ ...base, clientRequestId: "new-message-00002" });
  assert.equal(first.inputMode, "natural");
  assert.equal(first.workflow, "long_serial");
  assert.equal(first.userInstruction, base.userInstruction);
  assert.notEqual(first.clientRequestId, next.clientRequestId);
  assert.equal("selectedAgents" in first, false);
  assert.equal("operation" in first, false);
});

test("澄清只绑定当前同Run问题与revision，不是新建或Artifact返工", () => {
  const run = createWorkflowRunUiState(waiting());
  assert.equal(writingInputDisposition({ run }), "clarification");
  assert.deepEqual(buildClarificationRequest(run, "  只问答。\r\n  ", "clarify-request-0001"), {
    clientRequestId: "clarify-request-0001", expectedRevision: 3,
    decisionStepId: "decision-1", userMessage: "  只问答。\r\n  ",
  });
  assert.equal(writingInputDisposition({ run, revisionArtifactId: "artifact-1" }), "clarification");
  assert.throws(() => buildClarificationRequest(run, " \ufeff\u0085", "clarify-request-0001"));
});

test("Artifact返工必须显式选择当前候选，不与普通消息混淆", () => {
  const run = createWorkflowRunUiState({ ...waiting(), clarification: null, operation: "write_chapter", artifact: {
    artifactId: "artifact-1", artifactRevision: 1, status: "awaiting_user", actionable: true,
  } });
  assert.equal(writingInputDisposition({ run }), "blocked");
  assert.equal(writingInputDisposition({ run, revisionArtifactId: "other" }), "blocked");
  assert.equal(writingInputDisposition({ run, revisionArtifactId: "artifact-1" }), "artifact_revision");
  assert.throws(() => buildClarificationRequest(run, "继续", "clarify-request-0001"));
});

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { parseSseEvent } from "@/shared/contracts/sse-events";
import {
  applyWorkflowStreamEvent,
  createWorkflowRunUiState,
  selectForegroundWorkflowRun,
  workflowEventRequiresSessionMessageRefresh,
  workflowModelRoleLabel,
  workflowResolvedModelLabel,
  workflowRunShouldStopObservation,
  workflowRunStatusTitle,
  type WorkflowCurrentStep,
  type WorkflowEvent,
  type WorkflowModelProfile,
  type WorkflowResolvedModel,
  type WorkflowRunV2Response,
} from "../workflow-run-ui";

const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);

function modelProfile(profile: string): WorkflowModelProfile {
  const deploymentProfileKey = `deployment.${profile}`;
  return {
    profile,
    version: 1,
    reasoningMode: "bounded",
    deploymentProfileKey,
    promptProfile: {
      name: `prompt.${profile}`,
      version: 1,
      sha256: SHA_A,
    },
  };
}

function resolvedModel(
  profile: WorkflowModelProfile,
  model: string,
  fingerprint = SHA_B,
): WorkflowResolvedModel {
  return {
    deploymentProfileKey: profile.deploymentProfileKey,
    deploymentFingerprint: fingerprint,
    provider: "deepseek",
    model,
    transportProfile: "transport.responses.v1",
    endpointProfile: "endpoint.default.v1",
    structuredOutputRoute: "responses_json_schema_v1",
    capabilityVersion: "capability.structured.v1",
    reasoningMode: profile.reasoningMode,
    supportsRequestIdempotency: true,
  };
}

function activeStep(
  stepId: string,
  ordinal: number,
  profileName: string,
  model: string,
  fencingToken = 1,
  latestProgress: WorkflowCurrentStep["latestProgress"] = null,
): WorkflowCurrentStep {
  const profile = modelProfile(profileName);
  return {
    stepId,
    ordinal,
    purpose: profileName.startsWith("reviewer.") ? "review" : "generation",
    lane: "creative",
    modelProfile: profile,
    resolvedModel: resolvedModel(profile, model),
    status: "running",
    attemptCount: fencingToken,
    fencingToken,
    latestProgress,
    errorCode: null,
  };
}

function pendingRun(activeSteps: WorkflowCurrentStep[] = []): WorkflowRunV2Response {
  return {
    engineVersion: 2,
    runId: "run-1",
    taskId: "run-1",
    workflow: "long_serial",
    operation: "rewrite_chapter_selection",
    status: activeSteps.length > 0 ? "running" : "pending",
    activeSteps,
    currentStep: activeSteps[0] ?? null,
    cancelRequestedAt: null,
    lastEventSequence: 2,
    revision: 1,
    artifact: null,
    error: null,
    chapterId: "chapter-1",
    commandId: null,
    commandStatus: null,
  };
}

function workflowEvent(raw: Record<string, unknown>): WorkflowEvent {
  const event = parseSseEvent(raw);
  if (!event || event.type !== "workflow_event") {
    throw new Error("测试事件不符合 workflow_event 契约");
  }
  return event;
}

function envelope(sequence: number, eventType: string, payload: Record<string, unknown>) {
  return {
    protocolVersion: "2.0",
    engineVersion: 2,
    runId: "run-1",
    sequence,
    eventType,
    occurredAt: "2026-09-01T12:00:00Z",
    payload,
  };
}

test("V2 snapshot 原子重建全部并行步骤并恢复各自 latestProgress", () => {
  const writerProfile = modelProfile("writer.chapter_selection.v1");
  let previous = createWorkflowRunUiState(pendingRun([activeStep(
    "step-generation",
    1,
    "writer.chapter_selection.v1",
    "deepseek-chat",
    1,
  )]));
  previous = applyWorkflowStreamEvent(previous, workflowEvent(envelope(3, "step_progress", {
    stepId: "step-generation",
    fencingToken: 1,
    progressSequence: 1,
    modelProfile: writerProfile,
    resolvedModel: resolvedModel(writerProfile, "deepseek-chat"),
    phase: "waiting_provider",
    elapsedSeconds: 41,
    waitingOnProvider: true,
    usageStatus: "unknown",
  })))!;
  assert.equal(previous.activeSteps[0]?.progress?.elapsedSeconds, 41);

  const consistency = activeStep(
    "step-review-consistency",
    2,
    "reviewer.consistency.v1",
    "deepseek-reasoner",
    1,
    {
      progressSequence: 4,
      phase: "validating",
      elapsedSeconds: 29,
      waitingOnProvider: false,
      usageStatus: "complete",
    },
  );
  const editorial = activeStep(
    "step-review-editorial",
    3,
    "reviewer.editorial.v1",
    "deepseek-chat",
  );
  const event = parseSseEvent({
    protocolVersion: "2.0",
    engineVersion: 2,
    runId: "run-1",
    baseSequence: 7,
    snapshot: {
      workflow: "long_serial",
      operation: "rewrite_chapter_selection",
      status: "running",
      activeSteps: [consistency, editorial],
      currentStep: consistency,
      cancelRequestedAt: null,
      lastEventSequence: 7,
      revision: 3,
      artifact: null,
      error: null,
    },
  }, "run_snapshot");

  assert.equal(event?.type, "run_snapshot");
  if (!event || event.type !== "run_snapshot") return;
  const state = applyWorkflowStreamEvent(previous, event);
  assert.deepEqual(state?.activeSteps.map((step) => step.stepId), [
    "step-review-consistency",
    "step-review-editorial",
  ]);
  assert.equal(state?.activeSteps[0]?.progress?.progressSequence, 4);
  assert.equal(state?.activeSteps[0]?.progress?.elapsedSeconds, 29);
  assert.equal(state?.activeSteps[1]?.progress, null);
  assert.equal(state?.currentStep?.stepId, "step-review-consistency");
  assert.equal(state ? workflowRunStatusTitle(state) : null, "2 个步骤并行执行中");
});

test("并行 Reviewer 按 stepId 与 fencingToken 分别维护 started 和 progress", () => {
  const consistencyProfile = modelProfile("reviewer.consistency.v1");
  const editorialProfile = modelProfile("reviewer.editorial.v1");
  let state = createWorkflowRunUiState(pendingRun());

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(3, "review_started", {
    artifactId: "artifact-1",
    artifactRevision: 1,
    reviewerSteps: [
      {
        stepId: "step-review-consistency",
        ordinal: 2,
        purpose: "review",
        lane: "creative",
        modelProfile: consistencyProfile,
        status: "pending",
        attemptCount: 0,
        fencingToken: 0,
      },
      {
        stepId: "step-review-editorial",
        ordinal: 3,
        purpose: "review",
        lane: "creative",
        modelProfile: editorialProfile,
        status: "pending",
        attemptCount: 0,
        fencingToken: 0,
      },
    ],
  })))!;
  assert.deepEqual(state.activeSteps.map((step) => [
    step.stepId,
    step.status,
    step.fencingToken,
    step.resolvedModel,
  ]), [
    ["step-review-consistency", "pending", 0, null],
    ["step-review-editorial", "pending", 0, null],
  ]);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(4, "step_queued", {
    stepId: "step-review-consistency",
    ordinal: 2,
    purpose: "review",
    lane: "creative",
    modelProfile: consistencyProfile,
    attemptCount: 1,
    fencingToken: 1,
    reason: "initial_dispatch",
  })))!;
  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(5, "step_queued", {
    stepId: "step-review-editorial",
    ordinal: 3,
    purpose: "review",
    lane: "creative",
    modelProfile: editorialProfile,
    attemptCount: 1,
    fencingToken: 1,
    reason: "initial_dispatch",
  })))!;
  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(6, "step_started", {
    stepId: "step-review-consistency",
    ordinal: 2,
    purpose: "review",
    modelProfile: consistencyProfile,
    attemptCount: 1,
    fencingToken: 1,
  })))!;
  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(7, "step_started", {
    stepId: "step-review-editorial",
    ordinal: 3,
    purpose: "review",
    modelProfile: editorialProfile,
    attemptCount: 1,
    fencingToken: 1,
  })))!;
  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(8, "step_progress", {
    stepId: "step-review-editorial",
    fencingToken: 1,
    progressSequence: 1,
    modelProfile: editorialProfile,
    resolvedModel: resolvedModel(editorialProfile, "deepseek-chat"),
    phase: "waiting_provider",
    elapsedSeconds: 17,
    waitingOnProvider: true,
    usageStatus: "unknown",
  })))!;
  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(9, "step_progress", {
    stepId: "step-review-consistency",
    fencingToken: 1,
    progressSequence: 1,
    modelProfile: consistencyProfile,
    resolvedModel: resolvedModel(consistencyProfile, "deepseek-reasoner", SHA_A),
    phase: "validating",
    elapsedSeconds: 29,
    waitingOnProvider: false,
    usageStatus: "complete",
  })))!;

  assert.deepEqual(state.activeSteps.map((step) => [
    workflowModelRoleLabel(step.modelProfile, step.purpose),
    step.progress?.elapsedSeconds,
    step.resolvedModel?.model,
  ]), [
    ["一致性校验", 29, "deepseek-reasoner"],
    ["编辑复审", 17, "deepseek-chat"],
  ]);
  assert.equal(state.currentStep?.stepId, "step-review-consistency");
  assert.equal(workflowRunStatusTitle(state), "2 个步骤并行执行中");
});

test("旧 fence、错 profile 与倒退 progress 只能推进 Run 游标，不能污染步骤", () => {
  const profile = modelProfile("reviewer.consistency.v1");
  const wrongProfile = modelProfile("reviewer.editorial.v1");
  let state = createWorkflowRunUiState(pendingRun([activeStep(
    "step-review-consistency",
    2,
    "reviewer.consistency.v1",
    "deepseek-reasoner",
    2,
  )]));

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(3, "step_progress", {
    stepId: "step-review-consistency",
    fencingToken: 1,
    progressSequence: 99,
    modelProfile: profile,
    resolvedModel: resolvedModel(profile, "old-model"),
    phase: "waiting_provider",
    elapsedSeconds: 999,
    waitingOnProvider: true,
    usageStatus: "unknown",
  })))!;
  assert.equal(state.lastEventSequence, 3);
  assert.equal(state.activeSteps[0]?.progress, null);
  assert.equal(state.activeSteps[0]?.resolvedModel?.model, "deepseek-reasoner");

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(4, "step_progress", {
    stepId: "step-review-consistency",
    fencingToken: 2,
    progressSequence: 1,
    modelProfile: wrongProfile,
    resolvedModel: resolvedModel(wrongProfile, "wrong-model"),
    phase: "validating",
    elapsedSeconds: 77,
    waitingOnProvider: false,
    usageStatus: "complete",
  })))!;
  assert.equal(state.lastEventSequence, 4);
  assert.equal(state.activeSteps[0]?.progress, null);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(5, "step_progress", {
    stepId: "step-review-consistency",
    fencingToken: 2,
    progressSequence: 3,
    modelProfile: profile,
    resolvedModel: resolvedModel(profile, "deepseek-reasoner"),
    phase: "validating",
    elapsedSeconds: 33,
    waitingOnProvider: false,
    usageStatus: "complete",
  })))!;
  assert.equal(state.activeSteps[0]?.progress?.elapsedSeconds, 33);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(6, "step_progress", {
    stepId: "step-review-consistency",
    fencingToken: 2,
    progressSequence: 2,
    modelProfile: profile,
    resolvedModel: resolvedModel(profile, "deepseek-reasoner"),
    phase: "waiting_provider",
    elapsedSeconds: 22,
    waitingOnProvider: true,
    usageStatus: "partial",
  })))!;
  assert.equal(state.lastEventSequence, 6);
  assert.equal(state.activeSteps[0]?.progress?.elapsedSeconds, 33);
});

test("缺少 queued 上下文的 started 不会猜测 lane 或串到其他步骤", () => {
  const profile = modelProfile("reviewer.editorial.v1");
  const state = applyWorkflowStreamEvent(
    createWorkflowRunUiState(pendingRun()),
    workflowEvent(envelope(3, "step_started", {
      stepId: "orphan-step",
      ordinal: 3,
      purpose: "review",
      modelProfile: profile,
      attemptCount: 1,
      fencingToken: 1,
    })),
  );

  assert.equal(state?.lastEventSequence, 3);
  assert.deepEqual(state?.activeSteps, []);
  assert.equal(state?.currentStep, null);
});

test("只有 matching-fence step_finished 清理单个活动步骤，聚合事件不代替终态", () => {
  const generator = activeStep(
    "step-generation",
    1,
    "writer.chapter_selection.v1",
    "deepseek-chat",
  );
  const consistency = activeStep(
    "step-review-consistency",
    2,
    "reviewer.consistency.v1",
    "deepseek-reasoner",
  );
  const editorial = activeStep(
    "step-review-editorial",
    3,
    "reviewer.editorial.v1",
    "deepseek-chat",
  );
  let state = createWorkflowRunUiState(pendingRun([generator, consistency, editorial]));
  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(3, "candidate_ready", {
    stepId: "step-generation",
    artifactId: "artifact-1",
    artifactRevision: 1,
  })))!;
  assert.equal(state.activeSteps.length, 3);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(4, "step_finished", {
    stepId: "step-generation",
    fencingToken: 1,
    status: "completed",
    errorCode: null,
  })))!;
  assert.deepEqual(state.activeSteps.map((step) => step.stepId), [
    "step-review-consistency",
    "step-review-editorial",
  ]);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(5, "review_started", {
    artifactId: "artifact-1",
    artifactRevision: 1,
    reviewerSteps: [
      {
        stepId: consistency.stepId,
        ordinal: consistency.ordinal,
        purpose: "review",
        lane: consistency.lane,
        modelProfile: consistency.modelProfile,
        status: "pending",
        attemptCount: 0,
        fencingToken: 0,
      },
      {
        stepId: editorial.stepId,
        ordinal: editorial.ordinal,
        purpose: "review",
        lane: editorial.lane,
        modelProfile: editorial.modelProfile,
        status: "pending",
        attemptCount: 0,
        fencingToken: 0,
      },
    ],
  })))!;
  assert.equal(state.activeSteps.length, 2);
  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(6, "review_completed", {
    artifactId: "artifact-1",
    artifactRevision: 1,
    evaluationIds: ["evaluation-1", "evaluation-2"],
    mergedVerdict: "pass",
    reviewAvailability: "complete",
  })))!;
  assert.equal(state.activeSteps.length, 2);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(7, "step_finished", {
    stepId: "step-review-consistency",
    fencingToken: 2,
    status: "completed",
    errorCode: null,
  })))!;
  assert.equal(state.activeSteps.length, 2);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(8, "step_finished", {
    stepId: "step-review-consistency",
    fencingToken: 1,
    status: "completed",
    errorCode: null,
  })))!;
  assert.deepEqual(state.activeSteps.map((step) => step.stepId), ["step-review-editorial"]);

  state = applyWorkflowStreamEvent(state, workflowEvent(envelope(9, "step_finished", {
    stepId: "step-review-editorial",
    fencingToken: 1,
    status: "failed",
    errorCode: "REVIEWER_UNAVAILABLE",
  })))!;
  assert.deepEqual(state.activeSteps, []);
  assert.equal(state.currentStep, null);
});

test("逻辑角色与解析模型只展示允许公开的信息", () => {
  const profile = modelProfile("reviewer.editorial.v1");
  const resolved = resolvedModel(profile, "deepseek-chat");
  assert.equal(workflowModelRoleLabel(profile, "review"), "编辑复审");
  assert.equal(workflowModelRoleLabel(modelProfile("editor.answer.v1"), "generation"), "章节问答");
  assert.equal(workflowResolvedModelLabel(resolved), "DeepSeek · deepseek-chat");
  assert.doesNotMatch(workflowResolvedModelLabel(resolved) ?? "", /deployment|endpoint|fingerprint/i);
});

test("只有 chat_answer 完成事件要求回读当前会话权威消息", () => {
  const answerCompleted = workflowEvent(envelope(3, "completed", {
    outcomeType: "chat_answer",
    resultId: "message-1",
  }));
  const artifactCompleted = workflowEvent(envelope(4, "completed", {
    outcomeType: "artifact_applied",
    artifactId: "artifact-1",
    artifactRevision: 1,
    resultId: "artifact-1",
  }));

  assert.equal(workflowEventRequiresSessionMessageRefresh(answerCompleted), true);
  assert.equal(workflowEventRequiresSessionMessageRefresh(artifactCompleted), false);
});

test("状态卡逐项渲染 activeSteps，currentStep 不再充当并行活动权威", async () => {
  const conversationUrl = new URL("../writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");

  assert.match(source, /workflowRun\.activeSteps\.map\(\(step\)\s*=>/);
  assert.match(source, /key=\{`\$\{step\.stepId\}:\$\{step\.fencingToken\}`\}/);
  assert.match(source, /workflowModelRoleLabel\(step\.modelProfile, step\.purpose\)/);
  assert.match(source, /workflowResolvedModelLabel\(step\.resolvedModel\)/);
  assert.doesNotMatch(source, /workflowRun\.currentStep/);
  assert.doesNotMatch(source, /deploymentFingerprint|deploymentProfileKey|endpointProfile/);
});

test("awaiting_user 是前台观察边界并清空已终态步骤", () => {
  const base = createWorkflowRunUiState(pendingRun([activeStep(
    "step-review",
    2,
    "reviewer.consistency.v1",
    "deepseek-reasoner",
  )]));
  const state = applyWorkflowStreamEvent(base, workflowEvent(envelope(3, "awaiting_user", {
    artifactId: "artifact-1",
    artifactRevision: 1,
    allowedDecisions: ["approve", "discard", "revise"],
    reviewAvailability: "complete",
  })));

  assert.equal(state?.status, "waiting_user");
  assert.equal(state?.artifact?.actionable, true);
  assert.deepEqual(state?.activeSteps, []);
  assert.equal(workflowRunShouldStopObservation(state), true);
});

test("会话恢复只选择最新的非终态 V2 Run", () => {
  const initialRun = pendingRun();
  const selected = selectForegroundWorkflowRun([
    {
      engineVersion: 1,
      runId: "legacy-task",
      taskId: "legacy-task",
      novelId: "novel-1",
      chapterId: "chapter-1",
      writingSessionId: "session-1",
      workflow: "long_serial",
      operation: null,
      target: {},
      scope: {},
      phase: "active",
      outcome: {
        state: "running",
        code: "RUNNING",
        taskTerminal: false,
        streamShouldClose: false,
        reconciliationRequired: false,
        currentCommand: null,
        result: { kind: "none", ready: false, id: null },
        observedAt: "2026-09-01T12:00:00Z",
      },
      activeArtifactId: null,
      recoverable: true,
      createdAt: "2026-09-01T12:00:00Z",
      updatedAt: "2026-09-01T12:00:00Z",
    },
    { ...initialRun, status: "running" },
  ]);

  assert.equal(selected?.runId, "run-1");
  assert.equal(selectForegroundWorkflowRun([{ ...initialRun, status: "completed" }]), null);
});

import type { components } from "@inkforge/api-client";

import type {
  WorkflowStepProgressSnapshot,
  WritingSseEvent,
} from "@/shared/contracts/sse-events";

export type WritingRunStartResponse = components["schemas"]["WritingRunStartResponse"];
export type WritingRunStatusResponse = components["schemas"]["WritingRunStatusPublicResponse"];
type GeneratedWorkflowRunV2Response = components["schemas"]["WritingRunV2Response"];
type GeneratedWorkflowCurrentStep = components["schemas"]["WorkflowCurrentStepSnapshot"];
export type WorkflowCurrentStep = GeneratedWorkflowCurrentStep & {
  // 生成客户端刷新前保持可兼容；SSE Zod 契约已把该字段校验为 wire 必填。
  latestProgress?: WorkflowStepProgressSnapshot | null;
};
export type WorkflowRunV2Response = Omit<
  GeneratedWorkflowRunV2Response,
  "activeSteps" | "currentStep"
> & {
  activeSteps: WorkflowCurrentStep[];
  currentStep?: WorkflowCurrentStep | null;
};
export type WorkflowModelProfile = components["schemas"]["ModelProfileRef"];
export type WorkflowResolvedModel = components["schemas"]["ResolvedModelRef"];
export type WorkflowArtifact = components["schemas"]["WorkflowArtifactSnapshot"];
export type WorkflowError = components["schemas"]["WorkflowErrorSnapshot"];
export type WritingRunListItem = components["schemas"]["WritingRunPublicListItem"];

export type RunSnapshotEvent = Extract<WritingSseEvent, { type: "run_snapshot" }>;
export type WorkflowEvent = Extract<WritingSseEvent, { type: "workflow_event" }>;
export type WorkflowProgress = Extract<WorkflowEvent, { eventType: "step_progress" }>["payload"];

export type WorkflowActiveStep = Omit<WorkflowCurrentStep, "latestProgress"> & {
  progress: WorkflowStepProgressSnapshot | null;
};

export type WorkflowRunUiState = {
  engineVersion: 2;
  runId: string;
  workflow: string;
  operation: string | null;
  status: WorkflowRunV2Response["status"];
  activeSteps: WorkflowActiveStep[];
  currentStep: WorkflowCurrentStep | null;
  cancelRequestedAt: string | null;
  lastEventSequence: number;
  revision: number;
  artifact: WorkflowArtifact | null;
  error: WorkflowError | null;
  activity: string;
};

const MODEL_PROFILE_LABELS: Readonly<Record<string, string>> = {
  "writer.chapter_selection.v1": "章节选区改写",
  "reviewer.consistency.v1": "一致性校验",
  "reviewer.editorial.v1": "编辑复审",
};

const PROVIDER_LABELS: Readonly<Record<string, string>> = {
  anthropic: "Anthropic",
  deepseek: "DeepSeek",
  google: "Google",
  openai: "OpenAI",
  volcengine: "火山引擎",
};

export function isWorkflowRunV2(
  run: { engineVersion: number },
): run is GeneratedWorkflowRunV2Response {
  return run.engineVersion === 2;
}

export function writingRunId(run: WritingRunStartResponse): string {
  return isWorkflowRunV2(run) ? run.runId : run.id;
}

export function selectForegroundWorkflowRun(
  runs: readonly WritingRunListItem[],
): WorkflowRunV2Response | null {
  return runs.find((run): run is WorkflowRunV2Response => (
    run.engineVersion === 2
    && (run.status === "pending" || run.status === "running" || run.status === "waiting_user")
  )) ?? null;
}

export function createWorkflowRunUiState(run: WorkflowRunV2Response): WorkflowRunUiState {
  const activeSteps = activeStepsFromSnapshot(run.activeSteps);
  return {
    engineVersion: 2,
    runId: run.runId,
    workflow: run.workflow,
    operation: run.operation ?? null,
    status: run.status,
    activeSteps,
    currentStep: summarizeActiveSteps(activeSteps),
    cancelRequestedAt: run.cancelRequestedAt ?? null,
    lastEventSequence: run.lastEventSequence,
    revision: run.revision,
    artifact: run.artifact ?? null,
    error: run.error ?? null,
    activity: activityFromSnapshot(run),
  };
}

export function applyWorkflowStreamEvent(
  state: WorkflowRunUiState | null,
  event: RunSnapshotEvent | WorkflowEvent,
): WorkflowRunUiState | null {
  if (event.type === "run_snapshot") {
    const activeSteps = activeStepsFromSnapshot(event.snapshot.activeSteps);
    return {
      engineVersion: 2,
      runId: event.runId,
      workflow: event.snapshot.workflow,
      operation: event.snapshot.operation ?? null,
      status: event.snapshot.status,
      activeSteps,
      currentStep: summarizeActiveSteps(activeSteps),
      cancelRequestedAt: event.snapshot.cancelRequestedAt ?? null,
      lastEventSequence: event.baseSequence,
      revision: event.snapshot.revision,
      artifact: event.snapshot.artifact ?? null,
      error: event.snapshot.error ?? null,
      activity: activityFromSnapshot(event.snapshot),
    };
  }

  if (!state || state.runId !== event.runId || event.sequence <= state.lastEventSequence) {
    return state;
  }

  const advanced: WorkflowRunUiState = {
    ...state,
    lastEventSequence: event.sequence,
  };

  switch (event.eventType) {
    case "run_accepted":
      return {
        ...advanced,
        revision: event.payload.runRevision,
        activity: workflowEventLabel(event),
      };
    case "intent_resolved":
      return {
        ...advanced,
        operation: event.payload.operation,
        status: "running",
        activity: workflowEventLabel(event),
      };
    case "clarification_required":
      return clearActiveSteps({
        ...advanced,
        status: "waiting_user",
        activity: workflowEventLabel(event),
      });
    case "evidence_ready":
      return {
        ...advanced,
        status: "running",
        activity: workflowEventLabel(event),
      };
    case "step_queued":
      return applyStepQueued(advanced, event);
    case "step_started":
      return applyStepStarted(advanced, event);
    case "step_progress":
      return applyStepProgress(advanced, event);
    case "step_finished":
      return applyStepFinished(advanced, event);
    case "candidate_ready": {
      return {
        ...advanced,
        status: "running",
        artifact: {
          artifactId: event.payload.artifactId,
          artifactRevision: event.payload.artifactRevision,
          status: "under_review",
          actionable: false,
          reviewAvailability: null,
        },
        activity: workflowEventLabel(event),
      };
    }
    case "review_started":
      return applyReviewStarted({
        ...advanced,
        status: "running",
        artifact: {
          artifactId: event.payload.artifactId,
          artifactRevision: event.payload.artifactRevision,
          status: "under_review",
          actionable: false,
          reviewAvailability: null,
        },
        activity: workflowEventLabel(event),
      }, event);
    case "review_completed":
      return {
        ...advanced,
        status: "running",
        artifact: {
          artifactId: event.payload.artifactId,
          artifactRevision: event.payload.artifactRevision,
          status: "under_review",
          actionable: false,
          reviewAvailability: event.payload.reviewAvailability,
        },
        activity: workflowEventLabel(event),
      };
    case "awaiting_user":
      return clearActiveSteps({
        ...advanced,
        status: "waiting_user",
        artifact: {
          artifactId: event.payload.artifactId,
          artifactRevision: event.payload.artifactRevision,
          status: "awaiting_user",
          actionable: true,
          reviewAvailability: event.payload.reviewAvailability,
        },
        activity: workflowEventLabel(event),
      });
    case "applying":
      return {
        ...advanced,
        status: "running",
        artifact: {
          artifactId: event.payload.artifactId,
          artifactRevision: event.payload.artifactRevision,
          status: "applying",
          actionable: false,
          reviewAvailability: state.artifact?.reviewAvailability ?? null,
        },
        activity: workflowEventLabel(event),
      };
    case "completed":
      return clearActiveSteps({
        ...advanced,
        status: "completed",
        artifact: state.artifact ? { ...state.artifact, actionable: false } : null,
        activity: workflowEventLabel(event),
      });
    case "failed":
      return clearActiveSteps({
        ...advanced,
        status: "failed",
        error: {
          errorCode: event.payload.errorCode,
          failedStepId: event.payload.failedStepId ?? null,
          outcomeUnknown: event.payload.outcomeUnknown,
        },
        activity: workflowEventLabel(event),
      });
    case "cancelled":
      return clearActiveSteps({
        ...advanced,
        status: "cancelled",
        cancelRequestedAt: state.cancelRequestedAt ?? event.occurredAt,
        artifact: state.artifact ? { ...state.artifact, actionable: false } : null,
        activity: workflowEventLabel(event),
      });
  }
}

export function workflowRunIsForeground(state: WorkflowRunUiState | null): boolean {
  return Boolean(state && ["pending", "running", "waiting_user"].includes(state.status));
}

export function workflowRunShouldStopObservation(state: WorkflowRunUiState | null): boolean {
  return Boolean(state && ["waiting_user", "completed", "failed", "cancelled"].includes(state.status));
}

export function workflowStepPurposeLabel(purpose: string): string {
  const labels: Record<string, string> = {
    generation: "生成候选",
    review: "自动复审",
    resolve_intent: "确认任务范围",
    summarize_evidence: "整理创作依据",
    protocol_correction: "校正结果格式",
    user_confirmation: "处理你的决定",
  };
  return labels[purpose] ?? "处理任务";
}

export function workflowModelRoleLabel(
  modelProfile: WorkflowModelProfile | null,
  purpose: string,
): string {
  if (!modelProfile) return workflowStepPurposeLabel(purpose);
  const exactLabel = MODEL_PROFILE_LABELS[modelProfile.profile];
  if (exactLabel) return exactLabel;
  if (modelProfile.profile.startsWith("writer.")) return "写作生成";
  if (modelProfile.profile.startsWith("reviewer.")) return "自动复审";
  return workflowStepPurposeLabel(purpose);
}

export function workflowResolvedModelLabel(
  resolvedModel: WorkflowResolvedModel | null,
): string | null {
  if (!resolvedModel) return null;
  const provider = PROVIDER_LABELS[resolvedModel.provider] ?? resolvedModel.provider;
  return `${provider} · ${resolvedModel.model}`;
}

export function workflowProgressPhaseLabel(phase: WorkflowProgress["phase"]): string {
  const labels: Record<WorkflowProgress["phase"], string> = {
    preparing: "准备模型输入",
    waiting_provider: "等待模型返回",
    validating: "校验结果",
    reporting: "保存执行结果",
  };
  return labels[phase];
}

export function workflowRunStatusTitle(state: WorkflowRunUiState): string {
  if (state.cancelRequestedAt && state.status === "running") return "正在安全停止";
  if (state.status === "waiting_user") return "候选已就绪，等待你确认";
  if (state.status === "completed") return "任务已完成";
  if (state.status === "failed") return "任务执行失败";
  if (state.status === "cancelled") return "任务已停止";
  if (state.activeSteps.length > 1) return `${state.activeSteps.length} 个步骤并行执行中`;
  const activeStep = state.activeSteps[0];
  if (activeStep?.progress) return workflowProgressPhaseLabel(activeStep.progress.phase);
  if (activeStep) return workflowModelRoleLabel(activeStep.modelProfile, activeStep.purpose);
  return state.activity;
}

export function workflowEventLabel(event: WorkflowEvent): string {
  switch (event.eventType) {
    case "run_accepted": return "任务已受理";
    case "intent_resolved": return "任务范围已确认";
    case "clarification_required": return "需要你补充信息";
    case "evidence_ready": return "创作依据已冻结";
    case "step_queued": return `${workflowModelRoleLabel(event.payload.modelProfile, event.payload.purpose)}已排队`;
    case "step_started": return `${workflowModelRoleLabel(event.payload.modelProfile, event.payload.purpose)}已开始`;
    case "step_progress": return `${workflowModelRoleLabel(event.payload.modelProfile, "generation")} · ${workflowProgressPhaseLabel(event.payload.phase)}`;
    case "step_finished": return event.payload.status === "failed" ? "执行步骤失败" : "执行步骤已结束";
    case "candidate_ready": return "候选已生成";
    case "review_started": return "自动复审已开始";
    case "review_completed": return "自动复审已完成";
    case "awaiting_user": return "候选等待确认";
    case "applying": return "正在应用确认的变更";
    case "completed": return "任务已完成";
    case "failed": return `任务失败：${event.payload.errorCode}`;
    case "cancelled": return "任务已停止";
  }
}

function applyStepQueued(
  state: WorkflowRunUiState,
  event: Extract<WorkflowEvent, { eventType: "step_queued" }>,
): WorkflowRunUiState {
  const existing = state.activeSteps.find((step) => step.stepId === event.payload.stepId);
  if (!existing) {
    if (state.activeSteps.some((step) => step.ordinal === event.payload.ordinal)) return state;
    const nextStep: WorkflowActiveStep = {
      stepId: event.payload.stepId,
      ordinal: event.payload.ordinal,
      purpose: event.payload.purpose,
      lane: event.payload.lane,
      modelProfile: event.payload.modelProfile,
      resolvedModel: null,
      status: "pending",
      attemptCount: event.payload.attemptCount,
      fencingToken: event.payload.fencingToken,
      errorCode: null,
      progress: null,
    };
    return withActiveSteps({
      ...state,
      status: "running",
      activity: workflowEventLabel(event),
    }, [...state.activeSteps, nextStep]);
  }

  if (
    event.payload.fencingToken <= existing.fencingToken
    || event.payload.ordinal !== existing.ordinal
    || event.payload.purpose !== existing.purpose
    || event.payload.lane !== existing.lane
    || event.payload.attemptCount < existing.attemptCount
    || !modelProfileEquals(event.payload.modelProfile, existing.modelProfile)
  ) {
    return state;
  }

  const nextStep: WorkflowActiveStep = {
    ...existing,
    status: "pending",
    attemptCount: event.payload.attemptCount,
    fencingToken: event.payload.fencingToken,
    progress: null,
  };
  return withActiveSteps({
    ...state,
    status: "running",
    activity: workflowEventLabel(event),
  }, replaceActiveStep(state.activeSteps, nextStep));
}

function applyStepStarted(
  state: WorkflowRunUiState,
  event: Extract<WorkflowEvent, { eventType: "step_started" }>,
): WorkflowRunUiState {
  const existing = state.activeSteps.find((step) => step.stepId === event.payload.stepId);
  if (
    !existing
    || event.payload.fencingToken !== existing.fencingToken
    || event.payload.ordinal !== existing.ordinal
    || event.payload.purpose !== existing.purpose
    || event.payload.attemptCount !== existing.attemptCount
    || !modelProfileEquals(event.payload.modelProfile, existing.modelProfile)
  ) {
    return state;
  }
  const nextStep: WorkflowActiveStep = { ...existing, status: "running" };
  return withActiveSteps({
    ...state,
    status: "running",
    activity: workflowEventLabel(event),
  }, replaceActiveStep(state.activeSteps, nextStep));
}

function applyStepProgress(
  state: WorkflowRunUiState,
  event: Extract<WorkflowEvent, { eventType: "step_progress" }>,
): WorkflowRunUiState {
  const existing = state.activeSteps.find((step) => step.stepId === event.payload.stepId);
  if (
    !existing
    || event.payload.fencingToken !== existing.fencingToken
    || !modelProfileEquals(event.payload.modelProfile, existing.modelProfile)
    || (existing.resolvedModel && !resolvedModelEquals(event.payload.resolvedModel, existing.resolvedModel))
    || (existing.progress && event.payload.progressSequence <= existing.progress.progressSequence)
  ) {
    return state;
  }
  const nextStep: WorkflowActiveStep = {
    ...existing,
    resolvedModel: event.payload.resolvedModel,
    status: "running",
    progress: {
      progressSequence: event.payload.progressSequence,
      phase: event.payload.phase,
      elapsedSeconds: event.payload.elapsedSeconds,
      waitingOnProvider: event.payload.waitingOnProvider,
      usageStatus: event.payload.usageStatus,
    },
  };
  return withActiveSteps({
    ...state,
    status: "running",
    activity: workflowEventLabel(event),
  }, replaceActiveStep(state.activeSteps, nextStep));
}

function applyStepFinished(
  state: WorkflowRunUiState,
  event: Extract<WorkflowEvent, { eventType: "step_finished" }>,
): WorkflowRunUiState {
  const existing = state.activeSteps.find((step) => step.stepId === event.payload.stepId);
  if (!existing || existing.fencingToken !== event.payload.fencingToken) return state;
  return withActiveSteps({
    ...state,
    activity: workflowEventLabel(event),
  }, state.activeSteps.filter((step) => step.stepId !== event.payload.stepId));
}

function applyReviewStarted(
  state: WorkflowRunUiState,
  event: Extract<WorkflowEvent, { eventType: "review_started" }>,
): WorkflowRunUiState {
  const nextSteps = [...state.activeSteps];
  for (const pending of event.payload.reviewerSteps) {
    const existing = nextSteps.find((step) => step.stepId === pending.stepId);
    if (existing) {
      if (
        existing.ordinal !== pending.ordinal
        || existing.purpose !== pending.purpose
        || existing.lane !== pending.lane
        || !modelProfileEquals(existing.modelProfile, pending.modelProfile)
      ) {
        return state;
      }
      continue;
    }
    if (nextSteps.some((step) => step.ordinal === pending.ordinal)) return state;
    nextSteps.push({
      stepId: pending.stepId,
      ordinal: pending.ordinal,
      purpose: pending.purpose,
      lane: pending.lane,
      modelProfile: pending.modelProfile,
      resolvedModel: null,
      status: pending.status,
      attemptCount: pending.attemptCount,
      fencingToken: pending.fencingToken,
      errorCode: null,
      progress: null,
    });
  }
  return withActiveSteps(state, nextSteps);
}

function activeStepsFromSnapshot(
  steps: readonly WorkflowCurrentStep[],
): WorkflowActiveStep[] {
  return sortActiveSteps(steps.map(({ latestProgress, ...step }) => ({
    ...step,
    progress: latestProgress ?? null,
  })));
}

function replaceActiveStep(
  steps: readonly WorkflowActiveStep[],
  replacement: WorkflowActiveStep,
): WorkflowActiveStep[] {
  return steps.map((step) => step.stepId === replacement.stepId ? replacement : step);
}

function sortActiveSteps(steps: readonly WorkflowActiveStep[]): WorkflowActiveStep[] {
  return [...steps].sort((left, right) => (
    left.ordinal - right.ordinal || left.stepId.localeCompare(right.stepId)
  ));
}

function toStepSnapshot(step: WorkflowActiveStep): WorkflowCurrentStep {
  return {
    stepId: step.stepId,
    ordinal: step.ordinal,
    purpose: step.purpose,
    lane: step.lane,
    modelProfile: step.modelProfile,
    resolvedModel: step.resolvedModel,
    status: step.status,
    attemptCount: step.attemptCount,
    fencingToken: step.fencingToken,
    latestProgress: step.progress,
    errorCode: step.errorCode ?? null,
  };
}

function summarizeActiveSteps(steps: readonly WorkflowActiveStep[]): WorkflowCurrentStep | null {
  return steps[0] ? toStepSnapshot(steps[0]) : null;
}

function withActiveSteps(
  state: WorkflowRunUiState,
  activeSteps: readonly WorkflowActiveStep[],
): WorkflowRunUiState {
  const sorted = sortActiveSteps(activeSteps);
  return {
    ...state,
    activeSteps: sorted,
    currentStep: summarizeActiveSteps(sorted),
  };
}

function clearActiveSteps(state: WorkflowRunUiState): WorkflowRunUiState {
  return {
    ...state,
    activeSteps: [],
    currentStep: null,
  };
}

function modelProfileEquals(
  left: WorkflowModelProfile | null,
  right: WorkflowModelProfile | null,
): boolean {
  if (!left || !right) return left === right;
  return left.profile === right.profile
    && left.version === right.version
    && left.reasoningMode === right.reasoningMode
    && left.deploymentProfileKey === right.deploymentProfileKey
    && left.promptProfile.name === right.promptProfile.name
    && left.promptProfile.version === right.promptProfile.version
    && left.promptProfile.sha256 === right.promptProfile.sha256;
}

function resolvedModelEquals(
  left: WorkflowResolvedModel,
  right: WorkflowResolvedModel,
): boolean {
  return left.deploymentFingerprint === right.deploymentFingerprint
    && left.deploymentProfileKey === right.deploymentProfileKey
    && left.provider === right.provider
    && left.model === right.model
    && left.transportProfile === right.transportProfile
    && left.endpointProfile === right.endpointProfile
    && left.structuredOutputRoute === right.structuredOutputRoute
    && left.capabilityVersion === right.capabilityVersion
    && left.supportsRequestIdempotency === right.supportsRequestIdempotency
    && left.reasoningMode === right.reasoningMode;
}

function activityFromSnapshot(snapshot: {
  status: WorkflowRunV2Response["status"];
  activeSteps: readonly WorkflowCurrentStep[];
  cancelRequestedAt?: string | null;
}): string {
  if (snapshot.cancelRequestedAt && snapshot.status === "running") return "正在安全停止";
  if (snapshot.status === "waiting_user") return "候选等待确认";
  if (snapshot.status === "completed") return "任务已完成";
  if (snapshot.status === "failed") return "任务执行失败";
  if (snapshot.status === "cancelled") return "任务已停止";
  if (snapshot.activeSteps.length > 1) return `${snapshot.activeSteps.length} 个步骤并行执行中`;
  const currentStep = snapshot.activeSteps[0];
  if (currentStep) return workflowModelRoleLabel(currentStep.modelProfile, currentStep.purpose);
  return snapshot.status === "pending" ? "任务等待调度" : "任务执行中";
}

import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import type { WritingSessionTaskSummary } from "@/shared/contracts/writing-session";

export type LoadedSessionTask = WritingSessionTaskSummary | null;

export type LoadedSessionTaskState = {
  taskId: string | null;
  phase: "idle" | "discussing" | "recording";
  shouldRefreshAwaitingReviewArtifact: boolean;
};

export type LoadedSessionRecoveryState = LoadedSessionTaskState & {
  currentOperation: CreativeOperation | null;
  operationStage: string | null;
  activeArtifactId: string | null;
};

export function resolveLoadedSessionTaskState(
  task: LoadedSessionTask
): LoadedSessionTaskState {
  if (!task) {
    return {
      taskId: null,
      phase: "idle",
      shouldRefreshAwaitingReviewArtifact: false,
    };
  }

  if (task.phase === "awaiting_user_review") {
    return {
      taskId: task.id,
      phase: "recording",
      shouldRefreshAwaitingReviewArtifact: task.hasAwaitingReviewArtifact,
    };
  }

  if (task.phase === "active" || task.phase === "waiting_call") {
    return {
      taskId: task.id,
      phase: "discussing",
      shouldRefreshAwaitingReviewArtifact: false,
    };
  }

  return {
    taskId: null,
    phase: "idle",
    shouldRefreshAwaitingReviewArtifact: false,
  };
}

export function resolveLoadedSessionRecoveryState(
  task: LoadedSessionTask
): LoadedSessionRecoveryState {
  const taskState = resolveLoadedSessionTaskState(task);
  const isResumable = Boolean(taskState.taskId);
  return {
    ...taskState,
    currentOperation: isResumable ? task?.currentOperation ?? null : null,
    operationStage: isResumable ? task?.operationStage ?? null : null,
    activeArtifactId: isResumable ? task?.activeArtifactId ?? null : null,
  };
}

import type { CreativeOperation } from "@/shared/contracts/creative-operation";

export type LoadedSessionTaskPhase =
  | "idle"
  | "active"
  | "waiting_call"
  | "awaiting_user_review"
  | "completed"
  | "error";

export type LoadedSessionTask = {
  id: string;
  phase: LoadedSessionTaskPhase;
  updatedAt: string;
  hasAwaitingReviewArtifact: boolean;
  currentOperation?: CreativeOperation | null;
  operationStage?: string | null;
  activeArtifactId?: string | null;
} | null;

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
    taskId: task.id,
    phase: "idle",
    shouldRefreshAwaitingReviewArtifact: false,
  };
}

export function resolveLoadedSessionRecoveryState(
  task: LoadedSessionTask
): LoadedSessionRecoveryState {
  const taskState = resolveLoadedSessionTaskState(task);
  return {
    ...taskState,
    currentOperation: task?.currentOperation ?? null,
    operationStage: task?.operationStage ?? null,
    activeArtifactId: task?.activeArtifactId ?? null,
  };
}

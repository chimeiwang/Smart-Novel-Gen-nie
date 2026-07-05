import type { CreativeOperation } from "@/shared/contracts/creative-operation";

export type WritingConversationPhase =
  | "idle"
  | "discussing"
  | "generating"
  | "reviewing"
  | "recording"
  | "completed"
  | "error";

export type SessionWorkspaceState<TArtifact> = {
  sessionId: string | null;
  taskId: string | null;
  phase: WritingConversationPhase;
  currentOperation: CreativeOperation | null;
  operationStage: string | null;
  activeReviewArtifact: TArtifact | null;
};

export type SessionWorkspaceAction<TArtifact> =
  | { type: "replace"; state: SessionWorkspaceState<TArtifact> }
  | { type: "set_task"; taskId: string | null }
  | { type: "set_phase"; phase: WritingConversationPhase }
  | { type: "set_operation"; operation: CreativeOperation | null }
  | { type: "set_operation_stage"; stage: string | null }
  | { type: "set_active_artifact"; artifact: TArtifact | null };

export function createEmptySessionWorkspace<TArtifact>(
  sessionId: string | null = null
): SessionWorkspaceState<TArtifact> {
  return {
    sessionId,
    taskId: null,
    phase: "idle",
    currentOperation: null,
    operationStage: null,
    activeReviewArtifact: null,
  };
}

export function reduceSessionWorkspace<TArtifact>(
  state: SessionWorkspaceState<TArtifact>,
  action: SessionWorkspaceAction<TArtifact>
): SessionWorkspaceState<TArtifact> {
  switch (action.type) {
    case "replace":
      return action.state;
    case "set_task":
      return { ...state, taskId: action.taskId };
    case "set_phase":
      return { ...state, phase: action.phase };
    case "set_operation":
      return { ...state, currentOperation: action.operation };
    case "set_operation_stage":
      return { ...state, operationStage: action.stage };
    case "set_active_artifact":
      return { ...state, activeReviewArtifact: action.artifact };
  }
}

export function isCurrentSessionStream(
  selectedSessionId: string | null,
  streamSessionId: string
): boolean {
  return selectedSessionId === streamSessionId;
}

export function resolveArtifactInteractionScope(input: {
  activeArtifactId?: string | null;
  currentTaskId?: string | null;
  artifactId: string;
  artifactTaskId?: string | null;
}): "session" | "artifact" {
  return input.activeArtifactId === input.artifactId &&
    Boolean(input.currentTaskId) &&
    input.currentTaskId === input.artifactTaskId
    ? "session"
    : "artifact";
}

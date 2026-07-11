import type { WritingTaskPhase } from "@prisma/client";
import { deserializeGraphStateSnapshot } from "@/agents/graph/graph-state-snapshot";
import type { WritingSessionTaskSummary } from "@/shared/contracts/writing-session";

export type SessionTaskCandidate = {
  id: string;
  phase: WritingTaskPhase;
  updatedAt: Date;
  generatedContent: string | null;
  graphStateJson?: string | null;
};

const RESUMABLE_PHASE_PRIORITY: WritingTaskPhase[] = [
  "awaiting_user_review",
  "active",
  "waiting_call",
];

const HISTORICAL_PHASES = new Set<WritingTaskPhase>(["completed", "error"]);

function toSessionTaskSummary(task: SessionTaskCandidate): WritingSessionTaskSummary {
  const snapshot = deserializeGraphStateSnapshot(task.graphStateJson);
  const activeArtifactId =
    snapshot?.artifactReview.activeArtifactId ??
    snapshot?.activeArtifactId ??
    (task.phase === "awaiting_user_review" ? task.generatedContent : null);

  return {
    id: task.id,
    phase: task.phase,
    updatedAt: task.updatedAt.toISOString(),
    hasAwaitingReviewArtifact:
      task.phase === "awaiting_user_review" && Boolean(activeArtifactId),
    currentOperation: snapshot?.currentOperation ?? null,
    operationStage: snapshot?.operationStage ?? null,
    activeArtifactId,
  };
}

export function selectCurrentSessionTask(
  tasks: SessionTaskCandidate[]
): WritingSessionTaskSummary | null {
  for (const phase of RESUMABLE_PHASE_PRIORITY) {
    const match = tasks.find((task) => task.phase === phase);
    if (match) return toSessionTaskSummary(match);
  }

  return null;
}

export function selectCurrentSessionTaskFromSession(input: {
  tasks: SessionTaskCandidate[];
}): WritingSessionTaskSummary | null {
  return selectCurrentSessionTask(input.tasks);
}

export function selectLastSessionTask(
  tasks: SessionTaskCandidate[]
): WritingSessionTaskSummary | null {
  const match = tasks.find((task) => HISTORICAL_PHASES.has(task.phase));
  return match ? toSessionTaskSummary(match) : null;
}

import type { WritingTaskPhase } from "@prisma/client";
import type { CreativeOperation } from "@/shared/contracts/creative-operation";
import { deserializeGraphStateSnapshot } from "@/agents/graph/graph-state-snapshot";

export type SessionTaskCandidate = {
  id: string;
  phase: WritingTaskPhase;
  updatedAt: Date;
  generatedContent: string | null;
  graphStateJson?: string | null;
};

export type CurrentSessionTask = {
  id: string;
  phase: WritingTaskPhase;
  updatedAt: string;
  hasAwaitingReviewArtifact: boolean;
  currentOperation: CreativeOperation | null;
  operationStage: string | null;
  activeArtifactId: string | null;
} | null;

const PHASE_PRIORITY: WritingTaskPhase[] = [
  "awaiting_user_review",
  "active",
  "waiting_call",
  "completed",
  "error",
  "idle",
];

export function selectCurrentSessionTask(
  tasks: SessionTaskCandidate[]
): CurrentSessionTask {
  for (const phase of PHASE_PRIORITY) {
    const match = tasks.find((task) => task.phase === phase);
    if (match) {
      const snapshot = deserializeGraphStateSnapshot(match.graphStateJson);
      return {
        id: match.id,
        phase: match.phase,
        updatedAt: match.updatedAt.toISOString(),
        hasAwaitingReviewArtifact:
          match.phase === "awaiting_user_review" && Boolean(match.generatedContent),
        currentOperation: snapshot?.currentOperation ?? null,
        operationStage: snapshot?.operationStage ?? null,
        activeArtifactId:
          snapshot?.activeArtifactId ??
          (match.phase === "awaiting_user_review" ? match.generatedContent : null),
      };
    }
  }

  return null;
}

export function selectCurrentSessionTaskFromSession(input: {
  tasks: SessionTaskCandidate[];
  fallbackCandidates?: SessionTaskCandidate[];
}): CurrentSessionTask {
  if (input.tasks.length > 0) return selectCurrentSessionTask(input.tasks);
  return selectCurrentSessionTask(input.fallbackCandidates ?? []);
}

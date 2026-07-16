type AwaitingReviewTaskCandidate = {
  id: string;
  hasAwaitingReviewArtifact: boolean;
};

type SessionReviewTaskCandidates = {
  currentTask?: AwaitingReviewTaskCandidate | null;
  lastTask?: AwaitingReviewTaskCandidate | null;
};

type ReviewArtifactCandidate = {
  id: string;
  artifactKey?: string | null;
  status: string;
};

export function collectAwaitingReviewTaskIds(
  sessions: readonly SessionReviewTaskCandidates[],
): string[] {
  const taskIds = new Set<string>();
  for (const session of sessions) {
    for (const task of [session.currentTask, session.lastTask]) {
      if (task?.hasAwaitingReviewArtifact) taskIds.add(task.id);
    }
  }
  return [...taskIds];
}

export function mergeActionableReviewArtifacts<T extends ReviewArtifactCandidate>(
  ...collections: ReadonlyArray<readonly T[]>
): T[] {
  const order: string[] = [];
  const artifacts = new Map<string, T>();

  for (const collection of collections) {
    for (const artifact of collection) {
      if (artifact.status !== "awaiting_user") continue;
      const key = artifact.artifactKey || artifact.id;
      if (!artifacts.has(key)) order.push(key);
      artifacts.set(key, artifact);
    }
  }

  return order.flatMap((key) => {
    const artifact = artifacts.get(key);
    return artifact ? [artifact] : [];
  });
}

export type MessageWithReviewArtifact<TArtifact> = {
  reviewArtifact?: TArtifact | null;
};

export type ReviewArtifactWithTaskId = {
  engineVersion: 1 | 2;
  taskId: string | null;
  workflowRunId: string | null;
};

export type TaskBoundReviewArtifact = ReviewArtifactWithTaskId & {
  id: string;
};

export type ReviewStateEpoch = {
  capture: () => number;
  invalidate: () => void;
  isCurrent: (capturedEpoch: number) => boolean;
};

export function createReviewStateEpoch(): ReviewStateEpoch {
  let epoch = 0;
  return {
    capture: () => epoch,
    invalidate: () => {
      epoch += 1;
    },
    isCurrent: (capturedEpoch) => capturedEpoch === epoch,
  };
}

export type ReviewArtifactOptimisticDecision = "approve" | "discard" | "revise";

export type OptimisticReviewArtifactStatus = "applying" | "discarding" | "revising";

export type OptimisticReviewArtifact<TArtifact> = TArtifact & {
  status?: string;
  optimisticStatus?: OptimisticReviewArtifactStatus;
};

export function attachReviewArtifactToLastMessage<TMessage extends MessageWithReviewArtifact<TArtifact>, TArtifact>(
  messages: TMessage[],
  artifact: TArtifact | null | undefined
): TMessage[] {
  if (!artifact || messages.length === 0) return messages;
  const lastIndex = messages.length - 1;
  return messages.map((message, index) =>
    index === lastIndex ? ({ ...message, reviewArtifact: artifact } as TMessage) : message
  );
}

export function attachReviewArtifactToConversation<
  TMessage extends MessageWithReviewArtifact<TArtifact>,
  TArtifact extends { id?: string; artifactKey?: string | null }
>(
  messages: TMessage[],
  artifact: TArtifact | null | undefined,
  createPlaceholder: () => TMessage
): TMessage[] {
  if (!artifact) return messages;
  const isSameArtifact = (message: TMessage) => {
    const current = message.reviewArtifact;
    if (!current) return false;
    if (artifact.id && current.id === artifact.id) return true;
    return Boolean(artifact.artifactKey && current.artifactKey === artifact.artifactKey);
  };
  const existingIndex = messages.findIndex(isSameArtifact);
  if (existingIndex >= 0) {
    return messages.map((message, index) =>
      index === existingIndex ? ({ ...message, reviewArtifact: artifact } as TMessage) : message
    );
  }
  if (messages.length === 0) {
    return [{ ...createPlaceholder(), reviewArtifact: artifact } as TMessage];
  }
  return [...messages, { ...createPlaceholder(), reviewArtifact: artifact } as TMessage];
}

export function clearReviewArtifactFromMessages<
  TMessage extends MessageWithReviewArtifact<TArtifact>,
  TArtifact extends { id?: string }
>(
  messages: TMessage[],
  artifactId: string
): TMessage[] {
  return messages.map((message) => {
    if (message.reviewArtifact?.id !== artifactId) return message;
    return { ...message, reviewArtifact: null };
  });
}

export function isTerminalReviewArtifact(
  artifact: TaskBoundReviewArtifact,
  taskId: string,
  transientArtifactIds: ReadonlySet<string>,
): boolean {
  return transientArtifactIds.has(artifact.id)
    || resolveReviewArtifactExecutionRunId(artifact) === taskId;
}

export function resolveReviewArtifactExecutionRunId(
  artifact: ReviewArtifactWithTaskId,
): string | null {
  const taskId = typeof artifact.taskId === "string" && artifact.taskId.length > 0
    ? artifact.taskId
    : null;
  const workflowRunId = typeof artifact.workflowRunId === "string" && artifact.workflowRunId.length > 0
    ? artifact.workflowRunId
    : null;
  if (artifact.engineVersion === 1) {
    return taskId && workflowRunId === null ? taskId : null;
  }
  if (artifact.engineVersion === 2) {
    return workflowRunId && taskId === null ? workflowRunId : null;
  }
  return null;
}

export function resolveVisibleReviewArtifact<TArtifact>(
  activeArtifact: TArtifact | null | undefined,
  messages: MessageWithReviewArtifact<TArtifact>[]
): TArtifact | null {
  if (activeArtifact) return activeArtifact;
  return messages.length > 0 ? messages[messages.length - 1]?.reviewArtifact ?? null : null;
}

export function resolveReviewArtifactTaskId(
  currentTaskId: string | null | undefined,
  artifact: ReviewArtifactWithTaskId | null | undefined
): string | null {
  if (!artifact) return currentTaskId ?? null;
  return resolveReviewArtifactExecutionRunId(artifact);
}

export function resolveReviewArtifactActionTaskId(
  currentTaskId: string | null | undefined,
  artifact: ReviewArtifactWithTaskId | null | undefined
): string | null {
  if (!artifact) return currentTaskId ?? null;
  return resolveReviewArtifactExecutionRunId(artifact);
}

export function applyOptimisticReviewArtifactDecision<
  TArtifact extends { id: string; status?: string }
>(
  artifact: TArtifact | null,
  input: { artifactId: string; decision: ReviewArtifactOptimisticDecision }
): OptimisticReviewArtifact<TArtifact> | null {
  if (!artifact || artifact.id !== input.artifactId) return artifact;
  if (input.decision === "discard") {
    return {
      ...artifact,
      status: "discarding",
      optimisticStatus: "discarding",
    };
  }
  if (input.decision === "revise") {
    return {
      ...artifact,
      status: "under_review",
      optimisticStatus: "revising",
    };
  }
  return {
    ...artifact,
    status: "applying",
    optimisticStatus: "applying",
  };
}

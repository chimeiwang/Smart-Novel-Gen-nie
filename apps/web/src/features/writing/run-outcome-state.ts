import type { RunOutcomeData } from "@/shared/contracts/sse-events";

export type LongRunOutcomeDecision =
  | { kind: "continue" }
  | { kind: "waiting_user"; artifactId: string }
  | { kind: "succeeded" }
  | { kind: "failed"; code: string }
  | { kind: "inconsistent"; code: string };

export type ReviewActionDecision = "approve" | "discard" | "revise";
export type ReviewActionResolution = "succeeded" | "failed" | null;

export function mapLongRunOutcome(
  outcome: RunOutcomeData,
): LongRunOutcomeDecision {
  if (outcome.state === "queued" || outcome.state === "running") {
    return { kind: "continue" };
  }
  if (
    outcome.state === "waiting_user"
    && outcome.result.kind === "review_artifact"
    && outcome.result.ready
    && typeof outcome.result.id === "string"
    && outcome.result.id.length > 0
  ) {
    return { kind: "waiting_user", artifactId: outcome.result.id };
  }
  if (outcome.state === "succeeded") {
    return { kind: "succeeded" };
  }
  if (outcome.state === "failed") {
    return { kind: "failed", code: outcome.code };
  }
  return { kind: "inconsistent", code: outcome.code };
}

export function resolvePendingReviewAction(
  decision: ReviewActionDecision,
  outcome: LongRunOutcomeDecision,
): ReviewActionResolution {
  if (outcome.kind === "failed" || outcome.kind === "inconsistent") {
    return "failed";
  }
  if (outcome.kind === "succeeded") return "succeeded";
  if (outcome.kind === "waiting_user" && decision === "revise") {
    return "succeeded";
  }
  return null;
}

export function rememberRunOutcomeSignature(
  eventType: string,
  signature: string | null,
): string | null {
  return eventType === "run_outcome" ? signature : null;
}

export function canLegacyPhaseUpdateProgress(phase: string): boolean {
  return phase !== "completed" && phase !== "error";
}

export type CompletionEffectGuard = {
  claim: (taskId: string, outcome: RunOutcomeData) => boolean;
};

export function createCompletionEffectGuard(): CompletionEffectGuard {
  const claimed = new Set<string>();
  return {
    claim(taskId, outcome) {
      if (outcome.state !== "succeeded") return false;
      const key = JSON.stringify({
        taskId,
        code: outcome.code,
        commandId: outcome.currentCommand?.id ?? null,
        resultKind: outcome.result.kind,
        resultId: outcome.result.id ?? null,
      });
      if (claimed.has(key)) return false;
      claimed.add(key);
      return true;
    },
  };
}

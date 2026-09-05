import type { RunOutcomeData } from "@/shared/contracts/sse-events";
import type { components } from "@inkforge/api-client";

export type ShortRunStatus = components["schemas"]["WritingRunStatusPublicResponse"];

export type ShortRunOutcome = RunOutcomeData;

export type ShortRunOutcomeDecision =
  | { kind: "continue" }
  | {
    kind: "succeeded";
    resultKind: "short_candidate" | "check_report";
    resultId: string | null;
  }
  | { kind: "failed"; code: string }
  | { kind: "inconsistent"; code: string };

export function decideShortRunOutcome(
  outcome: ShortRunOutcome,
): ShortRunOutcomeDecision {
  if (outcome.state === "queued" || outcome.state === "running") {
    return { kind: "continue" };
  }
  if (outcome.state === "failed" || outcome.state === "cancelled") {
    return { kind: "failed", code: outcome.code };
  }
  if (
    outcome.state === "succeeded"
    && outcome.result.ready
    && (outcome.result.kind === "short_candidate" || outcome.result.kind === "check_report")
    && (
      outcome.result.kind === "check_report"
      || (typeof outcome.result.id === "string" && outcome.result.id.length > 0)
    )
  ) {
    return {
      kind: "succeeded",
      resultKind: outcome.result.kind,
      resultId: outcome.result.id ?? null,
    };
  }
  return { kind: "inconsistent", code: outcome.code };
}

export function decideShortRunStatus(run: ShortRunStatus): ShortRunOutcomeDecision {
  if (run.workflow !== "short_medium") {
    return { kind: "inconsistent", code: "SHORT_MEDIUM_RUN_IDENTITY_INVALID" };
  }
  if (run.engineVersion === 1) return decideShortRunOutcome(run.outcome);
  if (run.status === "pending" || run.status === "running") return { kind: "continue" };
  if (run.status === "failed" || run.status === "cancelled") {
    return { kind: "failed", code: run.error?.errorCode ?? (run.status === "cancelled" ? "WORKFLOW_CANCELLED" : "WORKFLOW_FAILED") };
  }
  if (run.status === "completed") {
    if (run.operation === "full_check" && run.checkReport && Object.keys(run.checkReport).length === 1
      && typeof run.checkReport.text === "string" && run.checkReport.text.length > 0
      && !run.candidateVersionId && !run.artifact) {
      return { kind: "succeeded", resultKind: "check_report", resultId: null };
    }
    if (["generate_outline", "generate_manuscript", "replace_selection"].includes(run.operation ?? "")
      && typeof run.candidateVersionId === "string" && run.candidateVersionId.length > 0
      && !run.checkReport && run.artifact?.artifactId === run.candidateVersionId) {
      return { kind: "succeeded", resultKind: "short_candidate", resultId: run.candidateVersionId };
    }
  }
  return { kind: "inconsistent", code: "SHORT_MEDIUM_RESULT_MISSING" };
}

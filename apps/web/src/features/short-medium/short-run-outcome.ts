import type { RunOutcomeData } from "@/shared/contracts/sse-events";

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

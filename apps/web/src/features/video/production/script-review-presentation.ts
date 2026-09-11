import type { ScriptCandidate } from "./types";

/** 审阅是否通过只取决于完整结论，不能由 findings 是否为空推断。 */
export function scriptReviewPresentation(candidate: Pick<ScriptCandidate, "review" | "reviewFindings">) {
  const review = candidate.review;
  return {
    label: review ? review.decision === "revise" ? "仍有待核对项" : "已通过 AI 审阅" : "尚无审阅结果",
    requiresReview: review?.decision === "revise",
    summary: review?.summary ?? null,
    requiredChanges: review?.requiredChanges ?? [],
    findings: review ? review.findings : candidate.reviewFindings ?? [],
  };
}

import type { StoryboardCandidate } from "./types";

/** 只有完整 review 的 pass 才能展示审阅通过，不能由 findings 为空推断。 */
export function storyboardReviewPresentation(candidate: Pick<StoryboardCandidate, "review" | "reviewFindings">) {
  const review = candidate.review;
  return {
    label: review ? review.decision === "revise" ? "仍有待核对项" : "已通过 AI 审阅" : "尚无审阅结果",
    requiresReview: review?.decision === "revise",
    summary: review?.summary ?? null,
    requiredChanges: review?.requiredChanges ?? [],
    findings: review ? review.findings : candidate.reviewFindings ?? [],
  };
}

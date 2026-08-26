import type { QualityCheckDto } from "../../shared/contracts/quality-check";

type QualityCheckPresentationInput = Pick<
  QualityCheckDto,
  "status" | "result" | "scoreOverall" | "qualityGate"
>;

export type QualityCheckPresentationState =
  | QualityCheckPresentationInput["status"]
  | "invalid";

export type QualityScoreTone = "low" | "mid" | "high";

/**
 * 一致性报告契约使用 0..100 百分制。这里把旧十分制的 5/7 色阶等比例换算为
 * 50/70，避免仅修正文案后仍用错误门限着色。
 */
export function getConsistencyScoreTone(score: number): QualityScoreTone {
  if (score <= 50) return "low";
  if (score <= 70) return "mid";
  return "high";
}

/** 保留后端权威分值，不在展示层擅自除以十或重新四舍五入。 */
export function formatConsistencyScore(score: number): string {
  return `综合 ${score}/100`;
}

export function isValidCompletedQualityCheck(
  check: QualityCheckPresentationInput,
): boolean {
  return check.status === "completed"
    && typeof check.result === "string"
    && check.result.trim().length > 0
    && typeof check.scoreOverall === "number"
    && Number.isFinite(check.scoreOverall)
    && (check.qualityGate === "pass" || check.qualityGate === "revise");
}

export function isHandledQualityCheck(
  check: QualityCheckPresentationInput,
): boolean {
  return check.status === "skipped" || isValidCompletedQualityCheck(check);
}

export function countUnhandledQualityChecks(
  checks: readonly QualityCheckPresentationInput[],
): number {
  return checks.filter((check) => !isHandledQualityCheck(check)).length;
}

export function getQualityCheckPresentationState(
  check: QualityCheckPresentationInput,
): QualityCheckPresentationState {
  if (check.status === "completed") {
    return isValidCompletedQualityCheck(check) ? "completed" : "invalid";
  }
  return check.status;
}

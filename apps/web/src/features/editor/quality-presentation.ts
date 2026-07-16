import type { QualityCheckDto } from "../../shared/contracts/quality-check";

type QualityCheckPresentationInput = Pick<
  QualityCheckDto,
  "status" | "result" | "scoreOverall" | "qualityGate"
>;

export type QualityCheckPresentationState =
  | QualityCheckPresentationInput["status"]
  | "invalid";

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

export function getQualityCheckPresentationState(
  check: QualityCheckPresentationInput,
): QualityCheckPresentationState {
  if (check.status === "completed") {
    return isValidCompletedQualityCheck(check) ? "completed" : "invalid";
  }
  return check.status;
}

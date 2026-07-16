import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { QualityCheckDto } from "../../../shared/contracts/quality-check";

import {
  countUnhandledQualityChecks,
  getQualityCheckPresentationState,
  isHandledQualityCheck,
  isValidCompletedQualityCheck,
} from "../quality-presentation";

type QualityCheck = Pick<
  QualityCheckDto,
  "status" | "result" | "scoreOverall" | "qualityGate"
>;

const validCheck = (overrides: Partial<QualityCheck> = {}): QualityCheck => ({
  status: "completed",
  result: "人物动机与前文一致。",
  scoreOverall: 86,
  qualityGate: "pass",
  ...overrides,
});

describe("有效质量终检", () => {
  it("只接受报告、总分和合法门限完整的 completed", () => {
    assert.equal(isValidCompletedQualityCheck(validCheck()), true);
    assert.equal(isValidCompletedQualityCheck(validCheck({ qualityGate: "revise" })), true);
  });

  it("拒绝空报告、缺少总分、非有限总分和非法门限", () => {
    assert.equal(isValidCompletedQualityCheck(validCheck({ result: "  \n " })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ scoreOverall: null })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ scoreOverall: Number.NaN })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ scoreOverall: Number.POSITIVE_INFINITY })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ scoreOverall: Number.NEGATIVE_INFINITY })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ scoreOverall: true as unknown as number })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ qualityGate: "rewrite" })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ qualityGate: null })), false);
    assert.equal(isValidCompletedQualityCheck(validCheck({ status: "running" })), false);
  });
});

describe("质量终检展示态", () => {
  it("skipped 单独视为已处理", () => {
    const skipped = validCheck({
      status: "skipped",
      result: null,
      scoreOverall: null,
      qualityGate: null,
    });

    assert.equal(isValidCompletedQualityCheck(skipped), false);
    assert.equal(isHandledQualityCheck(skipped), true);
    assert.equal(getQualityCheckPresentationState(skipped), "skipped");
  });

  it("字段不完整的 completed 输出 invalid 且不视为已处理", () => {
    const invalid = validCheck({ result: null });

    assert.equal(isHandledQualityCheck(invalid), false);
    assert.equal(getQualityCheckPresentationState(invalid), "invalid");
    assert.equal(getQualityCheckPresentationState(validCheck()), "completed");
  });

  it("待处理计数包含无效 completed，不包含有效 completed 和 skipped", () => {
    assert.equal(countUnhandledQualityChecks([
      validCheck({ status: "pending", result: null, scoreOverall: null, qualityGate: null }),
      validCheck({ result: null }),
      validCheck(),
      validCheck({ status: "skipped", result: null, scoreOverall: null, qualityGate: null }),
    ]), 2);
  });
});

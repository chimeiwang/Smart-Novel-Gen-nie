import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { decideShortRunOutcome } from "../short-run-outcome";

const base = {
  code: "TEST",
  taskTerminal: false,
  streamShouldClose: false,
  reconciliationRequired: false,
  currentCommand: null,
  result: { kind: "none" as const, ready: false, id: null },
  observedAt: "2026-08-01T12:00:00Z",
};

describe("中短篇运行结果", () => {
  it("排队和运行中只继续观察", () => {
    assert.deepEqual(decideShortRunOutcome({ ...base, state: "queued" }), {
      kind: "continue",
    });
    assert.deepEqual(decideShortRunOutcome({ ...base, state: "running" }), {
      kind: "continue",
    });
  });

  it("只有真实产物就绪的成功才可打开结果", () => {
    assert.deepEqual(
      decideShortRunOutcome({
        ...base,
        state: "succeeded",
        taskTerminal: true,
        streamShouldClose: true,
        result: { kind: "short_candidate", ready: true, id: "artifact-1" },
      }),
      { kind: "succeeded", resultKind: "short_candidate", resultId: "artifact-1" },
    );
  });

  it("成功但产物未就绪时明确显示对账异常", () => {
    const decision = decideShortRunOutcome({
      ...base,
      state: "succeeded",
      taskTerminal: true,
      streamShouldClose: true,
    });

    assert.equal(decision.kind, "inconsistent");
    assert.equal(
      decideShortRunOutcome({
        ...base,
        state: "succeeded",
        taskTerminal: true,
        streamShouldClose: true,
        result: { kind: "short_candidate", ready: true, id: null },
      }).kind,
      "inconsistent",
    );
  });

  it("失败与状态冲突不会伪装成成功", () => {
    assert.equal(
      decideShortRunOutcome({
        ...base,
        state: "failed",
        code: "MODEL_FAILED",
        taskTerminal: true,
        streamShouldClose: true,
      }).kind,
      "failed",
    );
    assert.equal(
      decideShortRunOutcome({
        ...base,
        state: "inconsistent",
        code: "SHORT_MEDIUM_RESULT_MISSING",
        taskTerminal: true,
        streamShouldClose: true,
        reconciliationRequired: true,
      }).kind,
      "inconsistent",
    );
  });
});

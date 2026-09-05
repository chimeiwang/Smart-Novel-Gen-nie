import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { decideShortRunOutcome, decideShortRunStatus, type ShortRunStatus } from "../short-run-outcome";

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

  it("取消任务按失败型终态收敛并保留错误码", () => {
    assert.deepEqual(
      decideShortRunOutcome({
        ...base,
        state: "cancelled",
        code: "WRITING_RUN_CANCELLED",
        taskTerminal: true,
        streamShouldClose: true,
      }),
      { kind: "failed", code: "WRITING_RUN_CANCELLED" },
    );
  });
});

const v2 = {
  engineVersion: 2, runId: "short-run-1", taskId: "short-run-1", workflow: "short_medium",
  chapterId: "chapter-1", commandId: null, commandStatus: null, operation: "generate_manuscript",
  status: "completed", activeSteps: [], lastEventSequence: 8, revision: 3,
} as const;

describe("中短篇 V2 权威结果", () => {
  it("只使用精确候选引用，不把完成事件或普通Artifact猜成候选", () => {
    const candidate: ShortRunStatus = { ...v2, candidateVersionId: "candidate-1", artifact: {
      artifactId: "candidate-1", artifactRevision: 1, status: "awaiting_user", actionable: false,
    }, activeSteps: [] };
    assert.deepEqual(decideShortRunStatus(candidate), {
      kind: "succeeded", resultKind: "short_candidate", resultId: "candidate-1",
    });
    assert.equal(decideShortRunStatus({ ...candidate, candidateVersionId: "other" }).kind, "inconsistent");
    assert.equal(decideShortRunStatus({ ...candidate, candidateVersionId: undefined }).kind, "inconsistent");
  });

  it("完整检查报告不产生候选，缺少结果不能显示成功", () => {
    const report: ShortRunStatus = { ...v2, activeSteps: [], operation: "full_check", checkReport: { text: "完整检查😀\r\n" } };
    assert.equal(decideShortRunStatus(report).kind, "succeeded");
    assert.equal(decideShortRunStatus({ ...report, checkReport: undefined }).kind, "inconsistent");
    assert.equal(decideShortRunStatus({ ...report, checkReport: { summary: "不是完整报告" } }).kind, "inconsistent");
    assert.equal(decideShortRunStatus({ ...report, checkReport: { text: "" } }).kind, "inconsistent");
    assert.equal(decideShortRunStatus({ ...report, candidateVersionId: "candidate-1" }).kind, "inconsistent");
  });

  it("运行、取消和错误引擎业务身份分别收敛", () => {
    assert.equal(decideShortRunStatus({ ...v2, activeSteps: [], status: "running" }).kind, "continue");
    assert.equal(decideShortRunStatus({ ...v2, activeSteps: [], status: "cancelled" }).kind, "failed");
    assert.deepEqual(decideShortRunStatus({ ...v2, activeSteps: [], status: "failed",
      error: { errorCode: "MODEL_OUTCOME_UNKNOWN", outcomeUnknown: true } }), {
      kind: "failed", code: "MODEL_OUTCOME_UNKNOWN",
    });
    assert.equal(decideShortRunStatus({ ...v2, activeSteps: [], workflow: "long_serial" }).kind, "inconsistent");
    assert.equal(decideShortRunStatus({ ...v2, activeSteps: [], status: "waiting_user" }).kind, "inconsistent");
  });
});

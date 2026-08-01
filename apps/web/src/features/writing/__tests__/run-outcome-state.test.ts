import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  canLegacyPhaseUpdateProgress,
  createCompletionEffectGuard,
  mapLongRunOutcome,
  rememberRunOutcomeSignature,
  resolvePendingReviewAction,
} from "../run-outcome-state";

const base = {
  code: "TEST",
  taskTerminal: false,
  streamShouldClose: false,
  reconciliationRequired: false,
  currentCommand: null,
  result: { kind: "none" as const, ready: false, id: null },
  observedAt: "2026-08-01T12:00:00Z",
};

describe("长篇运行结果", () => {
  it("排队和运行中继续观察", () => {
    assert.deepEqual(mapLongRunOutcome({ ...base, state: "queued" }), {
      kind: "continue",
    });
    assert.deepEqual(mapLongRunOutcome({ ...base, state: "running" }), {
      kind: "continue",
    });
  });

  it("等待用户与成功映射到不同界面阶段", () => {
    assert.deepEqual(
      mapLongRunOutcome({
        ...base,
        state: "waiting_user",
        streamShouldClose: true,
        result: { kind: "review_artifact", ready: true, id: "artifact-1" },
      }),
      { kind: "waiting_user", artifactId: "artifact-1" },
    );
    assert.deepEqual(
      mapLongRunOutcome({
        ...base,
        state: "succeeded",
        taskTerminal: true,
        streamShouldClose: true,
      }),
      { kind: "succeeded" },
    );
  });

  it("失败和对账冲突均不能显示成功", () => {
    assert.deepEqual(
      mapLongRunOutcome({
        ...base,
        state: "failed",
        code: "MODEL_FAILED",
        taskTerminal: true,
        streamShouldClose: true,
      }),
      { kind: "failed", code: "MODEL_FAILED" },
    );
    assert.deepEqual(
      mapLongRunOutcome({
        ...base,
        state: "inconsistent",
        code: "REVIEW_ARTIFACT_MISSING",
        streamShouldClose: true,
        reconciliationRequired: true,
      }),
      { kind: "inconsistent", code: "REVIEW_ARTIFACT_MISSING" },
    );
  });

  it("脱离当前会话的草案操作也只按权威 outcome 收敛", () => {
    assert.equal(
      resolvePendingReviewAction(
        "revise",
        mapLongRunOutcome({
          ...base,
          state: "waiting_user",
          streamShouldClose: true,
          result: { kind: "review_artifact", ready: true, id: "artifact-2" },
        }),
      ),
      "succeeded",
    );
    assert.equal(
      resolvePendingReviewAction(
        "approve",
        mapLongRunOutcome({
          ...base,
          state: "succeeded",
          taskTerminal: true,
          streamShouldClose: true,
        }),
      ),
      "succeeded",
    );
    assert.equal(
      resolvePendingReviewAction(
        "discard",
        mapLongRunOutcome({
          ...base,
          state: "failed",
          code: "APPLY_FAILED",
          taskTerminal: true,
          streamShouldClose: true,
        }),
      ),
      "failed",
    );
    assert.equal(
      resolvePendingReviewAction(
        "approve",
        mapLongRunOutcome({ ...base, state: "running" }),
      ),
      null,
    );
  });

  it("终态 outcome 后出现 legacy 帧时强制重新应用权威状态", () => {
    let signature = rememberRunOutcomeSignature("run_outcome", "terminal");
    assert.equal(signature, "terminal");

    signature = rememberRunOutcomeSignature("completed", signature);

    assert.equal(signature, null);
    assert.notEqual(signature, "terminal");
  });

  it("legacy 阶段事件不能直接写入完成或失败生命周期", () => {
    assert.equal(canLegacyPhaseUpdateProgress("discussing"), true);
    assert.equal(canLegacyPhaseUpdateProgress("generating"), true);
    assert.equal(canLegacyPhaseUpdateProgress("completed"), false);
    assert.equal(canLegacyPhaseUpdateProgress("error"), false);
  });

  it("同一任务的同一成功 outcome 只触发一次完成副作用", () => {
    const guard = createCompletionEffectGuard();
    const outcome = {
      ...base,
      state: "succeeded" as const,
      code: "WRITING_RUN_SUCCEEDED",
      taskTerminal: true,
      streamShouldClose: true,
      currentCommand: {
        id: "command-1",
        kind: "start",
        status: "succeeded" as const,
        updatedAt: "2026-08-01T12:00:00Z",
      },
    };

    assert.equal(guard.claim("task-1", outcome), true);
    assert.equal(guard.claim("task-1", outcome), false);
    assert.equal(guard.claim("task-2", outcome), true);
  });
});

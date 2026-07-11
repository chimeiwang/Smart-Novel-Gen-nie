/**
 * 工作流状态契约测试。
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/workflow.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  ChapterStatusSchema,
  WorkflowStepStatusSchema,
  WritingTaskPhaseSchema,
} from "../workflow";

describe("workflow contract", () => {
  it("写作任务阶段包含等待用户审核草案", () => {
    assert.equal(WritingTaskPhaseSchema.safeParse("awaiting_user_review").success, true);
  });

  it("章节状态保持小而明确", () => {
    assert.deepEqual(ChapterStatusSchema.options, ["drafting", "review", "completed"]);
  });

  it("工作流步骤状态不接受任意字符串", () => {
    assert.equal(WorkflowStepStatusSchema.safeParse("completed").success, true);
    assert.equal(WorkflowStepStatusSchema.safeParse("paused").success, false);
  });
});

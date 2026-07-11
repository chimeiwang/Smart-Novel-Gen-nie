import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildAuthorChapterDraftInstruction,
  buildAuthorSystemPrompt,
  getInvalidWritingOutlineMessage,
  shouldBlockForMissingApprovedBeatPlan,
} from "../nodes/author-node";
import type { WritingState } from "../state";

function createInput(overrides: Partial<Pick<WritingState, "currentOperation" | "novelData" | "userMessage">> = {}) {
  return {
    currentOperation: {
      kind: "write_chapter",
    } as WritingState["currentOperation"],
    novelData: {
      approvedBeatPlan: null,
    } as WritingState["novelData"],
    userMessage: "请基于已批准章节计划生成本章正文草案",
    ...overrides,
  };
}

describe("approved Beat Plan preGuard", () => {
  it("blocks an explicit approved Beat Plan request when no plan exists", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput()), true);
  });

  it("allows ordinary writing requests without an approved Beat Plan", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({ userMessage: "请生成本章正文草案" })), false);
  });

  it("does not mistake an explicit Beat Plan opt-out for a requirement", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({ userMessage: "不需要 Beat Plan，直接生成本章正文草案" })), false);
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({ userMessage: "即使没有已批准章节计划也继续写" })), false);
  });

  it("allows the explicit request when an approved Beat Plan exists", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({
      novelData: {
        approvedBeatPlan: { id: "plan-1" },
      } as WritingState["novelData"],
    })), false);
  });

  it("does not block unrelated operations", () => {
    assert.equal(shouldBlockForMissingApprovedBeatPlan(createInput({
      currentOperation: { kind: "review_chapter" } as WritingState["currentOperation"],
    })), false);
  });
});

describe("作家局部大纲 preGuard", () => {
  it("当前章无映射时在模型调用前阻断", () => {
    const message = getInvalidWritingOutlineMessage(createInput({
      novelData: {
        approvedBeatPlan: null,
        writingOutlineContext: { status: "unmapped" },
      } as WritingState["novelData"],
    }));
    assert.match(message ?? "", /没有唯一可用的大纲章节组映射/);
  });

  it("当前章匹配多个章节组时在模型调用前阻断", () => {
    const message = getInvalidWritingOutlineMessage(createInput({
      novelData: {
        approvedBeatPlan: null,
        writingOutlineContext: { status: "ambiguous" },
      } as WritingState["novelData"],
    }));
    assert.match(message ?? "", /系统不会随机选择/);
  });
});

describe("作家提示词瘦身", () => {
  it("主提示词保留核心写作目标但移除重复流程清单", () => {
    const prompt = buildAuthorSystemPrompt();

    assert.ok(prompt.length < 800);
    assert.match(prompt, /目标、阻力、变化、代价或钩子/);
    assert.doesNotMatch(prompt, /## 行动循环/);
    assert.doesNotMatch(prompt, /## 工具使用策略/);
    assert.doesNotMatch(prompt, /## 写作纪律/);
    assert.doesNotMatch(prompt, /单轮最多查/);
    assert.doesNotMatch(prompt, /如果没有已批准 Beat Plan/);
  });

  it("正文草案规则集中在短指令中且避免污染草案正文", () => {
    const instruction = buildAuthorChapterDraftInstruction({ hasApprovedBeatPlan: false });

    assert.ok(instruction.length < 360);
    assert.match(instruction, /begin_artifact_output/);
    assert.match(instruction, /ARTIFACT_OUTPUT_START\/END/);
    assert.match(instruction, /不放章节标题/);
    assert.match(instruction, /ARTIFACT_OUTPUT_END 之后/);
    assert.doesNotMatch(instruction, /结构化大纲/);
    assert.doesNotMatch(instruction, /outlineAdjustments/);
  });
});

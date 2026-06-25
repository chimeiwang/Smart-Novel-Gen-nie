/**
 * CreativeOperation 契约测试。
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/creative-operation.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  CREATIVE_OPERATION_KINDS,
  CREATIVE_OPERATION_LABELS,
  CreativeOperationSchema,
  createFallbackOperation,
  getCreativeOperationLabel,
  getDefaultOperationForAgent,
} from "../creative-operation";

describe("CreativeOperation contract", () => {
  it("支持章节生成操作", () => {
    const result = CreativeOperationSchema.safeParse({
      kind: "write_chapter",
      targetType: "chapter",
      userGoal: "根据大纲写第三章",
      primaryAgent: "写作",
      reviewers: ["校验", "编辑"],
      outputKind: "chapter_text",
      requiresArtifact: false,
      requiresUserApproval: false,
      confidence: 0.91,
      reasoning: "用户明确要求生成正文。",
    });

    assert.equal(result.success, true);
  });

  it("@设定 默认映射到设定草案操作", () => {
    assert.deepEqual(
      getDefaultOperationForAgent("设定", "@设定 给主角补充宗门背景"),
      {
        kind: "revise_lore",
        targetType: "lore",
        userGoal: "@设定 给主角补充宗门背景",
        primaryAgent: "设定",
        reviewers: [],
        outputKind: "lore_proposal",
        requiresArtifact: true,
        requiresUserApproval: true,
        confidence: 0.72,
        reasoning: "用户使用 @Agent 前缀，按该 Agent 的默认创作操作处理。",
      }
    );
  });

  it("提供低置信度回退操作", () => {
    const operation = createFallbackOperation("随便聊聊");
    assert.equal(operation.kind, "answer_question");
    assert.equal(operation.primaryAgent, "编辑");
    assert.equal(operation.requiresArtifact, false);
  });

  it("提供展示标签", () => {
    assert.equal(getCreativeOperationLabel("sync_lore"), "同步设定");
  });

  it("每个创作操作都有中文名", () => {
    for (const kind of CREATIVE_OPERATION_KINDS) {
      const label = CREATIVE_OPERATION_LABELS[kind];
      assert.ok(label, `缺少中文名: ${kind}`);
      assert.equal(/[a-z_]/.test(label), false, `中文名不能暴露内部变量: ${label}`);
    }
    assert.equal(getCreativeOperationLabel("write_chapter"), "生成正文草案");
    assert.equal(getCreativeOperationLabel("rewrite_scene"), "改写场景草案");
  });
});

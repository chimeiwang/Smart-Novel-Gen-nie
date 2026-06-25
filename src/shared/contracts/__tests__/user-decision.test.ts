/**
 * 用户决策契约测试。
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/user-decision.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  ResumeWritingRequestSchema,
  UserDecisionSchema,
  createArtifactReviewInterrupt,
  normalizeResumeDecision,
} from "../user-decision";

describe("UserDecision contract", () => {
  it("支持待审核草案决策", () => {
    const result = UserDecisionSchema.safeParse({
      type: "artifact_review",
      artifactId: "artifact-1",
      decision: "revise",
      userMessage: "补强第二章爽点",
    });

    assert.equal(result.success, true);
  });

  it("支持应用草案时携带前端编辑后的正文", () => {
    const result = UserDecisionSchema.safeParse({
      type: "artifact_review",
      artifactId: "artifact-1",
      decision: "approve",
      editedContent: "编辑后的草案正文",
    });

    assert.equal(result.success, true);
    if (result.success) {
      assert.equal(result.data.type, "artifact_review");
      assert.equal(result.data.editedContent, "编辑后的草案正文");
    }
  });

  it("把旧 resume 参数归一化为 artifact_review 决策", () => {
    assert.deepEqual(
      normalizeResumeDecision({
        artifactId: "artifact-1",
        decision: "approve",
      }),
      {
        type: "artifact_review",
        artifactId: "artifact-1",
        decision: "approve",
        userMessage: undefined,
      }
    );
  });

  it("归一化 userDecision 时保留 editedContent", () => {
    assert.deepEqual(
      normalizeResumeDecision({
        userDecision: {
          type: "artifact_review",
          artifactId: "artifact-1",
          decision: "approve",
          editedContent: "编辑后的草案正文",
        },
      }),
      {
        type: "artifact_review",
        artifactId: "artifact-1",
        decision: "approve",
        editedContent: "编辑后的草案正文",
      }
    );
  });

  it("归一化 userDecision 时保留结构化变更选择", () => {
    assert.deepEqual(
      normalizeResumeDecision({
        userDecision: {
          type: "artifact_review",
          artifactId: "artifact-1",
          decision: "approve",
          selectedUpdateRefs: [
            { section: "characters", index: 0 },
            { section: "outlineContent" },
          ],
        },
      }),
      {
        type: "artifact_review",
        artifactId: "artifact-1",
        decision: "approve",
        selectedUpdateRefs: [
          { section: "characters", index: 0 },
          { section: "outlineContent" },
        ],
      }
    );
  });

  it("把普通用户消息归一化为 continue_chat 决策", () => {
    assert.deepEqual(
      normalizeResumeDecision({ userMessage: "@剧情 检查一下节奏" }),
      {
        type: "continue_chat",
        userMessage: "@剧情 检查一下节奏",
      }
    );
  });

  it("resume 请求可以携带当前写作会话 ID 用于绑定校验", () => {
    const result = ResumeWritingRequestSchema.safeParse({
      taskId: "task-1",
      writingSessionId: "session-1",
      userMessage: "继续写",
    });

    assert.equal(result.success, true);
    if (result.success) {
      assert.equal(result.data.writingSessionId, "session-1");
    }
  });

  it("生成统一 interrupt payload", () => {
    assert.deepEqual(
      createArtifactReviewInterrupt({
        artifactId: "artifact-1",
        summary: "编辑复审通过",
        content: "可以应用。",
      }),
      {
        type: "user_input_required",
        decisionType: "artifact_review",
        artifactId: "artifact-1",
        summary: "编辑复审通过",
        content: "可以应用。",
        artifact: undefined,
        allowedDecisions: ["approve", "discard", "revise"],
      }
    );
  });
});

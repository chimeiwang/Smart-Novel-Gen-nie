/**
 * 创作操作定义测试。
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { CREATIVE_OPERATION_KINDS, getCreativeOperationLabel } from "@/shared/contracts/creative-operation";
import { assertOperationDefinitionsComplete, getOperationDefinition } from "../operation-definition";

describe("创作操作定义", () => {
  it("覆盖全部创作操作并保持中文名一致", () => {
    assert.doesNotThrow(() => assertOperationDefinitionsComplete());
    for (const kind of CREATIVE_OPERATION_KINDS) {
      assert.equal(getOperationDefinition(kind).label, getCreativeOperationLabel(kind));
    }
  });

  it("正文相关操作必须生成待审核草案", () => {
    const write = getOperationDefinition("write_chapter");
    assert.equal(write.label, "生成正文草案");
    assert.equal(write.requiresArtifact, true);
    assert.equal(write.requiresUserApproval, true);
    assert.equal(write.textArtifactKind, "chapter_draft");

    const rewrite = getOperationDefinition("rewrite_scene");
    assert.equal(rewrite.label, "改写场景草案");
    assert.equal(rewrite.requiresArtifact, true);
    assert.equal(rewrite.requiresUserApproval, true);
    assert.equal(rewrite.textArtifactKind, "chapter_draft");
  });

  it("回答问题不生成待审核草案", () => {
    const answer = getOperationDefinition("answer_question");
    assert.equal(answer.label, "回答问题");
    assert.equal(answer.requiresArtifact, false);
    assert.equal(answer.artifactPolicy, "none");
  });

  it("创建大纲走结构化更新草案", () => {
    const createOutline = getOperationDefinition("create_outline");
    assert.equal(createOutline.label, "创建大纲");
    assert.equal(createOutline.requiresArtifact, true);
    assert.equal(createOutline.requiresUserApproval, true);
    assert.equal(createOutline.artifactPolicy, "agent_updates");
    assert.equal(createOutline.textArtifactKind, undefined);
  });
});

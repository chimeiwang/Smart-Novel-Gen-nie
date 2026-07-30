import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  canRunDocumentAction,
  canStartSelectionEdit,
  candidateAutomaticallyAdopted,
  requiresConfirmation,
  versionActionForInspection,
} from "../short-workspace-state";

describe("中短篇工作区门禁", () => {
  it("工作稿未保存时禁止启动 Agent、采用和恢复", () => {
    for (const state of ["waiting", "saving", "failed", "conflict"] as const) {
      assert.equal(canRunDocumentAction(state), false);
    }
    assert.equal(canRunDocumentAction("saved"), true);
  });

  it("提交、采用和恢复都需要独立确认", () => {
    assert.equal(requiresConfirmation("submit"), true);
    assert.equal(requiresConfirmation("adopt"), true);
    assert.equal(requiresConfirmation("restore"), true);
  });

  it("Agent 候选永不自动采用", () => {
    assert.equal(candidateAutomaticallyAdopted, false);
  });

  it("选区修改同时要求非空选区和非空修改要求", () => {
    assert.equal(canStartSelectionEdit(true, "加强冲突"), true);
    assert.equal(canStartSelectionEdit(true, "  "), false);
    assert.equal(canStartSelectionEdit(false, "加强冲突"), false);
  });

  it("过期候选使用恢复语义，只有当前基础上的候选可以采用", () => {
    assert.equal(versionActionForInspection({
      versionId: "candidate-2",
      status: "awaiting_user",
      baseVersionId: "version-1",
      currentVersionId: "version-1",
    }), "adopt");
    assert.equal(versionActionForInspection({
      versionId: "candidate-1",
      status: "awaiting_user",
      baseVersionId: "version-0",
      currentVersionId: "version-1",
    }), "restore");
  });
});

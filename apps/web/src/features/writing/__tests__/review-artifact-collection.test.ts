import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  collectAwaitingReviewTaskIds,
  mergeActionableReviewArtifacts,
} from "../review-artifact-collection";

describe("章节待审核产物收集", () => {
  it("从多个会话的 currentTask 与 lastTask 收集并去重待审核任务", () => {
    assert.deepEqual(collectAwaitingReviewTaskIds([
      {
        currentTask: { id: "task-1", hasAwaitingReviewArtifact: true },
        lastTask: { id: "task-2", hasAwaitingReviewArtifact: true },
      },
      {
        currentTask: { id: "task-1", hasAwaitingReviewArtifact: true },
        lastTask: { id: "task-3", hasAwaitingReviewArtifact: false },
      },
      { currentTask: null, lastTask: null },
    ]), ["task-1", "task-2"]);
  });

  it("只保留可操作产物并按 artifactKey 去重，后到状态覆盖旧状态", () => {
    const merged = mergeActionableReviewArtifacts([
      { id: "artifact-old", artifactKey: "chapter:1", status: "awaiting_user", summary: "旧" },
      { id: "artifact-applied", artifactKey: "chapter:2", status: "applied", summary: "已应用" },
    ], [
      { id: "artifact-new", artifactKey: "chapter:1", status: "awaiting_user", summary: "新" },
      { id: "artifact-3", artifactKey: null, status: "awaiting_user", summary: "其他" },
    ]);

    assert.deepEqual(merged.map((artifact) => artifact.id), ["artifact-new", "artifact-3"]);
    assert.equal(merged[0].summary, "新");
  });
});

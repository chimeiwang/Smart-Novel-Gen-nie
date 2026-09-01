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

  it("只保留可操作产物并按产物 id 去重，不折叠不同任务的同 key 产物", () => {
    const merged = mergeActionableReviewArtifacts([
      { id: "artifact-old", artifactKey: "chapter:1", status: "awaiting_user", summary: "旧" },
      { id: "artifact-applied", artifactKey: "chapter:2", status: "applied", summary: "已应用" },
    ], [
      { id: "artifact-new", artifactKey: "chapter:1", status: "awaiting_user", summary: "新" },
      { id: "artifact-old", artifactKey: "chapter:1", status: "awaiting_user", summary: "旧产物新状态" },
      { id: "artifact-3", artifactKey: null, status: "awaiting_user", summary: "其他" },
    ]);

    assert.deepEqual(merged.map((artifact) => artifact.id), [
      "artifact-old",
      "artifact-new",
      "artifact-3",
    ]);
    assert.equal(merged[0].summary, "旧产物新状态");
  });

  it("同一 revision 的完整详情不会被后到的列表摘要覆盖", () => {
    const merged = mergeActionableReviewArtifacts([
      {
        id: "artifact-1",
        status: "awaiting_user",
        revision: 3,
        detailLoaded: true,
        summary: "完整详情",
      },
    ], [
      {
        id: "artifact-1",
        status: "awaiting_user",
        revision: 3,
        detailLoaded: false,
        summary: "列表摘要",
      },
    ]);

    assert.equal(merged[0].detailLoaded, true);
    assert.equal(merged[0].summary, "完整详情");
  });
});

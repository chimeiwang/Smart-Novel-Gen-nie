import assert from "node:assert/strict";
import test from "node:test";

import type { components } from "@inkforge/api-client";
import {
  applySavedOutlineToAggregate,
  createOutlineEditorBase,
  shouldAdoptAggregateOutline,
} from "../short-story/short-story-outline-lifecycle";

type ShortStoryArtifact = components["schemas"]["ShortStoryArtifactResponse"];
type ReviewArtifact = components["schemas"]["ReviewArtifactResponse"];

function outlineArtifact(revision: number, sectionId = "section-1"): ShortStoryArtifact {
  return {
    id: "outline-1",
    novelId: "novel-1",
    chapterId: "chapter-1",
    taskId: "task-1",
    workflowRunId: null,
    artifactKey: "outline",
    kind: "outline_draft",
    status: "awaiting_user",
    title: "完整大纲",
    summary: "大纲",
    payload: {
      kind: "outline_draft",
      storyLengthProfile: "short_medium",
      originalInspiration: "一个陌生人敲门",
      corePremise: "身份交换",
      anchors: { mustKeep: [], confirmed: [], avoid: [] },
      sections: [{ id: sectionId, title: "开端", events: "陌生人敲门" }],
      content: "完整大纲",
      changeSummary: "修改",
      anchorChanges: [],
    },
    diff: null,
    createdByAgent: "剧情",
    updatedByAgent: "剧情",
    reviewerAgent: null,
    revision,
    evaluations: [],
    createdAt: "2026-07-01T00:00:00Z",
    updatedAt: "2026-07-01T00:00:00Z",
  };
}

test("dirty 编辑器不会因后台 aggregate 升版偷换保存基线", () => {
  const base = createOutlineEditorBase(outlineArtifact(3));
  const latest = outlineArtifact(4);

  assert.deepEqual(base, { artifactId: "outline-1", revision: 3 });
  assert.equal(shouldAdoptAggregateOutline({ dirty: true, base, next: latest }), false);
  assert.equal(shouldAdoptAggregateOutline({ dirty: false, base, next: latest }), true);
});

test("PUT 返回的大纲立即成为 aggregate 权威版本并带回新增节稳定 ID", () => {
  const aggregate: components["schemas"]["ShortStoryArtifactsResponse"] = {
    outline: outlineArtifact(1, "section-1"),
    chapterDraft: null,
    latestTask: null,
    workflowSession: null,
  };
  const saved: ReviewArtifact = {
    ...outlineArtifact(2, "server-new-section"),
    kind: "outline_draft",
  };

  const next = applySavedOutlineToAggregate(aggregate, saved);

  assert.equal(next.outline?.revision, 2);
  assert.equal(next.outline?.payload.kind, "outline_draft");
  assert.equal(next.outline?.payload.sections[0].id, "server-new-section");
});


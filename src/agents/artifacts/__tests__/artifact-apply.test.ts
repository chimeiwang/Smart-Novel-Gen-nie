import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { filterAgentUpdatesBySelection, resolveReviewArtifactApplyTarget } from "../artifact-apply";

describe("artifact apply", () => {
  it("allows outline draft artifacts to update the formal outline text", () => {
    assert.equal(
      resolveReviewArtifactApplyTarget({
        kind: "outline_draft",
        content: "第一卷：遗产线索与第一次反转",
      }),
      "outline_content"
    );
  });

  it("does not apply revision briefs as formal novel data", () => {
    assert.equal(
      resolveReviewArtifactApplyTarget({
        kind: "revision_brief",
        content: "请强化前三章的钩子和主角行动动机。",
      }),
      null
    );
  });

  it("allows chapter drafts to update chapter content after user approval", () => {
    assert.equal(
      resolveReviewArtifactApplyTarget({
        kind: "chapter_draft",
        content: "第一章正文草案",
      }),
      "chapter_content"
    );
    assert.equal(
      resolveReviewArtifactApplyTarget({
        kind: "chapter_content",
        content: "第一章正文草案",
      }),
      "chapter_content"
    );
  });

  it("allows beat plan drafts to create approved chapter beat plans after user approval", () => {
    assert.equal(
      resolveReviewArtifactApplyTarget({
        kind: "beat_plan_draft",
        content: "第一章 Beat Plan 草案",
      }),
      "beat_plan"
    );
    assert.equal(
      resolveReviewArtifactApplyTarget({
        kind: "beat_plan",
        beatPlan: {
          title: "第一章 Beat Plan",
          summary: "主角发现线索并付出代价。",
          chapterGoal: "让主角进入主线案件",
          sceneBeats: [
            {
              order: 1,
              goal: "发现线索",
              conflict: "线索被对手抢先封锁",
              characters: ["主角"],
              estimatedWords: 1200,
              acceptanceCriteria: "主角做出主动选择",
            },
          ],
        },
      }),
      "beat_plan"
    );
  });

  it("filters agent updates by selected item refs before applying", () => {
    assert.deepEqual(
      filterAgentUpdatesBySelection(
        {
          characters: [
            { action: "create", name: "老钱" },
            { action: "create", name: "老赵" },
          ],
          locations: [
            { action: "create", name: "藏书阁暗室" },
          ],
          outlineContent: "第一卷总纲",
        },
        [
          { section: "characters", index: 1 },
          { section: "outlineContent" },
        ]
      ),
      {
        characters: [
          { action: "create", name: "老赵" },
        ],
        outlineContent: "第一卷总纲",
      }
    );
  });

  it("returns no updates when the user selects nothing", () => {
    assert.deepEqual(
      filterAgentUpdatesBySelection(
        {
          items: [
            { action: "create", name: "玉简残片" },
          ],
        },
        []
      ),
      {}
    );
  });
});

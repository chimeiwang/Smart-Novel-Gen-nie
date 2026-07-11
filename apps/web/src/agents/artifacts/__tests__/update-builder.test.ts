import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  buildOutlineTreeUpdate,
  mergeAgentUpdates,
  validateAgentUpdatesForReview,
} from "../update-builder";

describe("update builder", () => {
  it("expands a nested outline tree into strict outlineAdjustments", () => {
    const update = buildOutlineTreeUpdate({
      artifactKey: "outline-builder-1",
      batchIndex: 0,
      mode: "replace",
      stages: [
        {
          title: "第一阶段 鹿溪镇暗流",
          chapterStartOrder: 1,
          chapterEndOrder: 15,
          plotUnits: [
            {
              title: "鹿溪镇的暗流",
              chapterStartOrder: 1,
              chapterEndOrder: 8,
              chapterGroups: [
                {
                  title: "裂痕",
                  chapterStartOrder: 1,
                  chapterEndOrder: 3,
                  estimatedWordCount: 30000,
                },
              ],
            },
          ],
        },
      ],
    });

    assert.deepEqual(update.outlineAdjustments, [
      {
        action: "create",
        kind: "stage",
        title: "第一阶段 鹿溪镇暗流",
        chapterStartOrder: 1,
        chapterEndOrder: 15,
        clientKey: "outline-builder-1-b0-s1",
      },
      {
        action: "create",
        kind: "plot_unit",
        title: "鹿溪镇的暗流",
        chapterStartOrder: 1,
        chapterEndOrder: 8,
        clientKey: "outline-builder-1-b0-s1-u1",
        parentKey: "outline-builder-1-b0-s1",
      },
      {
        action: "create",
        kind: "chapter_group",
        title: "裂痕",
        chapterStartOrder: 1,
        chapterEndOrder: 3,
        estimatedWordCount: 30000,
        clientKey: "outline-builder-1-b0-s1-u1-g1",
        parentKey: "outline-builder-1-b0-s1-u1",
      },
    ]);
    assert.deepEqual(validateAgentUpdatesForReview(update), []);
  });

  it("keeps multiple outline tree batches unique in one artifact", () => {
    const first = buildOutlineTreeUpdate({
      artifactKey: "outline-builder-1",
      batchIndex: 0,
      mode: "replace",
      stages: [{ title: "第一阶段", chapterStartOrder: 1, chapterEndOrder: 15, plotUnits: [{ title: "遗产线索", chapterStartOrder: 1, chapterEndOrder: 15 }] }],
    });
    const second = buildOutlineTreeUpdate({
      artifactKey: "outline-builder-1",
      batchIndex: 1,
      mode: "replace",
      stages: [{ title: "第二阶段", chapterStartOrder: 16, chapterEndOrder: 30, plotUnits: [{ title: "宗门裂痕", chapterStartOrder: 16, chapterEndOrder: 30 }] }],
    });

    const merged = mergeAgentUpdates(first, second);

    const keys = (merged.outlineAdjustments ?? [])
      .map((item) => item.clientKey)
      .filter((key): key is string => Boolean(key));
    assert.deepEqual(keys, [
      "outline-builder-1-b0-s1",
      "outline-builder-1-b0-s1-u1",
      "outline-builder-1-b1-s1",
      "outline-builder-1-b1-s1-u1",
    ]);
    assert.deepEqual(validateAgentUpdatesForReview(merged), []);
  });
});

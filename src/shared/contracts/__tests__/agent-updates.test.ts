/**
 * AgentUpdates 契约测试。
 *
 * 运行方式：npx tsx --test src/shared/contracts/__tests__/agent-updates.test.ts
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  AgentUpdatesProposalSchema,
  AgentUpdatesSchema,
  OutlineNodeKindSchema,
  sanitizeAgentUpdates,
} from "../agent-updates";

describe("AgentUpdates contract", () => {
  it("大纲节点类型只允许三层长篇结构", () => {
    assert.deepEqual(OutlineNodeKindSchema.options, ["stage", "plot_unit", "chapter_group"]);
    assert.equal(OutlineNodeKindSchema.safeParse("arc").success, false);
  });

  it("outlineAdjustments 接受并保留 kind、clientKey、parentKey", () => {
    const updates = {
      outlineContent: "全书总纲：主角离乡，追查旧案。",
      outlineAdjustments: [
        {
          action: "create",
          clientKey: "stage-1",
          title: "第一卷 离开青石镇",
          kind: "stage",
          content: "主角离开故乡，进入更大地图。",
        },
        {
          action: "create",
          clientKey: "unit-1",
          parentKey: "stage-1",
          title: "假案引路",
          kind: "plot_unit",
        },
      ],
    };

    assert.equal(AgentUpdatesSchema.safeParse(updates).success, true);
    assert.deepEqual(sanitizeAgentUpdates(updates), updates);
  });

  it("创建结构化大纲节点时要求 kind、标题和合法父子引用", () => {
    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [{ action: "create", title: "缺类型节点", chapterStartOrder: 1, chapterEndOrder: 10 }],
      }).success,
      false
    );

    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [{ action: "create", kind: "stage", title: "第一阶段", parentKey: "root", chapterStartOrder: 1, chapterEndOrder: 10 }],
      }).success,
      false
    );

    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [{ action: "create", kind: "plot_unit", title: "缺父级剧情单元", chapterStartOrder: 1, chapterEndOrder: 10 }],
      }).success,
      false
    );

    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [
          { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "unit-1", parentKey: "stage-1", title: "剧情单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "group-1", parentKey: "unit-1", title: "章节组", kind: "chapter_group", chapterStartOrder: 1, chapterEndOrder: 5 },
        ],
      }).success,
      true
    );
  });

  it("字数字段是可选辅助字段，不影响结构化大纲创建", () => {
    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [
          { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "unit-1", parentKey: "stage-1", title: "剧情单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "group-1", parentKey: "unit-1", title: "章节组", kind: "chapter_group", chapterStartOrder: 1, chapterEndOrder: 5 },
        ],
      }).success,
      true
    );
  });

  it("同批 parentKey 必须能解析到唯一 clientKey", () => {
    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [
          { action: "create", clientKey: "unit-1", parentKey: "missing-stage", title: "剧情单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 10 },
        ],
      }).success,
      false
    );

    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [
          { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "stage-1", title: "重复阶段", kind: "stage", chapterStartOrder: 11, chapterEndOrder: 20 },
        ],
      }).success,
      false
    );
  });

  it("同批 parentKey 必须指向合法父级类型", () => {
    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [
          { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "group-1", parentKey: "stage-1", title: "章节组", kind: "chapter_group", chapterStartOrder: 1, chapterEndOrder: 5 },
        ],
      }).success,
      false
    );

    assert.equal(
      AgentUpdatesProposalSchema.safeParse({
        outlineAdjustments: [
          { action: "create", clientKey: "stage-1", title: "第一阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "unit-1", parentKey: "stage-1", title: "剧情单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 10 },
          { action: "create", clientKey: "group-1", parentKey: "unit-1", title: "章节组", kind: "chapter_group", chapterStartOrder: 1, chapterEndOrder: 5 },
        ],
      }).success,
      true
    );
  });

  it("outlineAdjustments 拒绝非法 kind", () => {
    const updates = {
      outlineAdjustments: [
        {
          action: "create",
          title: "第一条人物线",
          kind: "character_arc",
        },
      ],
    };

    assert.equal(AgentUpdatesProposalSchema.safeParse(updates).success, false);
  });

  it("AgentUpdatesSchema 保持历史草案兼容，严格规则只用于 proposal 入口", () => {
    const legacyUpdates = {
      outlineAdjustments: [
        { action: "create", title: "旧版大纲节点" },
      ],
    };

    assert.equal(AgentUpdatesSchema.safeParse(legacyUpdates).success, true);
    assert.equal(AgentUpdatesProposalSchema.safeParse(legacyUpdates).success, false);
  });
});

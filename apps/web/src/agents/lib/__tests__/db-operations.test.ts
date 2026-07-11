/**
 * 数据库操作测试。
 *
 * 运行方式：npx tsx --test src/agents/lib/__tests__/db-operations.test.ts
 */

import { afterEach, describe, it } from "node:test";
import assert from "node:assert/strict";
import { prisma } from "@/shared/db/prisma";
import { executeUpdates } from "../db-operations";

type MockOutlineNode = {
  id: string;
  novelId: string;
  parentId: string | null;
  title: string;
  content: string | null;
  kind: "stage" | "plot_unit" | "chapter_group";
  status: "planned" | "in_progress" | "completed" | "skipped";
  order: number;
  estimatedWordCount: number | null;
  actualWordCount: number | null;
  chapterStartOrder: number | null;
  chapterEndOrder: number | null;
};

function matchesWhere(node: MockOutlineNode, where: Record<string, unknown>): boolean {
  return Object.entries(where).every(([key, value]) => {
    const actual = node[key as keyof MockOutlineNode];
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const condition = value as { not?: unknown; lte?: number; gte?: number; in?: unknown[] };
      if (condition.not !== undefined && actual === condition.not) return false;
      if (condition.lte !== undefined && (typeof actual !== "number" || actual > condition.lte)) return false;
      if (condition.gte !== undefined && (typeof actual !== "number" || actual < condition.gte)) return false;
      if (condition.in && !condition.in.includes(actual)) return false;
      return true;
    }
    return actual === value;
  });
}

const originalFindUnique = prisma.writingTask.findUnique.bind(prisma.writingTask);
const originalUpdate = prisma.writingTask.update.bind(prisma.writingTask);
const originalTransaction = prisma.$transaction.bind(prisma);

function installOutlineMock(seed: MockOutlineNode[]) {
  const nodes = [...seed];
  let outline: { id: string; novelId: string; content: string } | null = null;
  const createdData: unknown[] = [];
  const updatedData: unknown[] = [];

  Object.assign(prisma.writingTask, {
    findUnique: async () => ({ id: "task-1", novelId: "novel-1" }),
    update: async () => ({ id: "task-1" }),
  });

  Object.assign(prisma, {
    $transaction: async (callback: (tx: unknown) => Promise<void>) => {
      const tx = {
        outline: {
          findUnique: async ({ where }: { where: { novelId: string } }) =>
            outline?.novelId === where.novelId ? outline : null,
          upsert: async ({
            where,
            create,
            update,
          }: {
            where: { novelId: string };
            create: { novelId: string; content: string };
            update: { content: string };
          }) => {
            if (outline?.novelId === where.novelId) {
              outline = { ...outline, content: update.content };
            } else {
              outline = { id: "outline-1", ...create };
            }
            return outline;
          },
        },
        outlineNode: {
          count: async ({ where }: { where: Partial<MockOutlineNode> }) =>
            nodes.filter((node) => matchesWhere(node, where)).length,
          findFirst: async ({ where, select }: { where: Record<string, unknown>; select?: Record<string, boolean> }) => {
            const node = nodes.find((item) => matchesWhere(item, where));
            if (!node) return null;
            if (!select) return node;
            return Object.fromEntries(Object.keys(select).map((key) => [key, node[key as keyof MockOutlineNode]]));
          },
          findMany: async ({ where, take }: { where: Record<string, unknown>; take?: number }) =>
            nodes.filter((item) => matchesWhere(item, where)).slice(0, take),
          create: async ({ data }: { data: Omit<MockOutlineNode, "id"> }) => {
            createdData.push(data);
            const node = { id: "created-" + createdData.length, ...data };
            nodes.push(node);
            return node;
          },
          update: async ({ where, data }: { where: { id: string }; data: Partial<MockOutlineNode> }) => {
            updatedData.push(data);
            const index = nodes.findIndex((node) => node.id === where.id);
            assert.notEqual(index, -1);
            nodes[index] = { ...nodes[index], ...data };
            return nodes[index];
          },
          delete: async ({ where }: { where: { id: string } }) => {
            const index = nodes.findIndex((node) => node.id === where.id);
            if (index >= 0) nodes.splice(index, 1);
            return {};
          },
          deleteMany: async ({ where }: { where: Record<string, unknown> }) => {
            const before = nodes.length;
            for (let index = nodes.length - 1; index >= 0; index -= 1) {
              if (matchesWhere(nodes[index], where)) nodes.splice(index, 1);
            }
            return { count: before - nodes.length };
          },
        },
      };
      await callback(tx);
    },
  });

  return { createdData, updatedData, getOutline: () => outline };
}

afterEach(() => {
  Object.assign(prisma.writingTask, {
    findUnique: originalFindUnique,
    update: originalUpdate,
  });
  Object.assign(prisma, {
    $transaction: originalTransaction,
  });
});

describe("executeUpdates outline node kind", () => {
  it("创建大纲节点时保存显式 kind", async () => {
    const { createdData } = installOutlineMock([]);

    const result = await executeUpdates("task-1", {
      outlineAdjustments: [
        { action: "create", title: "第一卷", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 10 },
      ],
    });

    assert.equal(result.success, true);
    assert.equal(createdData.length, 1);
    assert.equal((createdData[0] as MockOutlineNode).kind, "stage");
  });

  it("未传 kind 时按父级推断剧情单元", async () => {
    const { createdData } = installOutlineMock([
      {
        id: "stage-1",
        novelId: "novel-1",
        parentId: null,
        title: "第一卷",
        content: null,
        kind: "stage",
        status: "planned",
        order: 0,
        estimatedWordCount: null,
        actualWordCount: null,
        chapterStartOrder: 1,
        chapterEndOrder: 10,
      },
    ]);

    const result = await executeUpdates("task-1", {
      outlineAdjustments: [
        { action: "create", title: "家族试炼", parentId: "stage-1", chapterStartOrder: 1, chapterEndOrder: 5 },
      ],
    });

    assert.equal(result.success, true);
    assert.equal((createdData[0] as MockOutlineNode).kind, "plot_unit");
  });

  it("更新大纲节点时保存 kind", async () => {
    const { updatedData } = installOutlineMock([
      {
        id: "node-1",
        novelId: "novel-1",
        parentId: null,
        title: "旧节点",
        content: null,
        kind: "stage",
        status: "planned",
        order: 0,
        estimatedWordCount: null,
        actualWordCount: null,
        chapterStartOrder: 1,
        chapterEndOrder: 10,
      },
    ]);

    const result = await executeUpdates("task-1", {
      outlineAdjustments: [
        { action: "update", nodeId: "node-1", kind: "stage", title: "第一卷" },
      ],
    });

    assert.equal(result.success, true);
    assert.equal(updatedData.length, 1);
    assert.equal((updatedData[0] as Partial<MockOutlineNode>).kind, "stage");
  });

  it("父节点范围缩小后不能排除已有子节点", async () => {
    const { updatedData } = installOutlineMock([
      {
        id: "stage-1",
        novelId: "novel-1",
        parentId: null,
        title: "第一阶段",
        content: null,
        kind: "stage",
        status: "planned",
        order: 0,
        estimatedWordCount: null,
        actualWordCount: null,
        chapterStartOrder: 1,
        chapterEndOrder: 20,
      },
      {
        id: "unit-1",
        novelId: "novel-1",
        parentId: "stage-1",
        title: "第一单元",
        content: null,
        kind: "plot_unit",
        status: "planned",
        order: 0,
        estimatedWordCount: null,
        actualWordCount: null,
        chapterStartOrder: 1,
        chapterEndOrder: 10,
      },
    ]);

    const result = await executeUpdates("task-1", {
      outlineAdjustments: [
        { action: "update", nodeId: "stage-1", chapterStartOrder: 1, chapterEndOrder: 5 },
      ],
    });

    assert.equal(result.success, false);
    assert.equal(updatedData.length, 0);
    assert.match(result.errors.join("\n"), /子节点.*不在更新后的父节点范围内/);
  });

  it("同一草案中写总纲并用 clientKey/parentKey 创建三层节点树", async () => {
    const { createdData, getOutline } = installOutlineMock([]);

    const result = await executeUpdates("task-1", {
      outlineContent: "全书总纲：主角离乡，追查旧案，最终推翻旧秩序。",
      outlineAdjustments: [
        { action: "create", clientKey: "g1", parentKey: "u1", title: "1-5章 被迫接案", kind: "chapter_group", chapterStartOrder: 1, chapterEndOrder: 5 },
        { action: "create", clientKey: "s1", title: "第一卷 离乡", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 10 },
        { action: "create", clientKey: "u1", parentKey: "s1", title: "假案引路", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 5 },
      ],
    });

    assert.equal(result.success, true);
    assert.equal(getOutline()?.content, "全书总纲：主角离乡，追查旧案，最终推翻旧秩序。");
    assert.equal(createdData.length, 3);
    assert.equal((createdData[0] as MockOutlineNode).kind, "stage");
    assert.equal((createdData[1] as MockOutlineNode).kind, "plot_unit");
    assert.equal((createdData[1] as MockOutlineNode).parentId, "created-1");
    assert.equal((createdData[2] as MockOutlineNode).kind, "chapter_group");
    assert.equal((createdData[2] as MockOutlineNode).parentId, "created-2");
  });

  it("parentId 和 parentKey 同时出现时拒绝创建", async () => {
    const { createdData } = installOutlineMock([
      {
        id: "stage-1",
        novelId: "novel-1",
        parentId: null,
        title: "第一卷",
        content: null,
        kind: "stage",
        status: "planned",
        order: 0,
        estimatedWordCount: null,
        actualWordCount: null,
        chapterStartOrder: 1,
        chapterEndOrder: 10,
      },
    ]);

    const result = await executeUpdates("task-1", {
      outlineAdjustments: [
        {
          action: "create",
          title: "冲突单元",
          kind: "plot_unit",
          parentId: "stage-1",
          parentKey: "stage-key",
          chapterStartOrder: 1,
          chapterEndOrder: 5,
        },
      ],
    });

    assert.equal(result.success, false);
    assert.equal(createdData.length, 0);
    assert.match(result.summary, /已自动回滚/);
  });

  it("replace 模式删除旧树后只写入一棵完整新树", async () => {
    const { createdData } = installOutlineMock([
      {
        id: "old-stage",
        novelId: "novel-1",
        parentId: null,
        title: "旧大纲",
        content: null,
        kind: "stage",
        status: "planned",
        order: 0,
        estimatedWordCount: null,
        actualWordCount: null,
        chapterStartOrder: 1,
        chapterEndOrder: 90,
      },
    ]);

    const result = await executeUpdates("task-1", {
      outlineTreeMode: "replace",
      outlineAdjustments: [
        { action: "create", clientKey: "s1", title: "第一阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 15 },
        { action: "create", clientKey: "u1", parentKey: "s1", title: "开篇单元", kind: "plot_unit", chapterStartOrder: 1, chapterEndOrder: 15 },
        { action: "create", clientKey: "g1", parentKey: "u1", title: "第1-3章", kind: "chapter_group", chapterStartOrder: 1, chapterEndOrder: 3 },
      ],
    });

    assert.equal(result.success, true);
    assert.equal(createdData.length, 3);
  });

  it("replace 模式在范围重叠时写入前失败", async () => {
    const { createdData } = installOutlineMock([]);
    const result = await executeUpdates("task-1", {
      outlineTreeMode: "replace",
      outlineAdjustments: [
        { action: "create", clientKey: "s1", title: "第一阶段", kind: "stage", chapterStartOrder: 1, chapterEndOrder: 20 },
        { action: "create", clientKey: "s2", title: "第二阶段", kind: "stage", chapterStartOrder: 15, chapterEndOrder: 30 },
      ],
    });
    assert.equal(result.success, false);
    assert.equal(createdData.length, 0);
    assert.match(result.errors.join("\n"), /重叠/);
  });
});

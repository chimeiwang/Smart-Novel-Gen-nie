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
};

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
            nodes.filter((node) =>
              Object.entries(where).every(([key, value]) => node[key as keyof MockOutlineNode] === value)
            ).length,
          findFirst: async ({ where, select }: { where: Partial<MockOutlineNode>; select?: Record<string, boolean> }) => {
            const node = nodes.find((item) =>
              Object.entries(where).every(([key, value]) => item[key as keyof MockOutlineNode] === value)
            );
            if (!node) return null;
            if (!select) return node;
            return Object.fromEntries(Object.keys(select).map((key) => [key, node[key as keyof MockOutlineNode]]));
          },
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
          delete: async () => ({}),
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
        { action: "create", title: "第一卷", kind: "stage" },
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
      },
    ]);

    const result = await executeUpdates("task-1", {
      outlineAdjustments: [
        { action: "create", title: "家族试炼", parentId: "stage-1" },
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

  it("同一草案中写总纲并用 clientKey/parentKey 创建三层节点树", async () => {
    const { createdData, getOutline } = installOutlineMock([]);

    const result = await executeUpdates("task-1", {
      outlineContent: "全书总纲：主角离乡，追查旧案，最终推翻旧秩序。",
      outlineAdjustments: [
        { action: "create", clientKey: "g1", parentKey: "u1", title: "1-5章 被迫接案", kind: "chapter_group" },
        { action: "create", clientKey: "s1", title: "第一卷 离乡", kind: "stage" },
        { action: "create", clientKey: "u1", parentKey: "s1", title: "假案引路", kind: "plot_unit" },
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
        },
      ],
    });

    assert.equal(result.success, false);
    assert.equal(createdData.length, 0);
    assert.match(result.summary, /已自动回滚/);
  });
});

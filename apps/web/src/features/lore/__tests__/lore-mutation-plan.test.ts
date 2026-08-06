import assert from "node:assert/strict";
import test from "node:test";

import {
  buildChildMutationPlan,
  executeChildMutationPlan,
} from "../lore-mutation-plan";

test("关系和经历按业务字段生成增改删并保留创建身份", () => {
  const original = [
    { id: "removed", updatedAt: "v1", content: "删除" },
    { id: "changed", updatedAt: "v2", content: "旧值" },
    { id: "unchanged", updatedAt: "v3", content: "不变" },
  ];
  const draft = [
    { id: "changed", updatedAt: "v2", content: "新值" },
    { id: "unchanged", updatedAt: "服务端刷新后的元数据", content: "不变" },
    { clientRequestId: "stable-create-id", content: "新增" },
  ];

  const plan = buildChildMutationPlan(original, draft);

  assert.deepEqual(plan.deletes.map((item) => item.id), ["removed"]);
  assert.deepEqual(plan.updates.map((item) => item.id), ["changed"]);
  assert.equal(plan.creates[0].clientRequestId, "stable-create-id");
});

test("差量请求严格按删除更新创建串行且失败即停止", async () => {
  const calls: string[] = [];
  const plan = {
    deletes: [{ id: "delete", updatedAt: "v1" }],
    updates: [{ id: "update", updatedAt: "v2" }],
    creates: [{ clientRequestId: "stable-create-id" }],
  };

  await assert.rejects(() => executeChildMutationPlan(plan, {
    delete: async (item) => { calls.push(`delete:${item.id}`); },
    update: async (item) => {
      calls.push(`update:${item.id}`);
      throw new Error("409");
    },
    create: async (item) => { calls.push(`create:${item.clientRequestId}`); },
  }));

  assert.deepEqual(calls, ["delete:delete", "update:update"]);
});

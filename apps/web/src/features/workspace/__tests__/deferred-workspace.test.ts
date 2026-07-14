import assert from "node:assert/strict";
import test from "node:test";

import {
  DeferredWorkspaceLoader,
  groupForTab,
  type WorkspaceGroupLoaders,
} from "../deferred-workspace";

test("把侧栏入口映射到三个延迟分组", () => {
  assert.equal(groupForTab("characters"), "lore");
  assert.equal(groupForTab("outline"), "planning");
  assert.equal(groupForTab("references"), "resources");
  assert.equal(groupForTab("chapters"), null);
});

test("同一分组并发加载一次并缓存成功结果", async () => {
  let loreCalls = 0;
  const loaders = {
    lore: async () => {
      loreCalls += 1;
      return { characters: [] };
    },
    planning: async () => ({ outlineNodes: [] }),
    resources: async () => ({ references: [] }),
  } as unknown as WorkspaceGroupLoaders;
  const loader = new DeferredWorkspaceLoader(loaders);

  await Promise.all([loader.load("lore"), loader.load("lore")]);
  await loader.load("lore");

  assert.equal(loreCalls, 1);
  assert.equal(loader.snapshot().lore.status, "success");
});

test("单个分组失败不会清空其他缓存并允许重试", async () => {
  let planningCalls = 0;
  const loaders = {
    lore: async () => ({ characters: [] }),
    planning: async () => {
      planningCalls += 1;
      if (planningCalls === 1) throw new Error("规划服务暂时不可用");
      return { outlineNodes: [] };
    },
    resources: async () => ({ references: [] }),
  } as unknown as WorkspaceGroupLoaders;
  const loader = new DeferredWorkspaceLoader(loaders);

  await loader.load("lore");
  await assert.rejects(loader.load("planning"), /规划服务暂时不可用/);
  assert.equal(loader.snapshot().lore.status, "success");
  assert.equal(loader.snapshot().planning.status, "error");
  assert.match(loader.snapshot().planning.error ?? "", /规划服务暂时不可用/);

  await loader.retry("planning");
  assert.equal(planningCalls, 2);
  assert.equal(loader.snapshot().planning.status, "success");
  assert.equal(loader.snapshot().lore.status, "success");
});

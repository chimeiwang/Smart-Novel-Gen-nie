import assert from "node:assert/strict";
import test from "node:test";

import {
  DeferredWorkspaceLoader,
  groupForTab,
  type WorkspaceGroupLoaders,
} from "../deferred-workspace";
import { countTextLength } from "../../../shared/lib/word-count";

test("把侧栏入口映射到三个延迟分组", () => {
  assert.equal(groupForTab("characters"), "lore");
  assert.equal(groupForTab("locations"), "lore");
  assert.equal(groupForTab("factions"), "lore");
  assert.equal(groupForTab("items"), "lore");
  assert.equal(groupForTab("glossaries"), "lore");
  assert.equal(groupForTab("storyBackground"), "planning");
  assert.equal(groupForTab("worldSetting"), "planning");
  assert.equal(groupForTab("outline"), "planning");
  assert.equal(groupForTab("progress"), "planning");
  assert.equal(groupForTab("storyProgress"), "planning");
  assert.equal(groupForTab("writingBible"), "planning");
  assert.equal(groupForTab("style"), "resources");
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

test("分组失效后重新请求且不清空其他分组", async () => {
  let loreCalls = 0;
  const loaders = {
    lore: async () => ({ characters: [{ id: `角色-${++loreCalls}` }] }),
    planning: async () => ({ outlineNodes: [] }),
    resources: async () => ({ references: [] }),
  } as unknown as WorkspaceGroupLoaders;
  const loader = new DeferredWorkspaceLoader(loaders);

  await loader.load("planning");
  await loader.load("lore");
  loader.invalidate("lore");
  const refreshed = await loader.load("lore");

  assert.equal(loreCalls, 2);
  assert.equal(refreshed.characters[0]?.id, "角色-2");
  assert.equal(loader.snapshot().planning.status, "success");
});

test("刷新期间旧请求晚完成也不能覆盖新结果", async () => {
  let resolveOld!: (value: { characters: Array<{ id: string }> }) => void;
  const oldResponse = new Promise<{ characters: Array<{ id: string }> }>((resolve) => {
    resolveOld = resolve;
  });
  let calls = 0;
  const loaders = {
    lore: async () => {
      calls += 1;
      if (calls === 1) {
        return await oldResponse;
      }
      return { characters: [{ id: "新结果" }] };
    },
    planning: async () => ({ outlineNodes: [] }),
    resources: async () => ({ references: [] }),
  } as unknown as WorkspaceGroupLoaders;
  const loader = new DeferredWorkspaceLoader(loaders);

  const oldRequest = loader.load("lore");
  const newResult = await loader.refresh("lore");
  resolveOld({ characters: [{ id: "旧结果" }] });
  await oldRequest;

  assert.equal(calls, 2);
  assert.equal(newResult.characters[0]?.id, "新结果");
  assert.equal(loader.snapshot().lore.data?.characters[0]?.id, "新结果");
});

test("统一字数规则忽略 Unicode 空白和 BOM，并按码点统计", () => {
  const vectors = [
    ["甲 乙\n丙", 3],
    ["\u3000甲\t乙", 2],
    ["甲\u00a0乙", 2],
    ["甲\ufeff乙", 2],
    ["\u0085甲", 1],
    ["😀", 1],
  ] as const;

  for (const [text, expected] of vectors) {
    assert.equal(countTextLength(text), expected, JSON.stringify(text));
  }
});

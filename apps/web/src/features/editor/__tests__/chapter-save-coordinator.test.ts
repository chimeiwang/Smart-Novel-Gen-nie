import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { setTimeout as delay } from "node:timers/promises";

import {
  ChapterSaveCoordinator,
  createBestEffortChapterDraftStorage,
  createChapterDraftStorage,
  type ChapterDraftSnapshot,
  type PendingChapterDraft,
} from "../chapter-save-coordinator";
import {
  flushActiveChapterSave,
  registerActiveChapterSave,
} from "../chapter-save-navigation";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

class MemoryDraftStorage {
  value: PendingChapterDraft | null = null;

  load() {
    return this.value;
  }

  save(value: PendingChapterDraft) {
    this.value = structuredClone(value);
  }

  clear() {
    this.value = null;
  }
}

class MemoryBrowserStorage {
  readonly values = new Map<string, string>();

  getItem(key: string) {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string) {
    this.values.set(key, value);
  }

  removeItem(key: string) {
    this.values.delete(key);
  }
}

const INITIAL: ChapterDraftSnapshot = { title: "第一章", content: "初稿" };

describe("ChapterSaveCoordinator", () => {
  it("在防抖时间内只保存最后一次输入", async () => {
    const calls: Array<ChapterDraftSnapshot & { expectedUpdatedAt: string }> = [];
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 5,
      save: async (request) => {
        calls.push(request);
        return { updatedAt: "v2" };
      },
    });

    coordinator.schedule({ title: "标题 A", content: "正文 A" });
    coordinator.schedule({ title: "标题 B", content: "正文 B" });
    await delay(30);

    assert.deepEqual(calls, [
      { title: "标题 B", content: "正文 B", expectedUpdatedAt: "v1" },
    ]);
    assert.equal(coordinator.state, "saved");
  });

  it("请求期间的新输入会在前一请求完成后串行补存", async () => {
    const first = deferred<{ updatedAt: string }>();
    const second = deferred<{ updatedAt: string }>();
    const calls: Array<ChapterDraftSnapshot & { expectedUpdatedAt: string }> = [];
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      save: (request) => {
        calls.push(request);
        return calls.length === 1 ? first.promise : second.promise;
      },
    });

    coordinator.schedule({ title: "标题 A", content: "正文 A" });
    const flushed = coordinator.flush();
    await delay(0);
    coordinator.schedule({ title: "标题 B", content: "正文 B" });
    assert.equal(calls.length, 1);

    first.resolve({ updatedAt: "v2" });
    await delay(0);
    assert.deepEqual(calls[1], {
      title: "标题 B",
      content: "正文 B",
      expectedUpdatedAt: "v2",
    });
    second.resolve({ updatedAt: "v3" });
    await flushed;

    assert.equal(calls.length, 2);
    assert.equal(coordinator.updatedAt, "v3");
  });

  it("flush 会取消长防抖并立即保存", async () => {
    let calls = 0;
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      save: async () => {
        calls += 1;
        return { updatedAt: "v2" };
      },
    });

    coordinator.schedule({ title: "立即保存", content: "正文" });
    await coordinator.flush();

    assert.equal(calls, 1);
    assert.equal(coordinator.state, "saved");
  });

  it("失败会保留最新草稿，retry 成功后才清除", async () => {
    const storage = new MemoryDraftStorage();
    let calls = 0;
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      storage,
      save: async () => {
        calls += 1;
        if (calls === 1) throw Object.assign(new Error("网络失败"), { status: 503 });
        return { updatedAt: "v2" };
      },
    });

    coordinator.schedule({ title: "未保存标题", content: "未保存正文" });
    await assert.rejects(coordinator.flush(), /网络失败/);
    assert.equal(coordinator.state, "failed");
    assert.equal(storage.value?.snapshot.content, "未保存正文");

    await coordinator.retry();
    assert.equal(coordinator.state, "saved");
    assert.equal(storage.value, null);
  });

  it("409 版本冲突不会清除本地草稿", async () => {
    const storage = new MemoryDraftStorage();
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      storage,
      save: async () => {
        throw Object.assign(new Error("版本冲突"), { status: 409 });
      },
    });

    coordinator.schedule({ title: "本地标题", content: "本地正文" });
    await assert.rejects(coordinator.flush(), /版本冲突/);

    assert.equal(coordinator.state, "conflict");
    assert.equal(storage.value?.snapshot.content, "本地正文");
  });

  it("版本冲突草稿仅在用户显式放弃后清除", () => {
    const storage = new MemoryDraftStorage();
    storage.value = {
      snapshot: { title: "本地标题", content: "必须先保留的本地正文" },
      expectedUpdatedAt: "v1",
    };
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v2",
      delayMs: 60_000,
      storage,
      save: async () => ({ updatedAt: "v3" }),
    });

    assert.equal(coordinator.state, "conflict");
    assert.equal(storage.value?.snapshot.content, "必须先保留的本地正文");

    assert.equal(coordinator.discardLocalDraft(), true);

    assert.equal(storage.value, null);
  });

  it("浏览器无法清理冲突草稿时不触发重新加载条件", () => {
    const pending: PendingChapterDraft = {
      snapshot: { title: "本地标题", content: "需要保留的本地正文" },
      expectedUpdatedAt: "v1",
    };
    const storage = createChapterDraftStorage({
      getItem: () => JSON.stringify(pending),
      setItem() {},
      removeItem() {
        throw new Error("浏览器禁止清理本地存储");
      },
    }, "draft:user:novel:chapter");
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v2",
      delayMs: 60_000,
      storage,
      save: async () => ({ updatedAt: "v3" }),
    });

    assert.equal(coordinator.discardLocalDraft(), false);
    assert.equal(coordinator.state, "conflict");
    assert.equal(coordinator.snapshot.content, "需要保留的本地正文");
  });

  it("dispose 会清理定时器并尝试保存待提交草稿", async () => {
    const saved: ChapterDraftSnapshot[] = [];
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      save: async (request) => {
        saved.push(request);
        return { updatedAt: "v2" };
      },
    });
    coordinator.schedule({ title: "切章前", content: "必须保存" });

    await coordinator.dispose();

    assert.equal(saved[0]?.content, "必须保存");
  });

  it("会恢复同一服务端版本上的本地待保存草稿", async () => {
    const storage = new MemoryDraftStorage();
    storage.value = {
      snapshot: { title: "恢复标题", content: "恢复正文" },
      expectedUpdatedAt: "v1",
    };
    const calls: Array<ChapterDraftSnapshot & { expectedUpdatedAt: string }> = [];
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      storage,
      save: async (request) => {
        calls.push(request);
        return { updatedAt: "v2" };
      },
    });

    assert.deepEqual(coordinator.snapshot, storage.value.snapshot);
    assert.equal(coordinator.state, "waiting");
    await coordinator.flush();
    assert.equal(calls[0]?.content, "恢复正文");
  });

  it("服务端已保存同一快照时清除旧版本本地草稿", () => {
    const storage = new MemoryDraftStorage();
    const committedSnapshot = { title: "已提交标题", content: "已提交正文" };
    storage.value = {
      snapshot: committedSnapshot,
      expectedUpdatedAt: "v1",
    };

    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: committedSnapshot,
      initialUpdatedAt: "v2",
      delayMs: 60_000,
      storage,
      save: async () => {
        throw new Error("相同快照不应再次保存");
      },
    });

    assert.equal(coordinator.state, "saved");
    assert.equal(storage.value, null);
  });

  it("外部状态写入成功后会推进后续保存使用的版本", async () => {
    const calls: Array<ChapterDraftSnapshot & { expectedUpdatedAt: string }> = [];
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      save: async (request) => {
        calls.push(request);
        return { updatedAt: "v3" };
      },
    });

    coordinator.advanceVersion("v2");
    coordinator.schedule({ title: "重新编辑", content: "新正文" });
    await coordinator.flush();

    assert.equal(calls[0]?.expectedUpdatedAt, "v2");
  });

  it("浏览器草稿存储只读写指定隔离键并忽略损坏数据", () => {
    const browserStorage = new MemoryBrowserStorage();
    const first = createChapterDraftStorage(browserStorage, "draft:user-a:novel-a:chapter-a");
    const second = createChapterDraftStorage(browserStorage, "draft:user-b:novel-b:chapter-b");
    const pending: PendingChapterDraft = {
      snapshot: { title: "本地标题", content: "本地正文" },
      expectedUpdatedAt: "v1",
    };

    first.save(pending);
    assert.deepEqual(first.load(), pending);
    assert.equal(second.load(), null);

    browserStorage.setItem("draft:user-b:novel-b:chapter-b", "{损坏");
    assert.equal(second.load(), null);
    assert.equal(browserStorage.getItem("draft:user-b:novel-b:chapter-b"), null);
  });

  it("浏览器存储读取失败时仍允许编辑器使用服务端快照", () => {
    const storage = createChapterDraftStorage({
      getItem() {
        throw new Error("浏览器禁止读取本地存储");
      },
      setItem() {},
      removeItem() {},
    }, "draft:user:novel:chapter");

    assert.equal(storage.load(), null);
  });

  it("浏览器拒绝访问 localStorage 属性时仍允许编辑器初始化", () => {
    const storage = createBestEffortChapterDraftStorage({
      get localStorage() {
        throw new Error("浏览器禁止访问本地存储");
      },
    }, "draft:user:novel:chapter");

    assert.equal(storage, undefined);
  });

  it("浏览器存储写入失败时不阻断服务端保存", async () => {
    let saveCalls = 0;
    const storage = createChapterDraftStorage({
      getItem: () => null,
      setItem() {
        throw new Error("本地存储空间不足");
      },
      removeItem() {},
    }, "draft:user:novel:chapter");
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      storage,
      save: async () => {
        saveCalls += 1;
        return { updatedAt: "v2" };
      },
    });

    coordinator.schedule({ title: "仍需保存", content: "完整正文" });
    await coordinator.flush();

    assert.equal(saveCalls, 1);
    assert.equal(coordinator.state, "saved");
  });

  it("浏览器存储清理失败时不把已成功请求误报为失败", async () => {
    const storage = createChapterDraftStorage({
      getItem: () => null,
      setItem() {},
      removeItem() {
        throw new Error("浏览器禁止清理本地存储");
      },
    }, "draft:user:novel:chapter");
    const coordinator = new ChapterSaveCoordinator({
      initialSnapshot: INITIAL,
      initialUpdatedAt: "v1",
      delayMs: 60_000,
      storage,
      save: async () => ({ updatedAt: "v2" }),
    });

    coordinator.schedule({ title: "已保存标题", content: "已保存正文" });
    await coordinator.flush();

    assert.equal(coordinator.state, "saved");
    assert.equal(coordinator.updatedAt, "v2");
  });
});

describe("章节切换保存门禁", () => {
  it("等待当前编辑器保存，并在失败时向导航方传播错误", async () => {
    let calls = 0;
    const unregister = registerActiveChapterSave(async () => {
      calls += 1;
      throw new Error("保存失败");
    });

    await assert.rejects(flushActiveChapterSave(), /保存失败/);
    assert.equal(calls, 1);

    unregister();
    await flushActiveChapterSave();
    assert.equal(calls, 1);
  });
});

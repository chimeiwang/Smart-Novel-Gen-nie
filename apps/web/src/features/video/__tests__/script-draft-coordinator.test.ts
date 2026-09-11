import assert from "node:assert/strict";
import test from "node:test";

import { ScriptDraftCoordinator, type DraftWrite } from "../production/script-draft-coordinator";
import { EpisodeRequestScope } from "../production/episode-request-scope";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

test("保存期间继续输入，确认必须等待最新工作稿保存", async () => {
  const first = deferred<{ document: string; revision: number }>();
  const writes: DraftWrite<string>[] = [];
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "原稿", revision: 0 }, requestId: () => `r${writes.length}`, save: async (write) => {
    writes.push(write);
    return writes.length === 1 ? first.promise : { document: write.document, revision: write.revision + 1 };
  } });
  coordinator.schedule("第一次修改");
  const saving = coordinator.flush();
  coordinator.schedule("继续修改");
  let confirmed: string | null = null;
  const confirming = coordinator.runExclusive(async (snapshot) => { confirmed = snapshot.document; return { result: snapshot.revision }; });
  assert.throws(() => coordinator.schedule("不能混入确认"));
  assert.equal(confirmed, null);
  first.resolve({ document: "第一次修改", revision: 1 });
  await saving;
  assert.equal(await confirming, 2);
  assert.equal(confirmed, "继续修改");
  assert.equal(writes[1].revision, 1);
  assert.equal(coordinator.state, "saved");
  coordinator.dispose();
});

test("网络未知重试保持原请求和内容，随后另存新输入", async () => {
  const writes: DraftWrite<string>[] = [];
  let sequence = 0;
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "原稿", revision: 4 }, requestId: () => `request-${++sequence}`, save: async (write) => {
    writes.push(write);
    if (writes.length === 1) throw new Error("网络中断");
    return { document: write.document, revision: write.revision + 1 };
  } });
  coordinator.schedule("可能已保存");
  await assert.rejects(coordinator.flush());
  coordinator.schedule("新输入");
  await coordinator.retry();
  assert.deepEqual(writes[0], writes[1]);
  assert.equal(writes[2].document, "新输入");
  assert.notEqual(writes[2].clientRequestId, writes[1].clientRequestId);
  coordinator.dispose();
});

test("409 不丢输入，不自动用新 revision 再写", async () => {
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "原稿", revision: 1 }, requestId: () => "r", save: async () => { throw { status: 409 }; } });
  coordinator.schedule("本地作者稿");
  await assert.rejects(coordinator.flush());
  await assert.rejects(coordinator.retry());
  assert.equal(coordinator.document, "本地作者稿");
  assert.equal(coordinator.revision, 1);
  coordinator.resolveConflict({ document: "远端作者稿", revision: 2 }, true);
  assert.equal(coordinator.document, "本地作者稿");
  assert.equal(coordinator.revision, 2);
  coordinator.dispose();
});

test("采用回包原子推进工作稿；重复命令不能并行", async () => {
  const candidate = deferred<{ result: string; draft: { document: string; revision: number } }>();
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "手写稿", revision: 2 }, requestId: () => "r", save: async (write) => write });
  const adopting = coordinator.runExclusive(async () => candidate.promise);
  await assert.rejects(coordinator.runExclusive(async () => ({ result: "重复" })));
  candidate.resolve({ result: "候选回执", draft: { document: "采用后的工作稿", revision: 3 } });
  assert.equal(await adopting, "候选回执");
  assert.equal(coordinator.document, "采用后的工作稿");
  assert.equal(coordinator.revision, 3);
  coordinator.dispose();
});

test("Core 身份映射不覆盖保存期间继续输入", async () => {
  const reply = deferred<{ document: { id: string; text: string }; revision: number; reconcileLocal: (latest: { id: string; text: string }) => { id: string; text: string } }>();
  let count = 0;
  const coordinator = new ScriptDraftCoordinator({ initial: { document: { id: "temp", text: "" }, revision: 0 }, requestId: () => `${++count}`, save: async (write) => count === 1 ? reply.promise : { document: write.document, revision: 2 } });
  coordinator.schedule({ id: "temp", text: "初稿" });
  const saving = coordinator.flush();
  coordinator.schedule({ id: "temp", text: "继续写" });
  reply.resolve({ document: { id: "stable", text: "初稿" }, revision: 1, reconcileLocal: (latest) => ({ ...latest, id: "stable" }) });
  await saving;
  assert.deepEqual(coordinator.document, { id: "stable", text: "继续写" });
  coordinator.dispose();
});

test("离开后迟到保存不通知新工作面，跨集请求旧代次失效", async () => {
  const reply = deferred<{ document: string; revision: number }>();
  let notices = 0;
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "A", revision: 0 }, requestId: () => "r", save: () => reply.promise, onChange: () => { notices += 1; } });
  coordinator.schedule("A 修改");
  const saving = coordinator.flush();
  coordinator.dispose();
  const before = notices;
  reply.resolve({ document: "A 修改", revision: 1 });
  await saving;
  assert.equal(notices, before);
  const scope = new EpisodeRequestScope();
  const a = scope.next();
  const b = scope.next();
  assert.equal(a(), false);
  assert.equal(b(), true);
  scope.dispose();
  assert.equal(b(), false);
});

test("校验失败修正输入后创建新请求，不反复重放已拒绝的内容", async () => {
  const writes: DraftWrite<string>[] = [];
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "有效", revision: 1 }, requestId: () => `r${writes.length}`, save: async (write) => { writes.push(write); if (!write.document) throw { status: 422 }; return { document: write.document, revision: 2 }; } });
  coordinator.schedule("");
  await assert.rejects(coordinator.flush());
  coordinator.schedule("已修正");
  await coordinator.retry();
  assert.equal(writes[1].document, "已修正");
  assert.notEqual(writes[0].clientRequestId, writes[1].clientRequestId);
  coordinator.dispose();
});

test("刷新后旧命令回执不得把已读到的远端新版本倒退", async () => {
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "其他作者已到新版", revision: 5 }, restored: { latest: "待核对稿", baseline: { document: "旧稿", revision: 1 }, pending: { clientRequestId: "same-request", document: "待核对稿", revision: 1 } }, requestId: () => "unused", save: async () => ({ document: "待核对稿", revision: 2 }) });
  await assert.rejects(coordinator.retry());
  assert.equal(coordinator.state, "conflict");
  assert.equal(coordinator.revision, 5);
  assert.equal(coordinator.document, "待核对稿");
  coordinator.dispose();
});

test("冲突后保留本地稿会按新 revision 继续自动保存", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const writes: DraftWrite<string>[] = [];
  const coordinator = new ScriptDraftCoordinator({ initial: { document: "旧稿", revision: 1 }, delayMs: 10, resourceLabel: "分镜", requestId: () => "new-request", save: async (write) => { writes.push(write); return { document: write.document, revision: write.revision + 1 }; } });
  coordinator.schedule("本地未保存分镜");
  coordinator.resolveConflict({ document: "远端分镜", revision: 4 }, true);
  context.mock.timers.tick(10);
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.equal(writes[0]?.revision, 4);
  assert.equal(writes[0]?.document, "本地未保存分镜");
  coordinator.dispose();
});

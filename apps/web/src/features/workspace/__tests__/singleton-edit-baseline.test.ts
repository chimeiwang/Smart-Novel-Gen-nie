import assert from "node:assert/strict";
import test from "node:test";

import {
  advanceSingletonEditBaseline,
  createSingletonEditBaseline,
  markSingletonEditDirty,
  observeSingletonEditVersion,
  resolveSingletonEditValue,
} from "../singleton-edit-baseline";

test("本地草稿从 v1 开始后，外部 props 更新到 v2 仍使用 v1 保存", () => {
  const opened = createSingletonEditBaseline("v1");
  const editing = markSingletonEditDirty(opened);
  const externallyUpdated = observeSingletonEditVersion(editing, "v2");

  assert.equal(externallyUpdated.expectedUpdatedAt, "v1");
  assert.equal(externallyUpdated.observedUpdatedAt, "v2");
  assert.equal(externallyUpdated.hasLocalDraft, true);
});

test("保存成功后，后续保存基线推进到响应返回的新版本", () => {
  const editing = markSingletonEditDirty(createSingletonEditBaseline("v1"));
  const saved = advanceSingletonEditBaseline(editing, "v2");

  assert.equal(saved.expectedUpdatedAt, "v2");
  assert.equal(saved.hasLocalDraft, false);

  const sameStaleProps = observeSingletonEditVersion(saved, "v1");
  assert.equal(sameStaleProps.expectedUpdatedAt, "v2");

  const editingAgain = markSingletonEditDirty(sameStaleProps);
  assert.equal(editingAgain.expectedUpdatedAt, "v2");
});

test("没有本地草稿时，props 从 v1 更新到 v2 会同步使用 v2 内容", () => {
  const opened = createSingletonEditBaseline("v1");
  const externallyUpdated = observeSingletonEditVersion(opened, "v2");

  assert.equal(resolveSingletonEditValue(externallyUpdated, "本地 v1", "服务端 v2"), "服务端 v2");
});

test("保存成功但 props 尚未追上响应版本时，继续显示刚保存的本地内容", () => {
  const editing = markSingletonEditDirty(createSingletonEditBaseline("v1"));
  const saved = advanceSingletonEditBaseline(editing, "v2");
  const staleProps = observeSingletonEditVersion(saved, "v1");

  assert.equal(resolveSingletonEditValue(staleProps, "刚保存的内容", "旧服务端内容"), "刚保存的内容");
});

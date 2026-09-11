import assert from "node:assert/strict";
import test from "node:test";
import { duplicateScene, nodeIdentity, reconcileScriptNodeIds, removeScene, reorderScene } from "../production/script-document-state";
import { episodeVersionLabels } from "../production/episode-version-context";
import { unicodeSelectionRange } from "../production/episode-source-panel";
import { flushEpisodeSaves, registerEpisodeSave } from "../production/episode-save-navigation";
import type { EpisodeDetail, ScriptDocument } from "../production/types";

const document: ScriptDocument = {
  schemaVersion: "video-episode-script/1.0",
  overview: { summary: "送信", creativeIntent: "不信任" },
  scenes: [
    { id: "scene-1", title: "交信", locationLabel: "门外", timeLabel: "夜", narrativeTime: "当晚", lines: [{ id: "line-1", kind: "action", text: "林岚交出信", sourceRefs: [] }] },
    { id: "scene-2", title: "回忆", locationLabel: "书房", timeLabel: "日", narrativeTime: "三日前", lines: [{ id: "line-2", kind: "action", text: "林岚写信", sourceRefs: [] }] },
  ],
  endingStates: [{ key: "letter", description: "顾舟持有信", narrativeTime: "当晚", entityIds: [] }],
  dependencies: [{ producerEpisodeId: "other", producerScriptVersionId: "v1", producerStateKey: "old", consumerSceneId: "scene-2", consumerLineId: "line-2", narrativeTime: "三日前", description: "回忆引用当时状态" }],
};

test("场次移动保留身份，复制分配全新临时身份且不复制承接", () => {
  const moved = reorderScene(document, "scene-2", -1);
  assert.equal(moved.scenes?.[0].id, "scene-2");
  assert.deepEqual(moved.dependencies, document.dependencies);
  let sequence = 0;
  const copied = duplicateScene(document.scenes![0], () => `new-${++sequence}`);
  assert.equal(copied.id, null);
  assert.equal(copied.tempKey, "new-1");
  assert.equal(copied.lines?.[0].id, null);
  assert.equal(copied.lines?.[0].tempKey, "new-2");
  assert.equal(document.scenes?.[0].id, "scene-1");
});

test("删除场次只移除本稿对应承接，历史输入不变", () => {
  const result = removeScene(document, "scene-2");
  assert.equal(result.scenes?.length, 1);
  assert.equal(result.dependencies?.length, 0);
  assert.equal(document.dependencies?.length, 1);
});

test("Core 身份映射同步承接锚点，不按内容相似度换身份", () => {
  const draft: ScriptDocument = { ...document, scenes: [{ ...document.scenes![1], id: null, tempKey: "temp-scene", lines: [{ ...document.scenes![1].lines![0], id: null, tempKey: "temp-line" }] }], dependencies: [{ ...document.dependencies![0], consumerSceneId: "temp-scene", consumerLineId: "temp-line" }] };
  const result = reconcileScriptNodeIds(draft, { "temp-scene": "stable-scene", "temp-line": "stable-line" });
  assert.equal(nodeIdentity(result.scenes![0]), "stable-scene");
  assert.equal(result.dependencies?.[0].consumerSceneId, "stable-scene");
  assert.equal(result.dependencies?.[0].consumerLineId, "stable-line");
  assert.equal(result.dependencies?.[0].producerScriptVersionId, "v1");
});

test("Unicode 取材范围按码点计数，不把代理对当两个字", () => {
  assert.deepEqual(unicodeSelectionRange("甲😀乙\n丙", 1, 4), { start: 1, end: 3 });
});

test("新正式剧本与旧制作、交付并存，缺失成果不会生成成功标签", () => {
  const detail = { scriptDraft: { revision: 9 }, currentScriptVersion: { versionNo: 2 }, episode: { currentProductionBaselineId: "制作-v1", latestDeliveryVersionId: "成片-v1" } } as EpisodeDetail;
  assert.deepEqual(episodeVersionLabels(detail), { draft: "工作稿 r9", script: "正式剧本 v2", production: "制作 制作-v1", delivery: "交付 成片-v1" });
  assert.equal(episodeVersionLabels({ ...detail, episode: { ...detail.episode, latestDeliveryVersionId: null } }).delivery, "尚无成片");
});

test("切换分集等待保存失败不会通过，项目命令恢复可排除自己的屏障", async () => {
  const calls: string[] = [];
  const unregisterProject = registerEpisodeSave({ novelId: "n", episodeId: "project", pending: () => true, flush: async () => { throw new Error("项目待核对"); } });
  const unregisterDraft = registerEpisodeSave({ novelId: "n", episodeId: "e", pending: () => true, flush: async () => { calls.push("saved"); } });
  await assert.rejects(flushEpisodeSaves("n"));
  await flushEpisodeSaves("n", "project");
  assert.deepEqual(calls, ["saved"]);
  unregisterProject(); unregisterDraft();
});

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

const workspaceRoot = process.cwd();
const libraryPaneSource = readFileSync(
  path.join(workspaceRoot, "src/features/workspace/library-pane.tsx"),
  "utf8",
);
const progressPanelSource = readFileSync(
  path.join(workspaceRoot, "src/features/progress/progress-panel.tsx"),
  "utf8",
);

test("单例资料保存通过编辑会话基线提交版本", () => {
  assert.match(libraryPaneSource, /planning\.storyProgressUpdatedAt/);
  assert.match(libraryPaneSource, /planning\.storyBackground\?\.updatedAt/);
  assert.match(libraryPaneSource, /planning\.worldSetting\?\.updatedAt/);
  assert.match(libraryPaneSource, /writingBible\?\.updatedAt/);
  assert.match(progressPanelSource, /progress\?\.updatedAt/);
  assert.match(libraryPaneSource, /expectedUpdatedAt:\s*currentEditBaseline\.expectedUpdatedAt/);
  assert.match(progressPanelSource, /expectedUpdatedAt:\s*currentEditBaseline\.expectedUpdatedAt/);
  assert.doesNotMatch(libraryPaneSource, /expectedUpdatedAt:\s*writingBible\?\.updatedAt/);
  assert.doesNotMatch(progressPanelSource, /expectedUpdatedAt:\s*progress\?\.updatedAt/);
});

test("进度面板直接复用生成客户端的 PlotProgressDto", () => {
  assert.match(progressPanelSource, /components\["schemas"\]\["PlotProgressDto"\]/);
});

test("409 冲突保留本地草稿并提示刷新，不自动重试", () => {
  assert.match(libraryPaneSource, /instanceof ApiResponseError/);
  assert.match(progressPanelSource, /instanceof ApiResponseError/);
  assert.match(libraryPaneSource, /当前草稿已保留/);
  assert.match(progressPanelSource, /当前草稿已保留/);
  assert.doesNotMatch(libraryPaneSource, /currentUpdatedAt[\s\S]*apiClient\.PUT/);
  assert.doesNotMatch(progressPanelSource, /currentUpdatedAt[\s\S]*apiClient\.PUT/);
});

test("单例资料保存期间禁用全部相关输入，避免成功回调清掉新输入", () => {
  assert.match(libraryPaneSource, /className="textarea library-long-textarea"[\s\S]*?disabled=\{pending\}/);
  assert.match(libraryPaneSource, /className=\{`story-profile-option[\s\S]*?disabled=\{pending\}/);
  assert.match(libraryPaneSource, /input className="input" inputMode="numeric"[\s\S]*?disabled=\{pending\}/);
  assert.match(libraryPaneSource, /textarea className="textarea textarea-resize"[\s\S]*?disabled=\{pending\}/);

  assert.equal(progressPanelSource.match(/disabled=\{pending\}/g)?.length, 5);
});

test("剧情进度保存后保留已保存快照，直到 props 追上响应版本", () => {
  assert.match(progressPanelSource, /resolveSingletonEditValue\(/);
  assert.match(progressPanelSource, /draft\s*\?\?\s*remoteDraft/);
  assert.doesNotMatch(progressPanelSource, /setDraft\(null\)/);
});

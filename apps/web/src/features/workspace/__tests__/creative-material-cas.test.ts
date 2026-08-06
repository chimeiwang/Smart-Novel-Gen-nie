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

test("单例资料保存请求使用最近一次 GET 返回的版本", () => {
  assert.match(libraryPaneSource, /planning\.storyProgressUpdatedAt/);
  assert.match(libraryPaneSource, /planning\.storyBackground\?\.updatedAt/);
  assert.match(libraryPaneSource, /planning\.worldSetting\?\.updatedAt/);
  assert.match(libraryPaneSource, /writingBible\?\.updatedAt/);
  assert.match(progressPanelSource, /progress\?\.updatedAt/);
  assert.match(libraryPaneSource, /expectedUpdatedAt/);
  assert.match(progressPanelSource, /expectedUpdatedAt/);
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

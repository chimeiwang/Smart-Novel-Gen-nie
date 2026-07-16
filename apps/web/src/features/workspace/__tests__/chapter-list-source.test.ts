import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("章节列表保留视图并分离新建与导航状态", async () => {
  const chapterListUrl = new URL("../../chapters/chapter-list.tsx", import.meta.url);
  const source = await readFile(chapterListUrl, "utf8");

  assert.match(source, /buildWorkspaceChapterHref/);
  assert.match(source, /formatChapterBeatPlanMeta/);
  assert.match(source, /\bview: WorkspaceView\b/);
  assert.match(source, /\bcreating\b/);
  assert.match(source, /\bnavigatingChapterId\b/);
  assert.match(source, /disabled=\{creating\}/);
  assert.match(source, /creating \? "添加中\.\.\." : "新增章节"/);
  assert.match(source, /navigating \? <span>切换中\.\.\.<\/span> : null/);
  assert.doesNotMatch(source, /const \[pending, startTransition\]/);
});

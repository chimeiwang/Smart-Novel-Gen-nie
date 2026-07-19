import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("中短篇工作区通过生成客户端接通聚合、版本和正式操作接口", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /browserApi\.GET\(\s*"\/api\/v1\/novels\/\{novel_id\}\/short-story\/artifacts"/);
  assert.match(source, /browserApi\.GET\(\s*"\/api\/v1\/review-artifacts\/\{artifact_id\}\/revisions"/);
  assert.match(source, /browserApi\.GET\(\s*"\/api\/v1\/writing\/sessions\/\{session_id\}"/);
  assert.match(source, /browserApi\.GET\([\s\S]*\/revisions\/\{revision\}/);
  assert.match(source, /browserApi\.POST\([\s\S]*\/revisions\/\{revision\}\/restore/);
  assert.match(source, /browserApi\.PUT\(\s*"\/api\/v1\/review-artifacts\/\{artifact_id\}\/outline"/);
  assert.match(source, /browserApi\.POST\([\s\S]*\/review-artifacts\/\{artifact_id\}\/decision/);
  assert.match(source, /browserApi\.POST\("\/api\/v1\/writing\/runs"/);
  assert.match(source, /browserApi\.PATCH\(\s*"\/api\/v1\/novels\/\{novel_id\}\/title"/);
  assert.match(source, /browserApi\.GET\(\s*"\/api\/v1\/novels\/\{novel_id\}\/workspace\/planning"/);
  assert.match(source, /browserApi\.PUT\(\s*"\/api\/v1\/novels\/\{novel_id\}\/writing-bible"/);
});

test("中短篇工作区把会话原话与大纲版本组合为可连续修改的对话", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /buildShortStoryOutlineConversation/);
  assert.match(source, /<ShortStoryOutlineConversation/);
  assert.match(source, /messages:\s*outlineConversationMessages/);
  assert.match(source, /onSubmit=\{submitOutlineRevisionRequest\}/);
  assert.match(source, /setOutlineRevisionRequest\(""\)/);
});

test("中短篇工作区不会直接展示英文操作、阶段、审核结论或 revision", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /formatShortStoryOperation\(latestTask\.operation\)/);
  assert.match(source, /formatShortStoryPhase\(latestTask\.phase\)/);
  assert.match(source, /formatShortStoryVerdict\(evaluation\.verdict\)/);
  assert.doesNotMatch(source, /\{latestTask\.operation\}|\{latestTask\.phase\}/);
  assert.doesNotMatch(source, />\{evaluation\.verdict\}</);
  assert.doesNotMatch(
    source,
    /保存为新 revision|当前为 revision|基于 revision|来源大纲 revision|>revision \{|历史 revision|恢复此版本为新 revision/,
  );
});

test("中短篇决策使用 expectedRevision 且从不发送 editedContent", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /expectedRevision:\s*artifact\.revision/);
  assert.doesNotMatch(source, /editedContent/);
});

test("正文工作区呈现编辑与校验两类全稿审核结论", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /编辑审核/);
  assert.match(source, /校验审核/);
  assert.match(source, /evaluations/);
});

test("中短篇工作区可保存、修改和清空篇幅参考", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /parseOptionalShortStoryTarget\(targetInput\)/);
  assert.match(source, /buildWritingBibleTargetUpdate\(planning\.writingBible, target\)/);
  assert.match(source, /篇幅参考（可选）/);
  assert.match(source, /typeof draftPayload\.metadata\.targetWordCount === "number"[\s\S]{0,160}篇幅参考约/);
});

test("旧中短篇多 Chapter 仍可打开但明确阻断新流程", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /bootstrap\.chapters\.length/);
  assert.match(source, /需整理为单一正文后才能启动新中短篇流程/);
  assert.match(source, /bootstrap\.chapters\.map/);
  assert.match(source, /buildWorkspaceChapterHref/);
  assert.match(source, /<Link[\s\S]{0,260}chapter\.id/);
  assert.match(source, /currentChapter\?\.content/);
});

test("正文和正式正文 pane 不读取或恢复大纲 revision", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /shouldLoadOutlineRevisions\(activePane/);
  assert.match(source, /canRestoreOutlineRevision/);
  assert.match(source, /activePane !== "outline"/);
  assert.match(source, /setRevisions\(\[\]\)/);
  assert.match(source, /setRevisionDetail\(null\)/);
});

test("大纲保存使用独立编辑基线并立即应用 PUT 返回结果", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /editorBaseArtifactId/);
  assert.match(source, /editorBaseRevision/);
  assert.match(source, /expectedRevision:\s*editorBaseRevision/);
  assert.match(source, /applySavedOutlineToAggregate/);
  assert.match(source, /基于最新版本重试/);
});

test("首次聚合成功前只允许重试读取状态，活跃任务锁住所有 mutation", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /authoritativeStateReady:\s*aggregate !== null/);
  assert.match(source, /重试读取状态/);
  assert.match(source, /isShortStoryInteractionLocked/);
  assert.match(source, /taskPhase:\s*latestTask\?\.phase/);
});

test("标题 revision 冲突提供整页刷新入口，避免继续使用陈旧 updatedAt", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /actionKey\.startsWith\("title:"\)/);
  assert.match(source, /setTitleConflict\(true\)/);
  assert.match(source, /window\.location\.reload\(\)/);
  assert.match(source, /刷新页面同步标题/);
});

test("页面可见性变化会先取消旧轮询 timer 再重排或立即刷新", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /pollingTimerRef/);
  assert.match(source, /clearPollingTimer\(\);[\s\S]{0,180}setPageVisible\(isVisible\)/);
  assert.match(source, /shouldRefreshOnVisibilityChange[\s\S]{0,180}refreshAggregate\(\)/);
});

test("轮询状态类型直接派生生成客户端 schema", async () => {
  const pollingUrl = new URL("../short-story/short-story-polling.ts", import.meta.url);
  const source = await readFile(pollingUrl, "utf8");

  assert.match(source, /import type \{ components \} from "@inkforge\/api-client"/);
  assert.match(source, /ShortStoryTaskStatus"\]\["latestCommandStatus"\]/);
  assert.match(source, /ShortStoryArtifactResponse"\]\["status"\]/);
});

test("正文草案应用成功后刷新 bootstrap 中的正式正文", async () => {
  const workspaceUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const source = await readFile(workspaceUrl, "utf8");

  assert.match(source, /useRouter\(\)/);
  assert.match(source, /previous\?\.chapterDraft\?\.status\s*!==\s*"applied"/);
  assert.match(source, /next\.chapterDraft\?\.status\s*===\s*"applied"/);
  assert.match(source, /router\.refresh\(\)/);
});

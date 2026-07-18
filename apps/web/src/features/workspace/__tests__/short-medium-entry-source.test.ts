import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("新建作品入口不默认选择篇幅并按篇幅显示两套表单", async () => {
  const modalUrl = new URL("../../projects/create-novel-modal.tsx", import.meta.url);
  const source = await readFile(modalUrl, "utf8");

  assert.match(source, /useState<StoryLengthProfile \| null>\(null\)/);
  assert.match(source, /storyLengthProfile === "short_medium"/);
  assert.match(source, /storyLengthProfile === "long_serial"/);
  assert.match(source, /name="inspiration"/);
  assert.match(source, /min=\{6_000\}/);
  assert.match(source, /max=\{80_000\}/);
  assert.match(source, /暂定标题（可选）/);
  assert.match(source, /第一章目标/);
  assert.doesNotMatch(source, /chapterCount/);
});

test("中短篇创建后显式建立会话并启动大纲任务", async () => {
  const modalUrl = new URL("../../projects/create-novel-modal.tsx", import.meta.url);
  const source = await readFile(modalUrl, "utf8");

  assert.match(source, /browserApi\.POST\("\/api\/v1\/novels"/);
  assert.match(source, /browserApi\.POST\("\/api\/v1\/writing\/sessions"/);
  assert.match(source, /browserApi\.POST\("\/api\/v1\/writing\/runs"/);
  assert.match(source, /workflowKind:\s*"short_medium"/);
  assert.match(source, /operation:\s*"develop_short_outline"/);
  assert.match(source, /writingSessionId:\s*session\.id/);
  assert.match(source, /router\.push\(`\/workspace\/\$\{result\.novelId\}`\)/);
  assert.match(source, /catch \(error\)[\s\S]*router\.push/);
});

test("作品列表直接使用生成客户端的 DashboardNovel 并展示篇幅", async () => {
  const listUrl = new URL("../../projects/novel-list-client.tsx", import.meta.url);
  const source = await readFile(listUrl, "utf8");

  assert.match(source, /import type \{ components \} from "@inkforge\/api-client"/);
  assert.match(source, /components\["schemas"\]\["DashboardNovel"\]\[\]/);
  assert.doesNotMatch(source, /type NovelItem\s*=/);
  assert.match(source, /storyLengthProfile/);
  assert.match(source, /targetTotalWordCount/);
});

test("现有写作会话显式使用长篇流程并提交草案版本", async () => {
  const conversationUrl = new URL("../../writing/writing-conversation.tsx", import.meta.url);
  const source = await readFile(conversationUrl, "utf8");
  const startBody = source.match(/browserApi\.POST\("\/api\/v1\/writing\/runs"[\s\S]*?\n\s*\}\)\);/)?.[0] ?? "";

  assert.match(startBody, /workflowKind:\s*"long_serial"/);
  assert.match(startBody, /operation:\s*null/);
  assert.match(source, /expectedRevision:\s*artifact\.revision/);
});

test("端到端辅助函数区分长篇与中短篇创建契约", async () => {
  const helperUrl = new URL("../../../../../../tests/e2e/helpers.ts", import.meta.url);
  const source = await readFile(helperUrl, "utf8");
  const longHelper = source.match(/export async function createNovelWithApi[\s\S]*?\n\}/)?.[0] ?? "";
  const shortHelper = source.match(/export async function createShortNovelWithApi[\s\S]*?\n\}/)?.[0] ?? "";

  assert.match(longHelper, /storyLengthProfile:\s*"long_serial"/);
  assert.match(longHelper, /firstChapterGoal/);
  assert.match(shortHelper, /storyLengthProfile:\s*"short_medium"/);
  assert.match(shortHelper, /inspiration/);
  assert.doesNotMatch(shortHelper, /genre|protagonist|firstChapterGoal/);
});

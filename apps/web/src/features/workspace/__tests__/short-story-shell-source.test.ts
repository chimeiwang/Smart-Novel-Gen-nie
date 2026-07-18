import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("工作区入口只按篇幅类型分流", async () => {
  const shellUrl = new URL("../workspace-shell.tsx", import.meta.url);
  const source = await readFile(shellUrl, "utf8");

  assert.match(source, /bootstrap\.storyLengthProfile === "short_medium"/);
  assert.match(source, /<ShortStoryWorkspace/);
  assert.match(source, /<LongSerialWorkspace/);
  assert.doesNotMatch(source, /SmartWritingPanel|ChapterEditor|ChapterList|LibraryPane/);
});

test("长篇原工作区被完整隔离，短篇工作区不导入长篇写作组件", async () => {
  const longUrl = new URL("../long-serial-workspace.tsx", import.meta.url);
  const shortUrl = new URL("../short-story/short-story-workspace.tsx", import.meta.url);
  const [longSource, shortSource] = await Promise.all([
    readFile(longUrl, "utf8"),
    readFile(shortUrl, "utf8"),
  ]);

  assert.match(longSource, /<SmartWritingPanel/);
  assert.match(longSource, /<ChapterEditor/);
  assert.match(longSource, /<ChapterList/);
  assert.match(longSource, /<LibraryPane/);
  assert.doesNotMatch(
    shortSource,
    /WritingConversation|SmartWritingPanel|ChapterEditor|ChapterList|BeatPlan|beat-plan|LibraryPane/,
  );
});


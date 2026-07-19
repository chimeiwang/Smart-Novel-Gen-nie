import assert from "node:assert/strict";
import test from "node:test";

import type { components } from "@inkforge/api-client";

import { buildShortStoryOutlineConversation } from "../short-story/short-story-outline-conversation-model";

type Message = components["schemas"]["MessageResponse"];
type Revision = components["schemas"]["ReviewArtifactRevisionSummary"];

function message(overrides: Partial<Message>): Message {
  return {
    id: "message-1",
    sessionId: "session-1",
    role: "user",
    agentId: null,
    content: "只修改第二节，让冲突更早出现",
    intent: "revision_focus",
    metadata: {
      source: "workflow",
      artifactId: "outline-1",
      sourceRevision: 1,
    },
    parentId: null,
    createdAt: "2026-07-19T01:00:00Z",
    ...overrides,
  };
}

function revision(value: number, summary: string | null = `完成版本 ${value}`): Revision {
  return {
    artifactId: "outline-1",
    revision: value,
    summary,
    createdByAgent: "剧情",
    createdAt: `2026-07-19T0${value}:10:00Z`,
  };
}

test("把用户改纲原话与其产生的大纲版本相邻展示", () => {
  const entries = buildShortStoryOutlineConversation({
    artifactId: "outline-1",
    currentRevision: 3,
    taskActive: false,
    messages: [
      message({ id: "request-1" }),
      message({
        id: "request-2",
        content: "保留结局，只重写第三节",
        metadata: { artifactId: "outline-1", sourceRevision: 2 },
        createdAt: "2026-07-19T02:00:00Z",
      }),
    ],
    revisions: [revision(3), revision(2), revision(1)],
  });

  assert.deepEqual(
    entries.map((entry) => [entry.kind, entry.content, entry.revision]),
    [
      ["outline_result", "完成版本 1", 1],
      ["user_request", "只修改第二节，让冲突更早出现", 1],
      ["outline_result", "完成版本 2", 2],
      ["user_request", "保留结局，只重写第三节", 2],
      ["outline_result", "完成版本 3", 3],
    ],
  );
});

test("忽略其他大纲、其他意图和非法 metadata 的消息", () => {
  const entries = buildShortStoryOutlineConversation({
    artifactId: "outline-1",
    currentRevision: 1,
    taskActive: false,
    messages: [
      message({ id: "other-artifact", metadata: { artifactId: "outline-2", sourceRevision: 1 } }),
      message({ id: "other-intent", intent: "chat" }),
      message({ id: "invalid-metadata", metadata: "invalid" }),
    ],
    revisions: [revision(1)],
  });

  assert.deepEqual(entries.map((entry) => entry.kind), ["outline_result"]);
});

test("任务执行中保留用户原话并显示正在修改", () => {
  const entries = buildShortStoryOutlineConversation({
    artifactId: "outline-1",
    currentRevision: 1,
    taskActive: true,
    messages: [message({ id: "pending-request" })],
    revisions: [revision(1)],
  });

  assert.equal(entries.at(-1)?.kind, "outline_result");
  assert.equal(entries.at(-1)?.state, "processing");
  assert.equal(entries.at(-1)?.revision, null);
});

test("任务结束但内容未变化时明确显示已处理且版本未变化", () => {
  const entries = buildShortStoryOutlineConversation({
    artifactId: "outline-1",
    currentRevision: 1,
    taskActive: false,
    messages: [message({ id: "unchanged-request" })],
    revisions: [revision(1)],
  });

  assert.equal(entries.at(-1)?.state, "unchanged");
  assert.equal(entries.at(-1)?.content, "已处理，完整大纲内容未变化");
});

test("旧项目没有用户消息时仍按顺序展示全部版本结果", () => {
  const entries = buildShortStoryOutlineConversation({
    artifactId: "outline-1",
    currentRevision: 3,
    taskActive: false,
    messages: [],
    revisions: [revision(3), revision(1), revision(2, null)],
  });

  assert.deepEqual(entries.map((entry) => entry.revision), [1, 2, 3]);
  assert.equal(entries[1]?.content, "已生成新的完整大纲");
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { components } from "@inkforge/api-client";

import {
  createWritingSessionTitle,
  formatSessionDisplayTitle,
  mapWritingPhaseToPersistentPhase,
  selectDefaultWritingSessionId,
} from "../session-presentation";

type SessionCandidate = components["schemas"]["WritingSessionListItem"];

const session = (
  id: string,
  updatedAt: string,
  overrides: Partial<SessionCandidate> = {},
): SessionCandidate => ({
  id,
  novelId: "novel-1",
  chapterId: "chapter-1",
  title: null,
  phase: "idle",
  createdAt: "2026-07-15T08:00:00Z",
  updatedAt,
  messageCount: 0,
  lastMessage: null,
  ...overrides,
});

describe("会话默认选择", () => {
  it("活动阶段会话优先于更近的普通历史会话", () => {
    const sessions = [
      session("recent-idle", "2026-07-16T10:00:00Z"),
      session("discussing", "2026-07-16T07:00:00Z", {
        phase: "discussing",
      }),
      session("generating", "2026-07-16T08:00:00Z", {
        phase: "generating",
      }),
      session("recording", "2026-07-16T09:00:00Z", {
        phase: "recording",
      }),
    ];

    assert.equal(selectDefaultWritingSessionId(sessions), "recording");
  });

  it("没有活动阶段会话时选择 updatedAt 最近者", () => {
    const sessions = [
      session("older", "2026-07-15T10:00:00Z"),
      session("newer", "2026-07-16T10:00:00Z"),
    ];

    assert.equal(selectDefaultWritingSessionId(sessions), "newer");
    assert.equal(selectDefaultWritingSessionId([]), null);
  });
});

describe("会话可读标题", () => {
  it("优先使用去除首尾空白后的显式标题", () => {
    assert.equal(
      formatSessionDisplayTitle(session("one", "2026-07-16T10:00:00Z", {
        title: "  第三章冲突设计  ",
        lastMessage: {
          content: "这条消息不应覆盖标题",
          role: "user",
          agentId: null,
        },
      })),
      "第三章冲突设计",
    );
  });

  it("标题仅含空白时降级使用最后消息摘要", () => {
    assert.equal(
      formatSessionDisplayTitle(session("one", "2026-07-16T10:00:00Z", {
        title: "  \n ",
        lastMessage: {
          content: "  请先梳理\n\n第三章冲突  ",
          role: "user",
          agentId: null,
        },
      })),
      "请先梳理 第三章冲突",
    );
  });

  it("标题和最后消息仅含空白时回退未命名会话", () => {
    assert.equal(
      formatSessionDisplayTitle(session("empty", "2026-07-16T10:00:00Z", {
        title: "  ",
        lastMessage: {
          content: " \n\t ",
          role: "user",
          agentId: null,
        },
      })),
      "未命名会话",
    );
  });

  it("摘要超过上限时截断并追加省略号", () => {
    assert.equal(
      formatSessionDisplayTitle(session("one", "2026-07-16T10:00:00Z", {
        lastMessage: {
          content: "一二三四五六七八九十",
          role: "agent",
          agentId: "写作",
        },
      }), 6),
      "一二三四五六…",
    );
    assert.equal(
      formatSessionDisplayTitle(session("empty", "2026-07-16T10:00:00Z")),
      "未命名会话",
    );
  });
});

describe("新会话标题", () => {
  it("合并空白并按上限截断自由输入", () => {
    assert.equal(createWritingSessionTitle("  请先梳理\n\n第三章  冲突  ", 10), "请先梳理 第三章 冲");
  });

  it("空任务使用未命名会话", () => {
    assert.equal(createWritingSessionTitle(" \n\t "), "未命名会话");
  });
});

describe("会话阶段持久化", () => {
  it("将等待审核相关 UI 阶段统一记录为 recording", () => {
    assert.equal(mapWritingPhaseToPersistentPhase("reviewing"), "recording");
    assert.equal(mapWritingPhaseToPersistentPhase("awaiting"), "recording");
  });

  it("错误阶段不写入会话", () => {
    assert.equal(mapWritingPhaseToPersistentPhase("error"), null);
  });

  it("其余可持久阶段保持契约值", () => {
    assert.equal(mapWritingPhaseToPersistentPhase("discussing"), "discussing");
    assert.equal(mapWritingPhaseToPersistentPhase("generating"), "generating");
    assert.equal(mapWritingPhaseToPersistentPhase("recording"), "recording");
    assert.equal(mapWritingPhaseToPersistentPhase("completed"), "completed");
    assert.equal(mapWritingPhaseToPersistentPhase("idle"), "idle");
  });
});

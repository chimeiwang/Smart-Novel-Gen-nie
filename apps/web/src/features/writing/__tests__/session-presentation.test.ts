import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  formatSessionDisplayTitle,
  selectDefaultWritingSessionId,
} from "../session-presentation";

type SessionCandidate = {
  id: string;
  title: string | null;
  phase: string;
  updatedAt: string;
  currentTask: { phase: string } | null;
  firstMessage?: { content: string } | null;
  lastMessage?: { content: string } | null;
};

const session = (
  id: string,
  updatedAt: string,
  overrides: Partial<SessionCandidate> = {},
): SessionCandidate => ({
  id,
  title: null,
  phase: "idle",
  updatedAt,
  currentTask: null,
  ...overrides,
});

describe("会话默认选择", () => {
  it("活动或 awaiting 会话优先于更近的普通历史会话", () => {
    const sessions = [
      session("recent-idle", "2026-07-16T10:00:00Z"),
      session("active", "2026-07-16T08:00:00Z", {
        currentTask: { phase: "active" },
      }),
      session("awaiting", "2026-07-16T09:00:00Z", {
        phase: "awaiting_user_review",
      }),
    ];

    assert.equal(selectDefaultWritingSessionId(sessions), "awaiting");
  });

  it("没有活动或 awaiting 会话时选择 updatedAt 最近者", () => {
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
        firstMessage: { content: "这条消息不应覆盖标题" },
      })),
      "第三章冲突设计",
    );
  });

  it("没有标题时依次使用首条消息和最后消息摘要", () => {
    assert.equal(
      formatSessionDisplayTitle(session("one", "2026-07-16T10:00:00Z", {
        firstMessage: { content: "  请先梳理\n\n第三章冲突  " },
        lastMessage: { content: "最后回复" },
      })),
      "请先梳理 第三章冲突",
    );
    assert.equal(
      formatSessionDisplayTitle(session("two", "2026-07-16T10:00:00Z", {
        lastMessage: { content: "只有最后消息" },
      })),
      "只有最后消息",
    );
  });

  it("摘要超过上限时截断并追加省略号", () => {
    assert.equal(
      formatSessionDisplayTitle(session("one", "2026-07-16T10:00:00Z", {
        firstMessage: { content: "一二三四五六七八九十" },
      }), 6),
      "一二三四五六…",
    );
    assert.equal(
      formatSessionDisplayTitle(session("empty", "2026-07-16T10:00:00Z")),
      "未命名会话",
    );
  });
});

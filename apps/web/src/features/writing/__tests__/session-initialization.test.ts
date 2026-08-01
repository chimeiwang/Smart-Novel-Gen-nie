import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { coordinateWritingSessionInitialization } from "../session-initialization";

describe("写作会话初始化", () => {
  it("先重置会话代际，再开始消息和草案读取", async () => {
    const calls: string[] = [];
    const sessions = [{ id: "session-1" }];

    await coordinateWritingSessionInitialization({
      sessions,
      alreadyInitialized: false,
      selectDefaultSessionId: () => "session-1",
      resetSessionContext: (sessionId) => calls.push(`reset:${sessionId}`),
      loadSessionMessages: async (sessionId) => {
        calls.push(`messages:${sessionId}`);
      },
      loadReviewArtifacts: async (loadedSessions) => {
        assert.equal(loadedSessions, sessions);
        calls.push("artifacts");
      },
    });

    assert.deepEqual(calls, [
      "reset:session-1",
      "messages:session-1",
      "artifacts",
    ]);
  });

  it("会话已初始化时只刷新草案集合", async () => {
    const calls: string[] = [];

    await coordinateWritingSessionInitialization({
      sessions: [{ id: "session-1" }],
      alreadyInitialized: true,
      selectDefaultSessionId: () => "session-1",
      resetSessionContext: () => calls.push("reset"),
      loadSessionMessages: async () => {
        calls.push("messages");
      },
      loadReviewArtifacts: async () => {
        calls.push("artifacts");
      },
    });

    assert.deepEqual(calls, ["artifacts"]);
  });
});

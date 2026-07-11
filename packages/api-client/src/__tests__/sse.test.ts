import assert from "node:assert/strict";
import test from "node:test";

import { createSseState, parseSseFrame } from "../sse";

test("解析事件并保存 Last-Event-ID，忽略心跳和重复序号", () => {
  const state = createSseState();
  const first = parseSseFrame(
    "id: event-1\nevent: agent_start\ndata: {\"sequence\":1,\"agentId\":\"写作\"}\n\n",
    state,
  );
  const heartbeat = parseSseFrame(": heartbeat\n\n", state);
  const duplicate = parseSseFrame(
    "id: event-1-copy\nevent: agent_start\ndata: {\"sequence\":1}\n\n",
    state,
  );
  assert.deepEqual(first, {
    id: "event-1",
    event: "agent_start",
    data: { sequence: 1, agentId: "写作" },
  });
  assert.equal(heartbeat, null);
  assert.equal(duplicate, null);
  assert.equal(state.lastEventId, "event-1");
  assert.equal(state.lastSequence, 1);
});

test("序号出现缺口时明确报错", () => {
  const state = createSseState({ lastEventId: "event-1", lastSequence: 1 });
  assert.throws(
    () =>
      parseSseFrame(
        "id: event-3\nevent: agent_chunk\ndata: {\"sequence\":3}\n\n",
        state,
      ),
    /事件序号不连续/,
  );
});

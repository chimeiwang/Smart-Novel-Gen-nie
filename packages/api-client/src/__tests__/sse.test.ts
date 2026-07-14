import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
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

test("共享样例能通过真实 SSE 帧解析器", async () => {
  const fixtureUrl = new URL(
    "../../../service-contracts/contracts/writing-sse-events.json",
    import.meta.url,
  );
  const examples = JSON.parse(await readFile(fixtureUrl, "utf8")) as Array<{
    event: string;
    envelope: {
      eventId: string;
      sequence: number;
      data: Record<string, unknown>;
    };
  }>;
  const state = createSseState();

  for (const example of examples) {
    const frame = [
      `id: ${example.envelope.eventId}`,
      `event: ${example.event}`,
      `data: ${JSON.stringify({ ...example.envelope.data, sequence: example.envelope.sequence })}`,
      "",
      "",
    ].join("\n");
    const parsed = parseSseFrame(frame, state);
    assert.equal(parsed?.event, example.event);
    assert.deepEqual(parsed?.data, {
      ...example.envelope.data,
      sequence: example.envelope.sequence,
    });
  }
});

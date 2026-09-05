import { createSseRequestHeaders, createSseState, parseSseFrame, type components } from "@inkforge/api-client";

import { parseSseEvent } from "@/shared/contracts/sse-events";
import { monitorRunStream } from "../writing/run-stream-monitor";
import { decideShortRunStatus, type ShortRunStatus } from "./short-run-outcome";

type V2Run = components["schemas"]["WritingRunV2Response"];
type Options = {
  open: (headers: HeadersInit, signal: AbortSignal) => Promise<Response>;
  readRun: () => Promise<ShortRunStatus>;
  signal: AbortSignal;
  wait?: (milliseconds: number, signal?: AbortSignal) => Promise<void>;
};

/** 事件只唤醒结果回读；候选和完整报告始终来自同一 Run 的 GET。 */
export async function observeShortV2Run(initial: V2Run, options: Options): Promise<ShortRunStatus> {
  const cursor = createSseState();
  let latest: ShortRunStatus = initial;
  const wrongIdentity = (run: ShortRunStatus) => run.engineVersion !== 2 || run.runId !== initial.runId
    || run.workflow !== "short_medium" || run.operation !== initial.operation;
  const terminal = (run: ShortRunStatus) => wrongIdentity(run) || decideShortRunStatus(run).kind !== "continue";

  if (terminal(initial)) {
    latest = await options.readRun();
  } else {
    await monitorRunStream<ShortRunStatus>({
      signal: options.signal,
      wait: options.wait,
      open: () => options.open(createSseRequestHeaders(cursor), options.signal),
      consume: async (response) => {
        if (!response.ok || !response.body) throw new Error("中短篇事件流不可用");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let received = false;
        let wake = false;
        const frame = (value: string) => {
          const proposedCursor = { ...cursor };
          const parsed = parseSseFrame(value, proposedCursor);
          if (!parsed) return;
          const event = parseSseEvent(parsed.data, parsed.event);
          if (!event || (event.type !== "run_snapshot" && event.type !== "workflow_event")
            || event.runId !== initial.runId) return;
          if (event.type === "run_snapshot") {
            if (event.snapshot.workflow !== "short_medium" || event.snapshot.operation !== initial.operation) return;
            cursor.lastSequence = event.baseSequence;
            cursor.lastEventId = event.baseSequence > 0 ? String(event.baseSequence) : null;
            wake = !["pending", "running"].includes(event.snapshot.status);
          } else {
            if (parsed.id !== String(event.sequence)) throw new Error("中短篇事件游标与序号不一致");
            Object.assign(cursor, proposedCursor);
            wake = ["completed", "failed", "cancelled"].includes(event.eventType);
          }
          received = true;
        };
        try {
          while (true) {
            const next = await reader.read();
            if (next.done) {
              buffer += decoder.decode();
              if (buffer.trim()) frame(buffer);
              return received;
            }
            buffer += decoder.decode(next.value, { stream: true });
            buffer = buffer.replaceAll("\r\n", "\n");
            const frames = buffer.split("\n\n");
            buffer = frames.pop() ?? "";
            for (const value of frames) {
              frame(value);
              if (wake) return received;
            }
          }
        } finally {
          await reader.cancel();
        }
      },
      readOutcome: options.readRun,
      handleOutcome: (run) => { latest = run; },
      shouldClose: terminal,
    });
  }
  if (wrongIdentity(latest)) throw new Error("中短篇任务的权威引擎或身份发生变化，已停止处理。");
  return latest;
}

export interface SseState {
  lastEventId: string | null;
  lastSequence: number;
}

export interface ParsedSseEvent<T = unknown> {
  id: string | null;
  event: string;
  data: T;
}

export function createSseState(initial?: Partial<SseState>): SseState {
  return {
    lastEventId: initial?.lastEventId ?? null,
    lastSequence: initial?.lastSequence ?? 0,
  };
}

export function createSseRequestHeaders(state: SseState): HeadersInit {
  return state.lastEventId ? { "Last-Event-ID": state.lastEventId } : {};
}

export function parseSseFrame(
  frame: string,
  state: SseState,
): ParsedSseEvent<Record<string, unknown>> | null {
  const normalized = frame.replace(/\r\n/g, "\n");
  if (!normalized.trim() || normalized.trimStart().startsWith(":")) return null;

  let id: string | null = null;
  let event = "message";
  const dataLines: string[] = [];
  for (const line of normalized.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    const raw = separator < 0 ? "" : line.slice(separator + 1);
    const value = raw.startsWith(" ") ? raw.slice(1) : raw;
    if (field === "id") id = value;
    else if (field === "event") event = value || "message";
    else if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  const parsed: unknown = JSON.parse(dataLines.join("\n"));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("SSE data 必须是对象");
  }
  const data = parsed as Record<string, unknown>;
  const sequence = data.sequence;
  if (typeof sequence === "number") {
    if (!Number.isSafeInteger(sequence) || sequence < 1) {
      throw new Error("SSE 事件序号无效");
    }
    if (sequence <= state.lastSequence) return null;
    if (sequence !== state.lastSequence + 1) {
      throw new Error(
        `SSE 事件序号不连续：期望 ${state.lastSequence + 1}，收到 ${sequence}`,
      );
    }
    state.lastSequence = sequence;
  }
  if (id) state.lastEventId = id;
  return { id, event, data };
}

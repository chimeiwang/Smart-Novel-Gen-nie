import {
  createSseRequestHeaders,
  createSseState,
  type SseState,
} from "@inkforge/api-client";

export type WritingEventCursors = ReturnType<typeof createWritingEventCursors>;

export function createWritingEventCursors() {
  const states = new Map<string, SseState>();

  const state = (taskId: string): SseState => {
    const existing = states.get(taskId);
    if (existing) return existing;
    const created = createSseState();
    states.set(taskId, created);
    return created;
  };

  return {
    state,
    headers(taskId: string): HeadersInit {
      return createSseRequestHeaders(state(taskId));
    },
    update(taskId: string, eventId: string | null): void {
      if (eventId) state(taskId).lastEventId = eventId;
    },
  };
}

import type { components } from "@inkforge/api-client";

type WritingSessionListItem = components["schemas"]["WritingSessionListItem"];
type SessionSelectionCandidate = Pick<
  WritingSessionListItem,
  "id" | "phase" | "updatedAt"
>;
type SessionTitleCandidate = Pick<WritingSessionListItem, "title" | "lastMessage">;
type SessionHistoryCandidate = Pick<WritingSessionListItem, "messageCount">;

const ACTIVE_PHASES = new Set(["discussing", "generating", "recording"]);
const DEFAULT_TITLE_LIMIT = 40;

export type PersistedWritingSessionPhase =
  | "idle"
  | "discussing"
  | "generating"
  | "recording"
  | "completed";

export function filterNonEmptyWritingSessions<T extends SessionHistoryCandidate>(
  sessions: readonly T[],
): T[] {
  return sessions.filter((session) => session.messageCount > 0);
}

export function selectDefaultWritingSessionId(
  sessions: readonly SessionSelectionCandidate[],
): string | null {
  const activeSessions = sessions.filter((session) => ACTIVE_PHASES.has(session.phase));
  const candidates = activeSessions.length > 0 ? activeSessions : sessions;
  let selected: SessionSelectionCandidate | undefined;
  let selectedTimestamp = Number.NEGATIVE_INFINITY;

  for (const candidate of candidates) {
    const parsedTimestamp = Date.parse(candidate.updatedAt);
    const timestamp = Number.isFinite(parsedTimestamp)
      ? parsedTimestamp
      : Number.NEGATIVE_INFINITY;

    if (!selected || timestamp > selectedTimestamp) {
      selected = candidate;
      selectedTimestamp = timestamp;
    }
  }

  return selected?.id ?? null;
}

export function formatSessionDisplayTitle(
  session: SessionTitleCandidate,
  maxLength = DEFAULT_TITLE_LIMIT,
): string {
  const explicitTitle = normalizeWhitespace(session.title);
  if (explicitTitle) {
    return explicitTitle;
  }

  const messageSummary = normalizeWhitespace(session.lastMessage?.content);
  if (!messageSummary) {
    return "未命名会话";
  }

  return messageSummary.length > maxLength
    ? `${messageSummary.slice(0, maxLength)}…`
    : messageSummary;
}

export function createWritingSessionTitle(
  task: string,
  maxLength = DEFAULT_TITLE_LIMIT,
): string {
  const normalized = normalizeWhitespace(task);
  if (!normalized) return "未命名会话";
  return normalized.slice(0, Math.max(1, maxLength));
}

export function mapWritingPhaseToPersistentPhase(
  phase: string,
): PersistedWritingSessionPhase | null {
  if (phase === "reviewing" || phase === "awaiting") return "recording";
  if (phase === "error") return null;
  if (
    phase === "idle" ||
    phase === "discussing" ||
    phase === "generating" ||
    phase === "recording" ||
    phase === "completed"
  ) {
    return phase;
  }
  return null;
}

function normalizeWhitespace(value: string | null | undefined): string {
  return value?.trim().replace(/\s+/g, " ") ?? "";
}

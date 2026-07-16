import type { components } from "@inkforge/api-client";

type WritingSessionListItem = components["schemas"]["WritingSessionListItem"];
type SessionSelectionCandidate = Pick<
  WritingSessionListItem,
  "id" | "phase" | "updatedAt"
>;
type SessionTitleCandidate = Pick<WritingSessionListItem, "title" | "lastMessage">;

const ACTIVE_PHASES = new Set(["discussing", "generating", "recording"]);
const DEFAULT_TITLE_LIMIT = 40;

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

function normalizeWhitespace(value: string | null | undefined): string {
  return value?.trim().replace(/\s+/g, " ") ?? "";
}

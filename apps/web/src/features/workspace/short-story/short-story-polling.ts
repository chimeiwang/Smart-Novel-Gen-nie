import type { components } from "@inkforge/api-client";

export type ShortStoryCommandStatus =
  components["schemas"]["ShortStoryTaskStatus"]["latestCommandStatus"];

export type ShortStoryArtifactStatus =
  components["schemas"]["ShortStoryArtifactResponse"]["status"];

const ACTIVE_COMMAND_STATUSES = new Set<ShortStoryCommandStatus>([
  "pending",
  "submitted",
  "processing",
]);
const ACTIVE_TASK_PHASES = new Set(["active", "waiting_call"]);
const TERMINAL_TASK_PHASES = new Set([
  "awaiting_user",
  "awaiting_user_review",
  "completed",
  "error",
]);
const ACTIVE_ARTIFACT_STATUSES = new Set<ShortStoryArtifactStatus>([
  "draft",
  "under_review",
  "applying",
]);
const ERROR_BACKOFF = [2_000, 4_000, 8_000, 15_000] as const;

export function getAcceptedPollingStatus(
  status: ShortStoryCommandStatus,
): ShortStoryCommandStatus {
  return ACTIVE_COMMAND_STATUSES.has(status) ? status : "pending";
}

export function getShortStoryPollDelay({
  visible,
  consecutiveErrors,
}: {
  visible: boolean;
  consecutiveErrors: number;
}): number {
  if (consecutiveErrors > 0) {
    return ERROR_BACKOFF[Math.min(consecutiveErrors, ERROR_BACKOFF.length) - 1];
  }
  return visible ? 2_000 : 10_000;
}

export function shouldPollShortStory({
  commandStatus,
  taskPhase,
  artifactStatuses,
}: {
  commandStatus: ShortStoryCommandStatus | null;
  taskPhase: string | null;
  artifactStatuses: ReadonlyArray<ShortStoryArtifactStatus | null>;
}): boolean {
  if (commandStatus && ACTIVE_COMMAND_STATUSES.has(commandStatus)) return true;
  if (taskPhase && TERMINAL_TASK_PHASES.has(taskPhase)) return false;
  if (taskPhase && ACTIVE_TASK_PHASES.has(taskPhase)) return true;
  return artifactStatuses.some(
    (status) => status !== null && ACTIVE_ARTIFACT_STATUSES.has(status),
  );
}

export function shouldRefreshOnVisibilityChange(
  wasVisible: boolean,
  isVisible: boolean,
): boolean {
  return !wasVisible && isVisible;
}

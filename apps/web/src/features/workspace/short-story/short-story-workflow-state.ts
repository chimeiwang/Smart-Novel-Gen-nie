import type {
  ShortStoryArtifactStatus,
  ShortStoryCommandStatus,
} from "./short-story-polling";

type ShortStoryActionState = {
  canRetryOutline: boolean;
  canEditOutline: boolean;
  canDecideOutline: boolean;
  canGenerateDraft: boolean;
  canReviseDraft: boolean;
  canDecideDraft: boolean;
  canUpdateTargetWordCount: boolean;
  targetWordCountValid: boolean;
};

const ACTIVE_COMMAND_STATUSES = new Set<ShortStoryCommandStatus>([
  "pending",
  "submitted",
  "processing",
]);
const ACTIVE_TASK_PHASES = new Set(["active", "waiting_call"]);

export function isValidShortStoryTarget(targetWordCount: number | null): targetWordCount is number {
  return targetWordCount !== null
    && Number.isInteger(targetWordCount)
    && targetWordCount >= 6_000
    && targetWordCount <= 80_000;
}

export function deriveShortStoryActions({
  authoritativeStateReady = true,
  targetWordCount,
  chapterCount = 1,
  outlineStatus,
  draftStatus,
  commandStatus,
  taskPhase,
}: {
  authoritativeStateReady?: boolean;
  targetWordCount: number | null;
  chapterCount?: number;
  outlineStatus: ShortStoryArtifactStatus | null;
  draftStatus: ShortStoryArtifactStatus | null;
  commandStatus: ShortStoryCommandStatus | null;
  taskPhase: string | null;
}): ShortStoryActionState {
  const targetWordCountValid = isValidShortStoryTarget(targetWordCount);
  const chapterStructureCompatible = authoritativeStateReady && chapterCount === 1;
  const busy = Boolean(
    (commandStatus && ACTIVE_COMMAND_STATUSES.has(commandStatus))
    || (taskPhase && ACTIVE_TASK_PHASES.has(taskPhase)),
  );
  const outlineAwaitingUser = outlineStatus === "awaiting_user" && !busy;
  const draftAwaitingUser = draftStatus === "awaiting_user" && !busy;

  return {
    canRetryOutline: chapterStructureCompatible
      && targetWordCountValid
      && outlineStatus === null
      && !busy,
    canEditOutline: chapterStructureCompatible && outlineAwaitingUser,
    canDecideOutline: chapterStructureCompatible && outlineAwaitingUser,
    canGenerateDraft: chapterStructureCompatible
      && targetWordCountValid
      && outlineStatus === "applied"
      && draftStatus === null
      && !busy,
    canReviseDraft: chapterStructureCompatible && draftAwaitingUser,
    canDecideDraft: chapterStructureCompatible && draftAwaitingUser,
    canUpdateTargetWordCount: authoritativeStateReady && !busy,
    targetWordCountValid,
  };
}

export function isShortStoryInteractionLocked({
  pendingAction,
  commandStatus,
  taskPhase,
}: {
  pendingAction: string | null;
  commandStatus: ShortStoryCommandStatus | null;
  taskPhase: string | null;
}): boolean {
  return pendingAction !== null
    || Boolean(commandStatus && ACTIVE_COMMAND_STATUSES.has(commandStatus))
    || Boolean(taskPhase && ACTIVE_TASK_PHASES.has(taskPhase));
}

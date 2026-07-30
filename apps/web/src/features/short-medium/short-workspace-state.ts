import type { ChapterSaveState } from "@/features/editor/chapter-save-coordinator";

export type ConfirmedVersionAction = "submit" | "adopt" | "restore";

export const candidateAutomaticallyAdopted = false;

export function canRunDocumentAction(saveState: ChapterSaveState): boolean {
  return saveState === "saved";
}

export function canStartSelectionEdit(
  hasSelection: boolean,
  instruction: string,
): boolean {
  return hasSelection && instruction.trim().length > 0;
}

export function versionActionForInspection(input: {
  versionId: string;
  status: "awaiting_user" | "applied";
  baseVersionId: string | null;
  currentVersionId: string | null;
}): ConfirmedVersionAction | null {
  if (input.versionId === input.currentVersionId) return null;
  if (
    input.status === "awaiting_user"
    && input.baseVersionId === input.currentVersionId
  ) {
    return "adopt";
  }
  return "restore";
}

export function requiresConfirmation(action: ConfirmedVersionAction): boolean {
  return action === "submit" || action === "adopt" || action === "restore";
}

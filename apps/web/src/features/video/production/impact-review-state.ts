import type { ImpactDecision } from "./types";

/** 只把本窗口明确编辑的项目覆盖到远端新版，其他项目保留远端决定。 */
export function rebaseImpactDecisions(
  remote: ImpactDecision[],
  local: ImpactDecision[],
  editedItemIds: ReadonlySet<string>,
): ImpactDecision[] {
  const merged = new Map(remote.map((decision) => [decision.itemId, decision]));
  for (const itemId of editedItemIds) {
    const decision = local.find((item) => item.itemId === itemId);
    if (decision) merged.set(itemId, decision);
  }
  return [...merged.values()];
}

export function impactDecisionNotesComplete(decisions: ImpactDecision[]): boolean {
  return decisions.every((decision) => decision.action === "defer" || decision.note.trim().length > 0);
}

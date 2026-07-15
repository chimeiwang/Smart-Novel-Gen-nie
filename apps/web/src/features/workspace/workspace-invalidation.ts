import type { WorkspaceGroup } from "./deferred-workspace";

type WorkspaceInvalidationListener = (groups: WorkspaceGroup[]) => void;

const listeners = new Set<{
  novelId: string;
  listener: WorkspaceInvalidationListener;
}>();

export function dispatchWorkspaceInvalidation(
  novelId: string,
  groups: WorkspaceGroup[],
): void {
  const uniqueGroups = [...new Set(groups)];
  for (const entry of listeners) {
    if (entry.novelId === novelId) entry.listener(uniqueGroups);
  }
}

export function subscribeWorkspaceInvalidation(
  novelId: string,
  listener: WorkspaceInvalidationListener,
): () => void {
  const entry = { novelId, listener };
  listeners.add(entry);
  return () => listeners.delete(entry);
}

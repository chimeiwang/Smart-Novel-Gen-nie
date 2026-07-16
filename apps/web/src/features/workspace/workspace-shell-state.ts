import type { WorkspaceView } from "./workspace-view";

type WorkspaceViewChangeOptions = {
  currentView: WorkspaceView;
  nextView: WorkspaceView;
  flush: () => Promise<void>;
  commit: (view: WorkspaceView) => void;
};

export async function commitWorkspaceViewChange({
  currentView,
  nextView,
  flush,
  commit,
}: WorkspaceViewChangeOptions): Promise<void> {
  if (currentView === nextView) return;
  await flush();
  commit(nextView);
}

export function formatWorkspaceViewSaveError(error: unknown): string {
  const detail = error instanceof Error ? error.message : "保存失败";
  return `章节保存失败，无法切换视图：${detail}`;
}

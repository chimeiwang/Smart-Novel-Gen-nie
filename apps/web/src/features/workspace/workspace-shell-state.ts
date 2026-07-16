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
  if (currentView === "reading") await flush();
  commit(nextView);
}

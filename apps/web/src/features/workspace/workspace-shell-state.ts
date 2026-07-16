import { parseWorkspaceView, type WorkspaceView } from "./workspace-view";

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

export function parseWorkspaceViewFromSearch(search: string): WorkspaceView {
  return parseWorkspaceView(new URLSearchParams(search).get("view"));
}

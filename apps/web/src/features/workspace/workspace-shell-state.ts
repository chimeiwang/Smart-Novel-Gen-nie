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

export function buildWorkspaceViewHref(href: string, view: WorkspaceView): string {
  const url = new URL(href);
  url.searchParams.set("view", view);
  return url.toString();
}

export function formatWorkspaceViewSaveError(error: unknown): string {
  const detail = error instanceof Error ? error.message : "保存失败";
  return `章节保存失败，无法切换视图：${detail}`;
}

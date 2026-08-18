export type WorkspaceView = "studio" | "reading" | "library";

const WORKSPACE_VIEWS: readonly WorkspaceView[] = [
  "studio",
  "reading",
  "library",
];

export function parseWorkspaceView(value: unknown): WorkspaceView {
  return typeof value === "string" && WORKSPACE_VIEWS.includes(value as WorkspaceView)
    ? (value as WorkspaceView)
    : "studio";
}

export function buildWorkspaceChapterHref(input: {
  novelId: string;
  chapterId: string;
  view: WorkspaceView;
}): string {
  const searchParams = new URLSearchParams({
    chapterId: input.chapterId,
    view: input.view,
  });

  return `/workspace/${encodeURIComponent(input.novelId)}?${searchParams.toString()}`;
}

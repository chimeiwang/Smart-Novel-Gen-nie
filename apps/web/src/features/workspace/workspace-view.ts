export type WorkspaceView = "studio" | "reading" | "library" | "video";
export type WorkspaceStoryLengthProfile = "short_medium" | "long_serial";

const WORKSPACE_VIEWS: readonly WorkspaceView[] = [
  "studio",
  "reading",
  "library",
  "video",
];

export function parseWorkspaceView(value: unknown): WorkspaceView {
  return typeof value === "string" && WORKSPACE_VIEWS.includes(value as WorkspaceView)
    ? (value as WorkspaceView)
    : "studio";
}

/**
 * 视频制作永久只对长篇开放。这里统一收口深链和服务端初始视图，避免短篇仅靠隐藏按钮保护边界。
 */
export function resolveWorkspaceViewForProfile(
  view: WorkspaceView,
  profile: WorkspaceStoryLengthProfile | null | undefined,
): WorkspaceView {
  return view === "video" && profile !== "long_serial" ? "studio" : view;
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

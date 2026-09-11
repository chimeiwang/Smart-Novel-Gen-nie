export type WorkspaceView = "studio" | "reading" | "library" | "video";
export type WorkspaceStoryLengthProfile = "short_medium" | "long_serial";
export type EpisodeWorksurface = "script" | "production";
export type EpisodeRouteContext = { projectId: string | null; episodeId: string | null; surface: EpisodeWorksurface };

export function parseEpisodeRouteContext(input: { projectId?: unknown; episodeId?: unknown; surface?: unknown }): EpisodeRouteContext {
  const identifier = (value: unknown) => typeof value === "string" && value.trim() ? value : null;
  return { projectId: identifier(input.projectId), episodeId: identifier(input.episodeId), surface: input.surface === "production" ? "production" : "script" };
}

/** 视频 URL 只记录分集上下文；章节选择不会暗中切换正在制作的集。 */
export function buildWorkspaceEpisodeHref(novelId: string, context: EpisodeRouteContext): string {
  const params = new URLSearchParams({ view: "video", surface: context.surface });
  if (context.projectId) params.set("projectId", context.projectId);
  if (context.episodeId) params.set("episodeId", context.episodeId);
  return `/workspace/${encodeURIComponent(novelId)}?${params.toString()}`;
}

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

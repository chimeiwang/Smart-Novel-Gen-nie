"use client";

import { EpisodeWorkspace, type EpisodeWorkspaceProps } from "./production/episode-workspace";

/** 分集是视频主入口的稳定身份，小说章节仅作为取材来源。 */
export function VideoWorkspace(props: EpisodeWorkspaceProps) {
  return <EpisodeWorkspace {...props} />;
}

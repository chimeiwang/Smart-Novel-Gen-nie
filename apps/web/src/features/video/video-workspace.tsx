"use client";

import { ChapterAdaptationWorkspace } from "./adaptation/chapter-adaptation-workspace";
import type { VideoWorkspaceProps } from "./video-workspace-types";

/** 长篇视频入口以章节影视化工作台为主，不再暴露旧五任务模型流程。 */
export function VideoWorkspace(props: VideoWorkspaceProps) {
  return <ChapterAdaptationWorkspace {...props} />;
}

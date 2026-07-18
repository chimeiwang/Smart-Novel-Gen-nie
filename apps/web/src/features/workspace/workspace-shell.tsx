"use client";

import { LongSerialWorkspace } from "./long-serial-workspace";
import type { LongSerialWorkspaceProps } from "./long-serial-workspace";
import { ShortStoryWorkspace } from "./short-story/short-story-workspace";

export function WorkspaceShell(props: LongSerialWorkspaceProps) {
  if (props.bootstrap.storyLengthProfile === "short_medium") {
    return <ShortStoryWorkspace bootstrap={props.bootstrap} />;
  }

  return <LongSerialWorkspace {...props} />;
}

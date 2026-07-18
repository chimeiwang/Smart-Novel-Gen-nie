import type { components } from "@inkforge/api-client";

export type ShortStoryPane = "outline" | "draft" | "formal";
type ArtifactStatus = components["schemas"]["ShortStoryArtifactResponse"]["status"];

export function shouldLoadOutlineRevisions(
  pane: ShortStoryPane,
  hasOutline: boolean,
): boolean {
  return pane === "outline" && hasOutline;
}

export function canRestoreOutlineRevision({
  pane,
  status,
}: {
  pane: ShortStoryPane;
  status: ArtifactStatus | null;
}): boolean {
  return pane === "outline" && status === "awaiting_user";
}

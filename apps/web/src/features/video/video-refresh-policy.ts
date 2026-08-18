type RefreshableVideoProject = {
  scenes: ReadonlyArray<{
    id: string;
    status: string;
    updatedAt: string;
  }>;
};

export const VIDEO_REFRESH_FAST_MS = 2_000;
export const VIDEO_REFRESH_MAX_MS = 8_000;

export function videoProjectRefreshSignature(project: RefreshableVideoProject): string {
  return project.scenes
    .map((scene) => `${scene.id}:${scene.status}:${scene.updatedAt}`)
    .join("|");
}

export function nextVideoRefreshDelay(unchangedPolls: number): number {
  if (unchangedPolls <= 0) return VIDEO_REFRESH_FAST_MS;
  if (unchangedPolls === 1) return 3_000;
  if (unchangedPolls === 2) return 5_000;
  return VIDEO_REFRESH_MAX_MS;
}

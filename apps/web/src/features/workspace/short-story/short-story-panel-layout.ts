export const SHORT_STORY_PANEL_IDS = {
  workflow: "short-story-workflow",
  canvas: "short-story-canvas",
  chat: "short-story-chat",
} as const;

export const SHORT_STORY_PANEL_CONSTRAINTS = {
  workflow: { defaultSize: 280, minSize: 220, maxSize: 360 },
  canvas: { minSize: 640 },
  chat: { defaultSize: 400, minSize: 320, maxSize: 520 },
} as const;

type ShortStoryPanelId = (typeof SHORT_STORY_PANEL_IDS)[keyof typeof SHORT_STORY_PANEL_IDS];

export type ShortStoryPanelLayout = Record<ShortStoryPanelId, number>;

export type ShortStoryPanelStorage = Pick<Storage, "getItem" | "setItem">;

export function buildShortStoryPanelStorageKey(novelId: string): string {
  return `inkforge:short-story-panel-layout:v1:${novelId}`;
}

function isShortStoryPanelLayout(value: unknown): value is ShortStoryPanelLayout {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return Object.values(SHORT_STORY_PANEL_IDS).every((panelId) => (
    typeof record[panelId] === "number"
    && Number.isFinite(record[panelId])
    && record[panelId] > 0
  ));
}

export function readShortStoryPanelLayout(
  storage: ShortStoryPanelStorage | null,
  novelId: string,
): ShortStoryPanelLayout | null {
  if (!storage) return null;
  try {
    const serialized = storage.getItem(buildShortStoryPanelStorageKey(novelId));
    if (!serialized) return null;
    const parsed: unknown = JSON.parse(serialized);
    return isShortStoryPanelLayout(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeShortStoryPanelLayout(
  storage: ShortStoryPanelStorage | null,
  novelId: string,
  layout: unknown,
): void {
  if (!storage || !isShortStoryPanelLayout(layout)) return;
  try {
    storage.setItem(buildShortStoryPanelStorageKey(novelId), JSON.stringify(layout));
  } catch {
    // 浏览器可能拒绝访问本地存储，分栏仍应继续工作。
  }
}

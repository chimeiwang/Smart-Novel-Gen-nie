import type { components } from "@inkforge/api-client";

type StableOutlineItem = { id: string } | { key: string };
type ShortStoryOutlineSection = components["schemas"]["ShortStoryOutlineSection"];
type ShortStoryOutlineSectionEdit = components["schemas"]["ShortStoryOutlineSectionEdit"];

export type EditableOutlineSection = {
  key: string;
  persistedId: string | null;
  title: string;
  events: string;
};

function getOutlineItemKey(item: StableOutlineItem): string {
  return "key" in item ? item.key : item.id;
}

export function moveOutlineItem<T extends StableOutlineItem>(
  items: readonly T[],
  id: string,
  direction: "up" | "down",
): T[] {
  const currentIndex = items.findIndex((item) => getOutlineItemKey(item) === id);
  if (currentIndex < 0) return [...items];

  const targetIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;
  if (targetIndex < 0 || targetIndex >= items.length) return [...items];

  const next = [...items];
  [next[currentIndex], next[targetIndex]] = [next[targetIndex], next[currentIndex]];
  return next;
}

export function appendOutlineItem<T extends StableOutlineItem>(
  items: readonly T[],
  createItem: () => T,
): T[] {
  const item = createItem();
  const itemKey = getOutlineItemKey(item);
  if (items.some((current) => getOutlineItemKey(current) === itemKey)) {
    throw new Error("分节稳定 ID 不能重复");
  }
  return [...items, item];
}

export function updateOutlineItem<T extends StableOutlineItem>(
  items: readonly T[],
  id: string,
  update: (item: T) => T,
): T[] {
  return items.map((item) => (getOutlineItemKey(item) === id ? update(item) : item));
}

export function removeOutlineItem<T extends StableOutlineItem>(
  items: readonly T[],
  id: string,
): T[] {
  if (items.length <= 1 || !items.some((item) => getOutlineItemKey(item) === id)) {
    return [...items];
  }
  return items.filter((item) => getOutlineItemKey(item) !== id);
}

export function createEditableOutlineSections(
  sections: readonly ShortStoryOutlineSection[],
): EditableOutlineSection[] {
  return sections.map((section) => ({
    key: section.id,
    persistedId: section.id,
    title: section.title,
    events: section.events,
  }));
}

export function serializeOutlineSections(
  sections: readonly EditableOutlineSection[],
): ShortStoryOutlineSectionEdit[] {
  return sections.map((section) => ({
    ...(section.persistedId ? { id: section.persistedId } : {}),
    title: section.title,
    events: section.events,
  }));
}

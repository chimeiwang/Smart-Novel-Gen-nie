import type { components } from "@inkforge/api-client";

export type LoreListKind = "characters" | "items" | "locations" | "factions" | "glossaries";

export type LoreListTag = {
  label: string;
  tone: "status" | "warning" | "neutral";
};

export type LoreListItemView = {
  id: string;
  kindLabel: "角色" | "物品" | "地点" | "势力" | "术语";
  name: string;
  initial: string;
  secondary: string | null;
  tags: LoreListTag[];
  summary: string | null;
  ariaLabel: string;
};

export type LoreListData = {
  characters: components["schemas"]["CharacterDto"][];
  items: components["schemas"]["ItemDto"][];
  locations: components["schemas"]["LocationDto"][];
  factions: components["schemas"]["FactionDto"][];
  glossaries: components["schemas"]["GlossaryDto"][];
};

const STATUS_LABELS: Record<components["schemas"]["CharacterStatus"], string> = {
  active: "活跃",
  missing: "失踪",
  dead: "死亡",
  imprisoned: "被囚禁",
  unknown: "未知",
};

function textOrNull(value: string | null | undefined): string | null {
  const normalized = value?.trim();
  return normalized ? normalized : null;
}

function createBaseItem(
  id: string,
  kindLabel: LoreListItemView["kindLabel"],
  name: string,
): Pick<LoreListItemView, "id" | "kindLabel" | "name" | "initial" | "ariaLabel"> {
  return {
    id,
    kindLabel,
    name,
    initial: Array.from(name.trim())[0] ?? kindLabel[0],
    ariaLabel: `编辑${kindLabel}：${name}`,
  };
}

export function buildLoreListItems(kind: LoreListKind, data: LoreListData): LoreListItemView[] {
  const locationNames = new Map(data.locations.map((location) => [location.id, location.name]));

  if (kind === "characters") {
    return data.characters.map((character) => ({
      ...createBaseItem(character.id, "角色", character.name),
      secondary: textOrNull(character.identity),
      tags: [
        {
          label: STATUS_LABELS[character.currentStatus],
          tone: character.currentStatus === "active" ? "status" as const : "warning" as const,
        },
        ...(textOrNull(character.faction?.name)
          ? [{ label: character.faction!.name, tone: "neutral" as const }]
          : []),
        ...(textOrNull(character.powerLevel)
          ? [{ label: character.powerLevel!.trim(), tone: "neutral" as const }]
          : []),
      ],
      summary: textOrNull(character.personality) ?? textOrNull(character.statusNote),
    }));
  }

  if (kind === "items") {
    return data.items.map((item) => ({
      ...createBaseItem(item.id, "物品", item.name),
      secondary: textOrNull(item.type),
      tags: [
        ...(textOrNull(item.rarity)
          ? [{ label: item.rarity!.trim(), tone: "neutral" as const }]
          : []),
        ...(textOrNull(item.owner?.name)
          ? [{ label: `持有：${item.owner!.name.trim()}`, tone: "neutral" as const }]
          : []),
      ],
      summary: textOrNull(item.effect) ?? textOrNull(item.description),
    }));
  }

  if (kind === "locations") {
    return data.locations.map((location) => {
      const parentName = location.parentId ? locationNames.get(location.parentId) : null;
      return {
        ...createBaseItem(location.id, "地点", location.name),
        secondary: textOrNull(location.type),
        tags: [
          ...(textOrNull(parentName)
            ? [{ label: `上级：${parentName!.trim()}`, tone: "neutral" as const }]
            : []),
          ...(textOrNull(location.climate)
            ? [{ label: location.climate!.trim(), tone: "neutral" as const }]
            : []),
        ],
        summary: textOrNull(location.description),
      };
    });
  }

  if (kind === "factions") {
    return data.factions.map((faction) => {
      const baseName = faction.baseId ? locationNames.get(faction.baseId) : null;
      return {
        ...createBaseItem(faction.id, "势力", faction.name),
        secondary: textOrNull(faction.type),
        tags: textOrNull(baseName)
          ? [{ label: `总部：${baseName!.trim()}`, tone: "neutral" as const }]
          : [],
        summary: textOrNull(faction.description),
      };
    });
  }

  return data.glossaries.map((glossary) => ({
    ...createBaseItem(glossary.id, "术语", glossary.term),
    secondary: textOrNull(glossary.category),
    tags: [],
    summary: textOrNull(glossary.definition),
  }));
}

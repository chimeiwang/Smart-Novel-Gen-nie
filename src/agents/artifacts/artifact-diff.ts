/**
 * Artifact 差异构建。
 *
 * @module agents/artifacts/artifact-diff
 * @description 将 AgentUpdates 转为前端可展示的字段级 diff。
 */

import type { AgentUpdates } from "@/shared/contracts/agent-updates";
import type { NovelData } from "@/agents/graph/state";

export type UpdateDiffField = {
  field: string;
  label: string;
  oldValue?: string;
  newValue?: string;
};

export type UpdateDiffItem = {
  section: string;
  action: string;
  name: string;
  fields: UpdateDiffField[];
};

export const FIELD_LABELS: Record<string, string> = {
  name: "名称",
  title: "标题",
  aliases: "别名",
  gender: "性别",
  age: "年龄",
  identity: "身份",
  personality: "性格",
  appearance: "外貌",
  background: "背景",
  coreDesire: "核心欲望",
  behaviorBoundaries: "行为边界",
  speechStyle: "说话习惯",
  relationshipPrinciples: "关系原则",
  shortTermGoal: "短期目标",
  powerLevel: "实力层级",
  combatAbility: "战斗能力",
  specialSkills: "特殊能力",
  currentStatus: "当前状态",
  statusNote: "状态说明",
  characterName: "角色",
  chapterTitle: "章节",
  order: "顺序",
  content: "内容",
  description: "描述",
  type: "类型",
  climate: "气候",
  culture: "文化",
  rarity: "稀有度",
  effect: "效果",
  origin: "来源",
  term: "术语",
  definition: "定义",
  category: "分类",
  status: "状态",
  kind: "节点类型",
  clientKey: "临时节点键",
  parentKey: "临时父节点键",
  estimatedWordCount: "预计字数",
  actualWordCount: "实际字数",
  plantedAt: "埋设位置",
  plantedContent: "埋设内容",
  expectedPayoff: "预期回收",
  payoffAt: "回收位置",
  payoffNote: "回收说明",
  worldSetting: "世界设定",
  storyBackground: "故事背景",
};

export const SECTION_LABELS: Record<string, string> = {
  characters: "角色",
  characterExperiences: "角色经历",
  locations: "地点",
  items: "物品",
  factions: "势力",
  glossaries: "术语",
  foreshadowing: "伏笔",
  outline: "大纲状态",
  outlineContent: "总纲",
  outlineAdjustments: "大纲节点",
  references: "参考资料",
  worldSetting: "世界设定",
  storyBackground: "故事背景",
};

const DIFF_FIELDS: Record<string, string[]> = {
  characters: [
    "name", "aliases", "gender", "age", "identity", "personality", "appearance",
    "background", "coreDesire", "behaviorBoundaries", "speechStyle",
    "relationshipPrinciples", "shortTermGoal", "powerLevel", "combatAbility",
    "specialSkills", "currentStatus", "statusNote",
  ],
  characterExperiences: ["characterName", "chapterTitle", "content", "order"],
  locations: ["name", "aliases", "type", "parentId", "description", "climate", "culture"],
  items: ["name", "aliases", "type", "rarity", "effect", "origin", "description", "ownerId"],
  factions: ["name", "aliases", "type", "baseId", "description"],
  glossaries: ["term", "definition", "category"],
  foreshadowing: ["name", "plantedAt", "plantedContent", "expectedPayoff", "payoffAt", "payoffNote"],
  outline: ["status", "actualWordCount"],
  outlineAdjustments: ["title", "content", "kind", "parentId", "clientKey", "parentKey", "status", "estimatedWordCount", "actualWordCount"],
  references: ["title", "type", "content"],
};

function stringifyDiffValue(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function valueChanged(oldValue: unknown, newValue: unknown): boolean {
  return (stringifyDiffValue(oldValue) ?? "") !== (stringifyDiffValue(newValue) ?? "");
}

function getEntityName(section: string, item: Record<string, unknown>): string {
  return String(
    item.name ||
    item.characterName ||
    item.term ||
    item.title ||
    item.nodeTitle ||
    item.nodeId ||
    item.id ||
    SECTION_LABELS[section] ||
    "未命名"
  );
}

function findExistingEntity(
  section: string,
  item: Record<string, unknown>,
  novelData?: NovelData
): Record<string, unknown> | undefined {
  if (!novelData) return undefined;

  const id = String(item.id || item.characterId || item.locationId || item.itemId || item.factionId || item.glossaryId || item.referenceId || item.nodeId || "");
  const name = String(item.name || item.characterName || item.term || item.title || item.nodeTitle || "");

  if (section === "characters") {
    return novelData.characters.find((c) => c.id === id || c.name === name) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "characterExperiences") {
    const experiences = novelData.characters.flatMap((character) =>
      (character.experiences ?? []).map((experience) => ({
        ...experience,
        characterName: character.name,
      }))
    );
    return experiences.find((experience) => {
      if (id && experience.id === id) return true;
      const characterId = String(item.characterId || "");
      return Boolean(characterId && experience.characterId === characterId && experience.content === item.content);
    }) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "locations") {
    return novelData.locations.find((l) => l.id === id || l.name === name) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "items") {
    return novelData.items.find((i) => i.id === id || i.name === name) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "factions") {
    return novelData.factions.find((f) => f.id === id || f.name === name) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "glossaries") {
    return novelData.glossaries.find((g) => g.id === id || g.term === name) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "foreshadowing") {
    return novelData.foreshadowings.find((f) => f.id === id || f.name === name) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "outline" || section === "outlineAdjustments") {
    return novelData.outlineNodes.find((n) => n.id === id || n.title.includes(name) || name.includes(n.title)) as unknown as Record<string, unknown> | undefined;
  }
  if (section === "references") {
    return novelData.references.find((r) => r.id === id || r.title === name) as unknown as Record<string, unknown> | undefined;
  }

  return undefined;
}

function buildDiffFields(
  section: string,
  item: Record<string, unknown>,
  existing?: Record<string, unknown>
): UpdateDiffField[] {
  if (Array.isArray(item.fieldChanges)) {
    const fields = item.fieldChanges
      .filter((change): change is Record<string, unknown> => Boolean(change) && typeof change === "object")
      .map((change) => {
        const field = String(change.field || "");
        return {
          field,
          label: FIELD_LABELS[field] ?? field,
          oldValue: stringifyDiffValue(change.oldValue ?? existing?.[field]),
          newValue: stringifyDiffValue(change.newValue),
        };
      })
      .filter((field) => field.field);
    if (fields.length > 0) return fields;
  }

  const fields = DIFF_FIELDS[section] ?? [];
  return fields
    .filter((field) => Object.prototype.hasOwnProperty.call(item, field))
    .filter((field) => item.action !== "update" || valueChanged(existing?.[field], item[field]))
    .map((field) => ({
      field,
      label: FIELD_LABELS[field] ?? field,
      oldValue: stringifyDiffValue(existing?.[field]),
      newValue: stringifyDiffValue(item[field]),
    }));
}

export function buildUpdateDiffs(updates: AgentUpdates, novelData?: NovelData): UpdateDiffItem[] {
  const diffs: UpdateDiffItem[] = [];
  const arraySections = [
    "characters", "characterExperiences", "locations", "items", "factions",
    "glossaries", "foreshadowing", "outline", "outlineAdjustments", "references",
  ] as const;

  for (const section of arraySections) {
    const items = updates[section] as Record<string, unknown>[] | undefined;
    for (const item of items ?? []) {
      const action = String(item.action || "update");
      const existing = action === "create" ? undefined : findExistingEntity(section, item, novelData);
      diffs.push({
        section: SECTION_LABELS[section] ?? section,
        action,
        name: getEntityName(section, item),
        fields: buildDiffFields(section, item, existing),
      });
    }
  }

  if (updates.worldSetting) {
    diffs.push({
      section: SECTION_LABELS.worldSetting,
      action: "update",
      name: SECTION_LABELS.worldSetting,
      fields: [{
        field: "worldSetting",
        label: FIELD_LABELS.worldSetting,
        oldValue: novelData?.worldSetting,
        newValue: updates.worldSetting,
      }],
    });
  }

  if (updates.storyBackground) {
    diffs.push({
      section: SECTION_LABELS.storyBackground,
      action: "update",
      name: SECTION_LABELS.storyBackground,
      fields: [{
        field: "storyBackground",
        label: FIELD_LABELS.storyBackground,
        oldValue: novelData?.storyBackground,
        newValue: updates.storyBackground,
      }],
    });
  }

  if (updates.outlineContent) {
    diffs.push({
      section: SECTION_LABELS.outlineContent,
      action: "update",
      name: SECTION_LABELS.outlineContent,
      fields: [{
        field: "outlineContent",
        label: "总纲",
        oldValue: novelData?.outlineSummary,
        newValue: updates.outlineContent,
      }],
    });
  }

  return diffs;
}

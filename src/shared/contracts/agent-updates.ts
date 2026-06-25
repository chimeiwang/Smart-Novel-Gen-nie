/**
 * Agent Updates 契约（Phase 2：唯一字段来源）
 *
 * @module shared/contracts/agent-updates
 * @description 所有 AgentUpdates section 的 Zod schema、TS 类型、sanitize、hasAgentUpdates。
 *  此为唯一数据源。sanitizer 不会丢弃 schema 允许的任何 section。
 *
 * @phase Phase 2 — AgentUpdates 契约统一
 */

import { z } from "zod";

// ============================================
// 基础类型
// ============================================

export const FieldChangeSchema = z.object({
  field: z.string(),
  operation: z.enum(["add", "remove", "update"]),
  oldValue: z.string().optional(),
  newValue: z.string().optional(),
});
export type FieldChange = z.infer<typeof FieldChangeSchema>;

const StatusEnum = z.enum(["active", "missing", "dead", "imprisoned", "unknown"]);
const OutlineStatusEnum = z.enum(["planned", "in_progress", "completed", "skipped"]);
export const OutlineNodeKindSchema = z.enum(["stage", "plot_unit", "chapter_group"]);
export type OutlineNodeKind = z.infer<typeof OutlineNodeKindSchema>;

// ============================================
// Section Schemas
// ============================================

export const CharacterAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().optional(),
  characterId: z.string().optional(),
  name: z.string().min(1),
  aliases: z.string().optional(),
  gender: z.string().optional(),
  age: z.string().optional(),
  identity: z.string().optional(),
  personality: z.string().optional(),
  appearance: z.string().optional(),
  background: z.string().optional(),
  coreDesire: z.string().optional(),
  behaviorBoundaries: z.string().optional(),
  speechStyle: z.string().optional(),
  relationshipPrinciples: z.string().optional(),
  shortTermGoal: z.string().optional(),
  factionId: z.string().optional(),
  powerLevel: z.string().optional(),
  combatAbility: z.string().optional(),
  specialSkills: z.string().optional(),
  currentStatus: StatusEnum.optional(),
  statusNote: z.string().optional(),
  fieldChanges: z.array(FieldChangeSchema).optional(),
});

export const LocationAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().optional(),
  locationId: z.string().optional(),
  name: z.string().min(1),
  aliases: z.string().optional(),
  type: z.string().optional(),
  parentId: z.string().optional(),
  description: z.string().optional(),
  climate: z.string().optional(),
  culture: z.string().optional(),
  fieldChanges: z.array(FieldChangeSchema).optional(),
});

export const ItemAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().optional(),
  itemId: z.string().optional(),
  name: z.string().min(1),
  aliases: z.string().optional(),
  type: z.string().optional(),
  rarity: z.string().optional(),
  effect: z.string().optional(),
  origin: z.string().optional(),
  description: z.string().optional(),
  ownerId: z.string().optional(),
  fieldChanges: z.array(FieldChangeSchema).optional(),
});

export const FactionAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().optional(),
  factionId: z.string().optional(),
  name: z.string().min(1),
  aliases: z.string().optional(),
  type: z.string().optional(),
  baseId: z.string().optional(),
  description: z.string().optional(),
  fieldChanges: z.array(FieldChangeSchema).optional(),
});

export const GlossaryAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().optional(),
  glossaryId: z.string().optional(),
  term: z.string().min(1),
  definition: z.string(),
  category: z.string().optional(),
  fieldChanges: z.array(FieldChangeSchema).optional(),
});

export const CharacterExperienceAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  id: z.string().optional(),
  characterId: z.string().optional(),
  characterName: z.string().optional(),
  chapterId: z.string().optional(),
  chapterTitle: z.string().optional(),
  content: z.string().min(1),
  order: z.number().optional(),
});

export const OutlineUpdateSchema = z.object({
  nodeId: z.string().min(1),
  status: OutlineStatusEnum,
  actualWordCount: z.number().optional(),
});

function hasText(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

const OutlineAdjustmentBaseSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  nodeId: z.string().optional(),
  nodeTitle: z.string().optional(),
  clientKey: z.string().optional(),
  parentKey: z.string().optional(),
  title: z.string().optional(),
  content: z.string().optional(),
  kind: OutlineNodeKindSchema.optional(),
  parentId: z.string().optional(),
  status: OutlineStatusEnum.optional(),
  estimatedWordCount: z.number().optional(),
  actualWordCount: z.number().optional(),
});

export const OutlineAdjustmentSchema = OutlineAdjustmentBaseSchema;

export const StrictOutlineAdjustmentSchema = OutlineAdjustmentBaseSchema.superRefine((adjustment, ctx) => {
  const hasParentId = hasText(adjustment.parentId);
  const hasParentKey = hasText(adjustment.parentKey);

  if (hasParentId && hasParentKey) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["parentKey"],
      message: "不能同时提供 parentId 和 parentKey；已有父节点用 parentId，同批新父节点用 parentKey",
    });
  }

  if (adjustment.action === "create") {
    if (!hasText(adjustment.title) && !hasText(adjustment.nodeTitle)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["title"],
        message: "创建大纲节点必须提供 title 或 nodeTitle",
      });
    }

    if (!adjustment.kind) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["kind"],
        message: "创建大纲节点必须提供 kind：stage、plot_unit 或 chapter_group",
      });
      return;
    }

    if (adjustment.kind === "stage") {
      if (hasParentId || hasParentKey) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: hasParentKey ? ["parentKey"] : ["parentId"],
          message: "stage（阶段/卷）必须是顶层节点，不能提供 parentId 或 parentKey",
        });
      }
      return;
    }

    if (!hasParentId && !hasParentKey) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["parentId"],
        message: adjustment.kind === "plot_unit"
          ? "plot_unit（剧情单元）必须挂在 stage 下，请提供 parentId 或 parentKey"
          : "chapter_group（章节组）必须挂在 plot_unit 下，请提供 parentId 或 parentKey",
      });
    }

    return;
  }

  if (hasParentKey) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["parentKey"],
      message: "parentKey 只用于同批创建节点；更新或删除已有节点请使用 parentId/nodeId/nodeTitle/title",
    });
  }

  if (adjustment.action === "update" || adjustment.action === "delete") {
    if (!hasText(adjustment.nodeId) && !hasText(adjustment.nodeTitle) && !hasText(adjustment.title)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["nodeId"],
        message: "更新或删除大纲节点必须提供 nodeId、nodeTitle 或 title 之一",
      });
    }
  }
});

export const StrictOutlineAdjustmentsSchema = z.array(StrictOutlineAdjustmentSchema).superRefine((adjustments, ctx) => {
  const createClientKeys = new Map<string, number>();
  const createItemsByClientKey = new Map<string, z.infer<typeof OutlineAdjustmentBaseSchema>>();
  const hasParentKeyReference = adjustments.some(
    (item) => item.action === "create" && hasText(item.parentKey)
  );

  for (const [index, item] of adjustments.entries()) {
    if (item.action !== "create" || !hasText(item.clientKey)) continue;
    const key = item.clientKey.trim();
    const existingIndex = createClientKeys.get(key);
    if (existingIndex !== undefined) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [index, "clientKey"],
        message: `clientKey "${key}" 重复；同批新建节点必须使用唯一 clientKey`,
      });
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [existingIndex, "clientKey"],
        message: `clientKey "${key}" 重复；同批新建节点必须使用唯一 clientKey`,
      });
    } else {
      createClientKeys.set(key, index);
      createItemsByClientKey.set(key, item);
    }
  }

  for (const [index, item] of adjustments.entries()) {
    if (item.action !== "create") continue;

    if (hasParentKeyReference && !hasText(item.clientKey)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [index, "clientKey"],
        message: "同批创建父子节点时，每个新节点都必须提供稳定 clientKey",
      });
    }

    if (!hasText(item.parentKey)) continue;
    const parentKey = item.parentKey.trim();
    if (hasText(item.clientKey) && item.clientKey.trim() === parentKey) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [index, "parentKey"],
        message: "parentKey 不能指向当前节点自己的 clientKey",
      });
    }
    const parentItem = createItemsByClientKey.get(parentKey);
    if (!parentItem) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [index, "parentKey"],
        message: `找不到 parentKey "${parentKey}" 对应的同批新建父节点；已有父节点请使用 parentId`,
      });
      continue;
    }

    const expectedParentKind = item.kind === "plot_unit"
      ? "stage"
      : item.kind === "chapter_group"
        ? "plot_unit"
        : null;
    if (expectedParentKind && parentItem.kind !== expectedParentKind) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: [index, "parentKey"],
        message: `${item.kind} 的 parentKey 必须指向同批 ${expectedParentKind} 节点`,
      });
    }
  }
});

export const ForeshadowingUpdateSchema = z.object({
  action: z.enum(["create", "update", "payoff", "abandon"]),
  id: z.string().optional(),
  name: z.string().min(1),
  plantedAt: z.string().optional(),
  plantedContent: z.string().optional(),
  expectedPayoff: z.string().optional(),
  payoffAt: z.string().optional(),
  payoffNote: z.string().optional(),
});

export const ReferenceAdjustmentSchema = z.object({
  action: z.enum(["create", "update", "delete"]),
  referenceId: z.string().optional(),
  id: z.string().optional(),
  title: z.string().min(1),
  type: z.string().optional(),
  content: z.string().optional(),
});

// ============================================
// 聚合 Schema
// ============================================

export const AgentUpdatesSchema = z.object({
  characters: z.array(CharacterAdjustmentSchema).optional(),
  locations: z.array(LocationAdjustmentSchema).optional(),
  items: z.array(ItemAdjustmentSchema).optional(),
  factions: z.array(FactionAdjustmentSchema).optional(),
  glossaries: z.array(GlossaryAdjustmentSchema).optional(),
  characterExperiences: z.array(CharacterExperienceAdjustmentSchema).optional(),
  outline: z.array(OutlineUpdateSchema).optional(),
  outlineContent: z.string().optional(),
  outlineAdjustments: z.array(OutlineAdjustmentSchema).optional(),
  foreshadowing: z.array(ForeshadowingUpdateSchema).optional(),
  references: z.array(ReferenceAdjustmentSchema).optional(),
  worldSetting: z.string().optional(),
  storyBackground: z.string().optional(),
});

export type AgentUpdates = z.infer<typeof AgentUpdatesSchema>;

export const AgentUpdatesProposalSchema = AgentUpdatesSchema.extend({
  outlineAdjustments: StrictOutlineAdjustmentsSchema.optional(),
});

/** AgentUpdateSection — sanitize/AgentDefinition 中使用的 section 名 */
export const AgentUpdateSectionSchema = z.enum([
  "characters",
  "locations",
  "items",
  "factions",
  "glossaries",
  "characterExperiences",
  "outline",
  "outlineAdjustments",
  "outlineContent",
  "foreshadowing",
  "references",
  "worldSetting",
  "storyBackground",
]);
export type AgentUpdateSection = z.infer<typeof AgentUpdateSectionSchema>;

export const ALL_UPDATE_SECTIONS: AgentUpdateSection[] = [...AgentUpdateSectionSchema.options];

export const AgentUpdateSelectionRefSchema = z.object({
  section: AgentUpdateSectionSchema,
  index: z.number().int().min(0).optional(),
});
export type AgentUpdateSelectionRef = z.infer<typeof AgentUpdateSelectionRefSchema>;

// ============================================
// 字段白名单（用于 sanitize）
// ============================================

const CHARACTER_FIELDS = [
  "name", "aliases", "gender", "age", "appearance", "personality",
  "identity", "background", "coreDesire", "behaviorBoundaries",
  "speechStyle", "relationshipPrinciples", "shortTermGoal", "factionId",
  "powerLevel", "combatAbility", "specialSkills", "currentStatus", "statusNote",
] as const;

const LOCATION_FIELDS = [
  "name", "aliases", "type", "parentId", "climate", "culture", "description",
] as const;

const ITEM_FIELDS = [
  "name", "aliases", "type", "rarity", "effect", "origin", "description", "ownerId",
] as const;

const FACTION_FIELDS = [
  "name", "aliases", "type", "baseId", "description",
] as const;

const GLOSSARY_FIELDS = ["term", "definition", "category"] as const;

const CHARACTER_EXPERIENCE_FIELDS = [
  "characterId", "characterName", "chapterId", "chapterTitle", "content", "order",
] as const;

const OUTLINE_FIELDS = [
  "title", "content", "kind", "parentId", "clientKey", "parentKey", "status", "estimatedWordCount", "actualWordCount",
] as const;

const FORESHADOWING_FIELDS = [
  "name", "plantedAt", "plantedContent", "expectedPayoff", "payoffAt", "payoffNote",
] as const;

const REFERENCE_FIELDS = ["title", "type", "content"] as const;

/** section → 合法字段白名单 */
const FIELD_MAP: Record<string, readonly string[]> = {
  characters: CHARACTER_FIELDS,
  locations: LOCATION_FIELDS,
  items: ITEM_FIELDS,
  factions: FACTION_FIELDS,
  glossaries: GLOSSARY_FIELDS,
  characterExperiences: CHARACTER_EXPERIENCE_FIELDS,
  outline: [],
  outlineAdjustments: OUTLINE_FIELDS,
  foreshadowing: FORESHADOWING_FIELDS,
  references: REFERENCE_FIELDS,
};

// ============================================
// sanitizeAgentUpdates（完整版：不丢弃任何 section）
// ============================================

/**
 * 过滤 Agent 输出的非法字段和值。
 *
 * Phase 2 修复：保留所有 12 个 section。
 * 旧版只处理 6 个，outline/outlineAdjustments/foreshadowing/references 被静默丢弃。
 */
export function sanitizeAgentUpdates(
  raw: unknown,
  allowedSections?: AgentUpdateSection[]
): AgentUpdates | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const input = raw as Record<string, unknown>;
  const updates: Record<string, unknown> = {};
  const allowed = allowedSections ? new Set(allowedSections) : null;

  // 数组型 sections（有白名单过滤）
  const arraySections: Array<{ key: string; idFields: string[] }> = [
    { key: "characters", idFields: ["characterId"] },
    { key: "locations", idFields: ["locationId"] },
    { key: "items", idFields: ["itemId"] },
    { key: "factions", idFields: ["factionId"] },
    { key: "glossaries", idFields: ["glossaryId"] },
    { key: "characterExperiences", idFields: [] },
    { key: "outlineAdjustments", idFields: ["nodeId"] },
    { key: "foreshadowing", idFields: [] },
    { key: "references", idFields: ["referenceId"] },
  ];

  for (const { key, idFields } of arraySections) {
    const section = sanitizeArraySection(input[key], key, idFields);
    if (section) updates[key] = section;
  }

  // outline（特殊 section：不是调整而是状态更新）
  if (Array.isArray(input.outline)) {
    updates.outline = sanitizeOutlineSection(input.outline);
  }

  if (typeof input.outlineContent === "string" && input.outlineContent.trim()) {
    if (!allowed || allowed.has("outlineContent")) updates.outlineContent = input.outlineContent.trim();
  }

  // 字符串型 sections
  if (typeof input.worldSetting === "string" && input.worldSetting.trim()) {
    if (!allowed || allowed.has("worldSetting")) updates.worldSetting = input.worldSetting.trim();
  }
  if (typeof input.storyBackground === "string" && input.storyBackground.trim()) {
    if (!allowed || allowed.has("storyBackground")) updates.storyBackground = input.storyBackground.trim();
  }

  // Phase 2：如果指定了 allowedSections，删除不允许的 section
  if (allowed) {
    for (const key of Object.keys(updates)) {
      if (!allowed.has(key as AgentUpdateSection)) {
        delete updates[key];
      }
    }
  }

  return hasAgentUpdates(updates as AgentUpdates) ? (updates as AgentUpdates) : undefined;
}

// ============================================
// hasAgentUpdates
// ============================================

export function hasAgentUpdates(updates: AgentUpdates | null | undefined): updates is AgentUpdates {
  if (!updates || typeof updates !== "object") return false;
  const u = updates as Record<string, unknown>;
  return Boolean(
    (u.characters as unknown[])?.length ||
    (u.locations as unknown[])?.length ||
    (u.items as unknown[])?.length ||
    (u.factions as unknown[])?.length ||
    (u.glossaries as unknown[])?.length ||
    (u.characterExperiences as unknown[])?.length ||
    (u.outline as unknown[])?.length ||
    u.outlineContent ||
    (u.outlineAdjustments as unknown[])?.length ||
    (u.foreshadowing as unknown[])?.length ||
    (u.references as unknown[])?.length ||
    u.worldSetting ||
    u.storyBackground
  );
}

// ============================================
// 内部 sanitize 函数
// ============================================

function sanitizeArraySection(
  input: unknown,
  sectionKey: string,
  idFieldNames: string[]
): Record<string, unknown>[] | undefined {
  if (!Array.isArray(input)) return undefined;

  const allowedFields = new Set<string>([
    "action", "id", ...idFieldNames,
    ...(FIELD_MAP[sectionKey] || []),
    "fieldChanges",
  ]);

  if (sectionKey === "glossaries") {
    allowedFields.add("glossaryId");
  }

  const items = input
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => {
      const next: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(item)) {
        if (!allowedFields.has(key) || value === undefined) continue;

        if (key === "action") {
          if (typeof value === "string" && ["create", "update", "delete", "payoff", "abandon"].includes(value)) {
            next.action = value;
          }
          continue;
        }
        if (key === "currentStatus") {
          if (typeof value === "string" && ["active", "missing", "dead", "imprisoned", "unknown"].includes(value)) {
            next.currentStatus = value;
          }
          continue;
        }
        if (key === "status") {
          if (typeof value === "string" && ["planned", "in_progress", "completed", "skipped"].includes(value)) {
            next.status = value;
          }
          continue;
        }
        if (key === "fieldChanges") {
          const changes = sanitizeFieldChanges(value);
          if (changes.length > 0) next.fieldChanges = changes;
          continue;
        }
        if (key === "order" && typeof value === "number") {
          next.order = value;
          continue;
        }
        if (typeof value === "string") next[key] = value;
        else if (typeof value === "number") next[key] = value;
      }
      return next;
    })
    .filter((item) => Object.keys(item).length > 0);

  return items.length > 0 ? items : undefined;
}

function sanitizeOutlineSection(
  input: unknown
): Record<string, unknown>[] | undefined {
  if (!Array.isArray(input)) return undefined;
  const items = input
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => {
      const next: Record<string, unknown> = {};
      if (typeof item.nodeId === "string") next.nodeId = item.nodeId;
      if (typeof item.status === "string" && ["planned", "in_progress", "completed", "skipped"].includes(item.status as string)) {
        next.status = item.status;
      }
      if (typeof item.actualWordCount === "number") next.actualWordCount = item.actualWordCount;
      return next;
    })
    .filter((item) => item.nodeId && item.status);
  return items.length > 0 ? items : undefined;
}

function sanitizeFieldChanges(raw: unknown): Record<string, unknown>[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((fc): fc is Record<string, unknown> => Boolean(fc) && typeof fc === "object")
    .map((fc) => {
      const next: Record<string, unknown> = {};
      if (typeof fc.field === "string") next.field = fc.field;
      if (typeof fc.operation === "string" && ["add", "remove", "update"].includes(fc.operation as string)) {
        next.operation = fc.operation;
      }
      if (typeof fc.oldValue === "string") next.oldValue = fc.oldValue;
      if (typeof fc.newValue === "string") next.newValue = fc.newValue;
      return next;
    })
    .filter((fc) => fc.field && fc.operation);
}

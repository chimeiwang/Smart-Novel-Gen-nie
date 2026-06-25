/**
 * AgentUpdates data-channel contract.
 *
 * This is the single source of truth for what may travel through short
 * tool arguments and what must travel through marked assistant text blocks.
 */

import { z } from "zod";

export const TOOL_SHORT_TEXT_MAX = 240;
export const TOOL_MEDIUM_TEXT_MAX = 500;

export const TEXT_UPDATE_SECTIONS = [
  "outlineContent",
  "worldSetting",
  "storyBackground",
] as const;
export type TextUpdateSection = typeof TEXT_UPDATE_SECTIONS[number];

export const ARRAY_UPDATE_SECTIONS = [
  "characters",
  "locations",
  "items",
  "factions",
  "glossaries",
  "characterExperiences",
  "outline",
  "outlineAdjustments",
  "foreshadowing",
  "references",
] as const;
export type ArrayUpdateSection = typeof ARRAY_UPDATE_SECTIONS[number];

export const ITEM_TEXT_BLOCK_SECTIONS = [
  "characters",
  "locations",
  "items",
  "factions",
  "glossaries",
  "characterExperiences",
  "outlineAdjustments",
  "foreshadowing",
  "references",
] as const;
export type ItemTextBlockSection = typeof ITEM_TEXT_BLOCK_SECTIONS[number];

export const ITEM_TEXT_BLOCK_FIELDS = [
  "content",
  "description",
  "background",
  "personality",
  "appearance",
  "coreDesire",
  "behaviorBoundaries",
  "speechStyle",
  "relationshipPrinciples",
  "shortTermGoal",
  "combatAbility",
  "specialSkills",
  "statusNote",
  "climate",
  "culture",
  "effect",
  "origin",
  "definition",
  "plantedContent",
  "expectedPayoff",
  "payoffNote",
] as const;
export type ItemTextBlockField = typeof ITEM_TEXT_BLOCK_FIELDS[number];

export const ITEM_TEXT_BLOCK_FIELDS_BY_SECTION: Record<ItemTextBlockSection, readonly ItemTextBlockField[]> = {
  characters: [
    "background", "personality", "appearance", "coreDesire", "behaviorBoundaries",
    "speechStyle", "relationshipPrinciples", "shortTermGoal", "combatAbility",
    "specialSkills", "statusNote",
  ],
  locations: ["description", "climate", "culture"],
  items: ["description", "effect", "origin"],
  factions: ["description"],
  glossaries: ["definition"],
  characterExperiences: ["content"],
  outlineAdjustments: ["content"],
  foreshadowing: ["plantedContent", "expectedPayoff", "payoffNote"],
  references: ["content"],
};

export const OUTLINE_TREE_FORBIDDEN_TOOL_FIELDS = [
  "parentId",
  "parentKey",
  "clientKey",
  "content",
] as const;

export const ToolShortTextSchema = z.string().trim().min(1).max(TOOL_SHORT_TEXT_MAX);
export const ToolOptionalShortTextSchema = z.string().trim().max(TOOL_SHORT_TEXT_MAX).optional();
export const ToolMediumTextSchema = z.string().trim().min(1).max(TOOL_MEDIUM_TEXT_MAX);
export const ToolOptionalMediumTextSchema = z.string().trim().max(TOOL_MEDIUM_TEXT_MAX).optional();

export const UpdateBuilderTextSectionSchema = z.enum(TEXT_UPDATE_SECTIONS);
export const UpdateBuilderItemTextSectionSchema = z.enum(ITEM_TEXT_BLOCK_SECTIONS);
export const UpdateBuilderItemTextFieldSchema = z.enum(ITEM_TEXT_BLOCK_FIELDS);

export const ForbiddenToolTextSectionsShape = Object.fromEntries(
  TEXT_UPDATE_SECTIONS.map((section) => [section, z.never().optional()])
) as { [K in TextUpdateSection]: z.ZodOptional<z.ZodNever> };

export const ForbiddenOutlineTreeToolFieldsShape = Object.fromEntries(
  OUTLINE_TREE_FORBIDDEN_TOOL_FIELDS.map((field) => [field, z.never().optional()])
) as { [K in typeof OUTLINE_TREE_FORBIDDEN_TOOL_FIELDS[number]]: z.ZodOptional<z.ZodNever> };

export function isTextUpdateSection(section: string): section is TextUpdateSection {
  return (TEXT_UPDATE_SECTIONS as readonly string[]).includes(section);
}

export function isItemTextBlockFieldAllowed(section: string, field: string): boolean {
  if (!isItemTextBlockSection(section)) return false;
  return ITEM_TEXT_BLOCK_FIELDS_BY_SECTION[section].includes(field as ItemTextBlockField);
}

function isItemTextBlockSection(section: string): section is ItemTextBlockSection {
  return (ITEM_TEXT_BLOCK_SECTIONS as readonly string[]).includes(section);
}

export function formatStringUnion(values: readonly string[]): string {
  return values.map((value) => `"${value}"`).join(" | ");
}

export const TEXT_UPDATE_SECTIONS_TEXT = TEXT_UPDATE_SECTIONS.join("、");
export const OUTLINE_TREE_FORBIDDEN_TOOL_FIELDS_TEXT = OUTLINE_TREE_FORBIDDEN_TOOL_FIELDS.join("、");
export const ITEM_TEXT_BLOCK_TOOLS_TEXT = "put_update_item_text_block / put_update_item_text_blocks";
export const ITEM_TEXT_BLOCK_TOOLS_CN_TEXT = "put_update_item_text_block 或 put_update_item_text_blocks";
export const UPDATE_BUILDER_TOOL_CHAIN_TEXT =
  "start_update_builder → append_outline_tree / append_update_batch / put_update_text_block / put_update_item_text_block(s) → finish_update_builder";
export const LORE_UPDATE_BUILDER_TOOL_CHAIN_TEXT =
  "start_update_builder → append_update_batch / put_update_text_block / put_update_item_text_block(s) → finish_update_builder";

export const AGENT_UPDATE_CHANNEL_RULES_PROMPT = [
  "## AgentUpdates 数据通道规则（必须遵守）",
  "",
  "- tool arguments 只能放短结构化命令，不能承载长正文。",
  `- propose_updates / append_update_batch 的 updates 禁止包含 ${TEXT_UPDATE_SECTIONS_TEXT}；这些长文本 section 必须用 put_update_text_block，并把正文放进 ARTIFACT_OUTPUT_START/END 标记块。`,
  `- 所有数组 item 的文本字段在 tool arguments 中最多 ${TOOL_SHORT_TEXT_MAX} 字，只能写短摘要；长背景、长描述、长梗概、长伏笔说明必须先创建/定位 item，再用 ${ITEM_TEXT_BLOCK_TOOLS_TEXT} 从 marker block 写入。`,
  `- append_outline_tree 是纯结构工具，只允许 title、estimatedWordCount 和 stage → plotUnits → chapterGroups 层级；禁止 ${OUTLINE_TREE_FORBIDDEN_TOOL_FIELDS_TEXT}。`,
  "- 多个长字段优先使用 put_update_item_text_blocks，一次工具调用对应多个 ARTIFACT_OUTPUT_START/END 标记块，按 blocks 顺序合并。",
].join("\n");

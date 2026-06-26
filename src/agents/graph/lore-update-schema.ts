/**
 * 设定更新 Schema（Phase 2：重导出层）
 *
 * @module agents/graph/lore-update-schema
 * @description Phase 2 重构后，sanitize/hasAgentUpdates 委托给共享契约。
 *  本文件保留 LORE_UPDATE_SCHEMA_PROMPT 并重导出共享函数。
 *
 * @phase Phase 2 — AgentUpdates 契约统一
 */

// 重导出（唯一来源为 shared/contracts/agent-updates.ts）
import {
  AGENT_UPDATE_CHANNEL_RULES_PROMPT,
  ITEM_TEXT_BLOCK_TOOLS_CN_TEXT,
  LORE_UPDATE_BUILDER_TOOL_CHAIN_TEXT,
  TOOL_SHORT_TEXT_MAX,
  UPDATE_BUILDER_TOOL_CHAIN_TEXT,
} from "@/shared/contracts/agent-update-channels";

export {
  sanitizeAgentUpdates,
  hasAgentUpdates,
  type AgentUpdates,
  type AgentUpdateSection,
  ALL_UPDATE_SECTIONS,
} from "@/shared/contracts/agent-updates";

// ============================================
// LORE_UPDATE_SCHEMA_PROMPT（保留）
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

// Phase C 返工：LORE_UPDATE_SCHEMA_PROMPT 改为描述 tool args 结构，不再引用 JSON updates 字段
export const LORE_UPDATE_SCHEMA_PROMPT = [
  "## 设定更新能力",
  "",
  "当且仅当用户明确要求新增、修改、删除、保存、更新设定时，提交结构化变更。",
  `短小变更使用 propose_updates；批量设定、长世界设定、长故事背景或带大量格式内容时，使用 update builder 工具链：${LORE_UPDATE_BUILDER_TOOL_CHAIN_TEXT}。`,
  AGENT_UPDATE_CHANNEL_RULES_PROMPT,
  "普通讨论、分析、建议时不要调用此工具。",
  "你不能直接写数据库；系统会把 updates 展示给用户确认，确认后再保存。",
  "",
  "### 通用规则",
  "- create：必须提供最小必填字段，其他未知字段不要编造。",
  "- update/delete：优先提供已知 id；没有 id 时才用 name/term 定位。",
  "- update：只填写用户要求改变或你确定需要补充的字段，不要重写整条设定。",
  "- fieldChanges 只能使用下方白名单字段；不确定字段名时不要写 fieldChanges，直接写对应顶层字段。",
  "- fieldChanges 不允许 remove 必填字段：角色/地点/物品/势力 name，术语 term/definition。",
  "- 关系字段必须写数据库 id：character.factionId、item.ownerId、location.parentId、faction.baseId。只知道名称时，先用工具查询对应详情或不要填。",
  "- currentStatus 只能是 active、missing、dead、imprisoned、unknown。",
  "",
  "### 短 updates 参数结构（设定顾问允许的 section）",
  "```json",
  "{",
  "  \"updates\": {",
  "    \"characters\": [],",
  "    \"locations\": [],",
  "    \"items\": [],",
  "    \"factions\": [],",
  "    \"glossaries\": [],",
  "    \"characterExperiences\": []",
  "  }",
  "}",
  "```",
  "",
  "大纲、章节结构、伏笔安排不属于设定顾问的保存边界；遇到这类修改请求，请说明职责边界并等待工作流重新分派。",
  "",
  "### 角色 characters[]",
  "允许字段：action, id, characterId, name, aliases, gender, age, appearance, personality, identity, background, coreDesire, behaviorBoundaries, speechStyle, relationshipPrinciples, shortTermGoal, factionId, powerLevel, combatAbility, specialSkills, currentStatus, statusNote, fieldChanges。",
  "create 必填：action=\"create\", name。update/delete 必填：action + id/characterId/name 之一。",
  "",
  "### 地点 locations[]",
  "允许字段：action, id, locationId, name, aliases, type, parentId, climate, culture, description, fieldChanges。",
  "",
  "### 物品 items[]",
  "允许字段：action, id, itemId, name, aliases, type, rarity, effect, origin, description, ownerId, fieldChanges。",
  "",
  "### 势力 factions[]",
  "允许字段：action, id, factionId, name, aliases, type, baseId, description, fieldChanges。",
  "",
  "### 术语 glossaries[]",
  "允许字段：action, id, glossaryId, term, definition, category, fieldChanges。",
  "",
  "### 角色经历 characterExperiences[]",
  "允许字段：action, id, characterId, characterName, chapterId, chapterTitle, content, order。",
  "",
].join("\n");

export const PLOT_UPDATE_SCHEMA_PROMPT = [
  "## 剧情更新能力",
  "",
  "当且仅当用户明确要求修改、保存、更新大纲、章节结构或伏笔时，提交结构化变更。",
  `短小变更使用 propose_updates；大纲创建、重构、展开、迁移、批量节点树、长总纲或章节组长梗概时，使用 update builder 工具链：${UPDATE_BUILDER_TOOL_CHAIN_TEXT}。`,
  AGENT_UPDATE_CHANNEL_RULES_PROMPT,
  "复杂大纲树必须优先用 append_outline_tree 提交 stage → plotUnits → chapterGroups 嵌套树；append_update_batch.outlineAdjustments 只用于短小修补、已有节点更新或兼容旧流程。",
  "普通讨论、分析、建议时不要调用此工具。系统会把 updates 展示给用户确认，确认后再保存。",
  "",
  "### 短 updates 参数结构（剧情顾问允许的 section）",
  "```json",
  "{",
  "  \"updates\": {",
  "    \"outline\": [],",
  "    \"outlineAdjustments\": [],",
  "    \"foreshadowing\": []",
  "  }",
  "}",
  "```",
  "",
  "### 总纲 outlineContent",
  "用于更新 Outline.content，承载全书方向、主线承诺和阶段性结构摘要。创建或重构结构化大纲时，优先同时提供 outlineContent 和 outlineAdjustments，但 outlineContent 必须通过 put_update_text_block 写入，不得出现在 propose_updates 或 append_update_batch 的 updates 参数中。",
  "",
  "### 大纲更新 outline[]",
  "字段：nodeId（必填）, status（planned/in_progress/completed/skipped）, actualWordCount。",
  "",
  "### 大纲调整 outlineAdjustments[]",
  "允许字段：action, nodeId, nodeTitle, clientKey, parentKey, title, content, kind, parentId, status, estimatedWordCount, actualWordCount。",
  "kind 必须是 stage（阶段/卷）、plot_unit（剧情单元）、chapter_group（章节组）之一。",
  `create 必填：action=\"create\", title 或 nodeTitle，kind。content 只写 ${TOOL_SHORT_TEXT_MAX} 字以内的节点职责摘要；章节组详细梗概、长段落、对白和正文必须用 ${ITEM_TEXT_BLOCK_TOOLS_CN_TEXT} 写入对应 item。`,
  "复杂批量创建新节点树时不要手写 outlineAdjustments；使用 append_outline_tree 提交嵌套树，由服务端生成 clientKey/parentKey。",
  "只有短小修补或兼容旧流程才手写 outlineAdjustments。手写时必须给每个新节点提供稳定 clientKey；子节点用 parentKey 指向同批父节点；已有父节点才用 parentId；不要同时提供 parentId 和 parentKey。",
  "使用 append_update_batch 手写 outlineAdjustments 时，可以跨批次追加大纲节点；parentKey 可以引用之前批次已追加的 clientKey，finish_update_builder 会统一校验完整树。",
  "层级约束：stage 只能顶层，不能有 parentId/parentKey；plot_unit 必须挂在 stage 下；chapter_group 必须挂在 plot_unit 下。",
  "结构优先级：kind、父子关系、title、短摘要、status 比字数更重要。estimatedWordCount 和 actualWordCount 是辅助字段，有明确规划时再填写，不要为了填数字而编造。",
  "内容职责摘要：stage 写阶段目标和卷级转折；plot_unit 写核心冲突、反转和结果；chapter_group 写章节组职责、覆盖章节范围、爆点/钩子。详细梗概走 item block。",
  "update/delete 必填：action + nodeId/nodeTitle/title 之一。",
  "",
  "### 伏笔 foreshadowing[]",
  "允许字段：action（create/update/payoff/abandon）, id, name, plantedAt, plantedContent, expectedPayoff, payoffAt, payoffNote。",
  `plantedContent、expectedPayoff、payoffNote 在 tool arguments 中只能写短摘要；长说明走 ${ITEM_TEXT_BLOCK_TOOLS_CN_TEXT}。`,
].join("\n");

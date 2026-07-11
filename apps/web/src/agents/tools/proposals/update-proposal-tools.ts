/**
 * Proposal 写入工具（Phase 7 创建，Phase C 返工）
 *
 * @module agents/tools/proposals/update-proposal-tools
 * @description 查询型 proposal 工具：返回对象当前状态和模板，帮助模型构造
 *  propose_updates control tool 的短 updates 参数。
 *
 * 流程：LLM 调用 proposal 工具 → 获得模板和当前状态 →
 *       短小变更调用 propose_updates control tool（在 updates 参数中提交短结构）→
 *       processControlEvents 处理 → interrupt 用户确认 → executeUpdates
 *
 * Phase C 返工：所有 instruction 改为指向 propose_updates tool 的 updates 参数，
 *   不再引用 "JSON 输出的 updates 字段"。长文本不得进入 proposal/propose_updates 参数。
 */

import { z } from "zod";
import type { ToolDefinition, ToolExecutorFn } from "../registry";
import { registerTool } from "../registry";
import { writeProposalPermission } from "../permissions";
import {
  ITEM_TEXT_BLOCK_TOOLS_CN_TEXT,
  TOOL_SHORT_TEXT_MAX,
  UPDATE_BUILDER_TOOL_CHAIN_TEXT,
} from "@/shared/contracts/agent-update-channels";

// ============================================
// 角色 Proposal 工具
// ============================================

export const PROPOSE_UPDATE_CHARACTER_DEF: ToolDefinition = {
  name: "propose_update_character",
  description: "生成角色修改 proposal。参数：character_name（角色名）+ 要修改的字段。返回 updates 模板供填充。",
  inputSchema: z.object({
    character_name: z.string().min(1),
  }),
  permission: writeProposalPermission("proposal.lore"),
  toolKind: "proposal",
};

export const proposeUpdateCharacterExecutor: ToolExecutorFn = (args, state) => {
  const charName = args.character_name as string;
  const d = state.novelData as Record<string, unknown>;
  const chars = (d.characters as Record<string, unknown>[]) || [];
  const c = chars.find((ch: Record<string, unknown>) =>
    (ch.name as string).includes(charName) || charName.includes(ch.name as string)
  );

  const current: Record<string, unknown> = c || { name: charName, note: "角色不存在，将创建新角色" };

  return JSON.stringify({
    type: "PROPOSAL_TEMPLATE",
    tool: "propose_update_character",
    message: `请将你对 ${charName} 的修改意图放入 agentOutput 的 updates.characters 数组中。`,
    currentState: {
      name: current.name,
      personality: current.personality,
      identity: current.identity,
      background: current.background,
      coreDesire: current.coreDesire,
      behaviorBoundaries: current.behaviorBoundaries,
      speechStyle: current.speechStyle,
      relationshipPrinciples: current.relationshipPrinciples,
      shortTermGoal: current.shortTermGoal,
      gender: current.gender,
      age: current.age,
      powerLevel: current.powerLevel,
      combatAbility: current.combatAbility,
      specialSkills: current.specialSkills,
      currentStatus: current.currentStatus,
      statusNote: current.statusNote,
    },
    updatesTemplate: {
      characters: [{
        action: c ? "update" : "create",
        name: charName,
        "// 以下为可选字段，只填你要修改的": "",
        personality: "修改后的性格",
        identity: "修改后的身份",
        background: "修改后的背景",
        coreDesire: "修改后的核心欲望",
        behaviorBoundaries: "修改后的行为边界",
        speechStyle: "修改后的说话习惯",
        relationshipPrinciples: "修改后的关系原则",
        shortTermGoal: "修改后的短期目标",
        gender: "性别",
        age: "年龄",
        powerLevel: "实力等级",
        combatAbility: "战斗能力",
        specialSkills: "特殊技能",
        currentStatus: "active | missing | dead | imprisoned | unknown",
        statusNote: "状态说明",
      }],
    },
    instruction: `将上述模板作为参考，短小变更调用 propose_updates control tool，在 updates 参数中提交短结构化变更，修改你需要的值，删除不需要的字段，然后用户会确认。角色背景、性格等长文本不要放进 propose_updates；先用 update builder 创建/定位角色 item，再用 ${ITEM_TEXT_BLOCK_TOOLS_CN_TEXT} 写入长字段。`,
  }, null, 2);
};

// ============================================
// 角色状态 Proposal 工具
// ============================================

export const PROPOSE_UPDATE_CHARACTER_STATUS_DEF: ToolDefinition = {
  name: "propose_update_character_status",
  description: "生成角色状态更新 proposal。参数：character_name、status。",
  inputSchema: z.object({
    character_name: z.string().min(1),
    status: z.enum(["active", "missing", "dead", "imprisoned", "unknown"]),
  }),
  permission: writeProposalPermission("proposal.lore"),
  toolKind: "proposal",
};

export const proposeUpdateCharacterStatusExecutor: ToolExecutorFn = (args) => {
  return JSON.stringify({
    type: "PROPOSAL_TEMPLATE",
    tool: "propose_update_character_status",
    updatesTemplate: {
      characters: [{
        action: "update",
        name: args.character_name,
        currentStatus: args.status,
      }],
    },
    instruction: "将上述模板作为参考，调用 propose_updates control tool，在 updates 参数中提交短结构化变更，用户会确认后执行。",
  }, null, 2);
};

// ============================================
// 大纲 Proposal 工具
// ============================================

export const PROPOSE_UPDATE_OUTLINE_DEF: ToolDefinition = {
  name: "propose_update_outline",
  description: `生成大纲节点短更新 proposal。参数：node_title、kind/status/content_summary/estimated_word_count/client_key/parent_key（可选）。content_summary 最多 ${TOOL_SHORT_TEXT_MAX} 字，只能是短摘要。`,
  inputSchema: z.object({
    node_title: z.string().min(1),
    action: z.enum(["create", "update"]).optional(),
    client_key: z.string().optional(),
    parent_key: z.string().optional(),
    kind: z.enum(["stage", "plot_unit", "chapter_group"]).optional(),
    status: z.enum(["planned", "in_progress", "completed", "skipped"]).optional(),
    content_summary: z.string().max(TOOL_SHORT_TEXT_MAX).optional(),
    estimated_word_count: z.number().optional(),
  }),
  permission: writeProposalPermission("proposal.plot"),
  toolKind: "proposal",
};

export const proposeUpdateOutlineExecutor: ToolExecutorFn = (args) => {
  return JSON.stringify({
    type: "PROPOSAL_TEMPLATE",
    tool: "propose_update_outline",
    updatesTemplate: {
      outlineAdjustments: [{
        action: args.action ?? "update",
        nodeTitle: args.node_title,
        title: args.node_title,
        clientKey: args.client_key,
        parentKey: args.parent_key,
        kind: args.kind,
        status: args.status,
        content: args.content_summary,
        estimatedWordCount: args.estimated_word_count,
      }],
    },
    instruction: `将上述模板作为参考，短小修补可以调用 propose_updates control tool，在 updates 参数中提交短结构化变更。content 只能是 ${TOOL_SHORT_TEXT_MAX} 字以内职责摘要；长章节组梗概、整章梗概或正文不要放进 propose_updates，必须使用 ${UPDATE_BUILDER_TOOL_CHAIN_TEXT}。注意 append_outline_tree 本身不接受 content。`,
  }, null, 2);
};

// ============================================
// 伏笔 Proposal 工具
// ============================================

export const PROPOSE_ADD_FORESHADOWING_DEF: ToolDefinition = {
  name: "propose_add_foreshadowing",
  description: "生成新伏笔短 proposal。参数：name、planted_content_summary、expected_payoff_summary。",
  inputSchema: z.object({
    name: z.string().min(1),
    planted_content_summary: z.string().max(TOOL_SHORT_TEXT_MAX).optional(),
    expected_payoff_summary: z.string().max(TOOL_SHORT_TEXT_MAX).optional(),
  }),
  permission: writeProposalPermission("proposal.plot"),
  toolKind: "proposal",
};

export const proposeAddForeshadowingExecutor: ToolExecutorFn = (args) => {
  return JSON.stringify({
    type: "PROPOSAL_TEMPLATE",
    tool: "propose_add_foreshadowing",
    updatesTemplate: {
      foreshadowing: [{
        action: "create",
        name: args.name,
        plantedContent: args.planted_content_summary,
        expectedPayoff: args.expected_payoff_summary,
      }],
    },
    instruction: `将上述模板作为参考，调用 propose_updates control tool，在 updates 参数中提交短结构化变更，用户会确认后执行。伏笔长说明不要放进 propose_updates；需要长文本时用 ${UPDATE_BUILDER_TOOL_CHAIN_TEXT}。`,
  }, null, 2);
};

export const PROPOSE_RESOLVE_FORESHADOWING_DEF: ToolDefinition = {
  name: "propose_resolve_foreshadowing",
  description: "生成伏笔回收 proposal。参数：foreshadowing_name。",
  inputSchema: z.object({
    foreshadowing_name: z.string().min(1),
    payoff_note_summary: z.string().max(TOOL_SHORT_TEXT_MAX).optional(),
  }),
  permission: writeProposalPermission("proposal.plot"),
  toolKind: "proposal",
};

export const proposeResolveForeshadowingExecutor: ToolExecutorFn = (args) => {
  return JSON.stringify({
    type: "PROPOSAL_TEMPLATE",
    tool: "propose_resolve_foreshadowing",
    updatesTemplate: {
      foreshadowing: [{
        action: "payoff",
        name: args.foreshadowing_name,
        payoffNote: args.payoff_note_summary,
      }],
    },
    instruction: `将上述模板作为参考，调用 propose_updates control tool，在 updates 参数中提交短结构化变更，用户会确认后执行。回收说明如需长文本，请用 ${UPDATE_BUILDER_TOOL_CHAIN_TEXT}。`,
  }, null, 2);
};

// ============================================
// 注册
// ============================================

registerTool(PROPOSE_UPDATE_CHARACTER_DEF, proposeUpdateCharacterExecutor);
registerTool(PROPOSE_UPDATE_CHARACTER_STATUS_DEF, proposeUpdateCharacterStatusExecutor);
registerTool(PROPOSE_UPDATE_OUTLINE_DEF, proposeUpdateOutlineExecutor);
registerTool(PROPOSE_ADD_FORESHADOWING_DEF, proposeAddForeshadowingExecutor);
registerTool(PROPOSE_RESOLVE_FORESHADOWING_DEF, proposeResolveForeshadowingExecutor);

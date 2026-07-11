/**
 * 工具权限模型
 *
 * @module agents/tools/permissions
 * @description Phase 3 工具层重构：每个工具必须声明权限元信息。
 *
 * 执行规则：
 * - readOnly && concurrencySafe → 可并行执行
 * - !readOnly → 一律不允许 LLM 直接执行写库，只能生成 proposal
 * - requiresConfirmation → proposal 交给 ReviewArtifact / operationWorkflow interrupt
 *
 * @phase Phase 3 — 工具层重构
 */

/** 工具能力域（Phase 3：稳定命名。Phase 0 新增 control.*） */
export type ToolCapability =
  | "novel.read"
  | "character.read"
  | "lore.read"
  | "plot.read"
  | "chapter.read"
  | "style.read"
  | "artifact.read"
  | "proposal.lore"
  | "proposal.plot"
  | "control.quality"
  | "control.proposal"
  | "control.builder"
  | "control.artifact"
  | "control.beat"
  | "control.validation"
  | "control.evaluation";

/** 工具权限元信息 */
export interface ToolPermission {
  /** 是否只读（不修改数据库） */
  readOnly: boolean;
  /** 是否并发安全（可与其他工具并行执行） */
  concurrencySafe: boolean;
  /** 是否需要用户确认后才能执行 */
  requiresConfirmation: boolean;
  /** 工具所属能力域 */
  capability: ToolCapability;
  /** 工具所属 Agent（可选，用于工具分配） */
  agentIds?: string[];
}

/** 默认只读工具权限 */
export const READ_ONLY_TOOL: ToolPermission = {
  readOnly: true,
  concurrencySafe: true,
  requiresConfirmation: false,
  capability: "lore.read",
};

/** 只读工具权限工厂 */
export function readOnlyPermission(
  capability: ToolCapability,
  agentIds?: string[]
): ToolPermission {
  return {
    readOnly: true,
    concurrencySafe: true,
    requiresConfirmation: false,
    capability,
    agentIds,
  };
}

/** 写入工具权限（LLM 不得直接执行） */
export function writeProposalPermission(
  capability: ToolCapability,
  agentIds?: string[]
): ToolPermission {
  return {
    readOnly: false,
    concurrencySafe: false,
    requiresConfirmation: true,
    capability,
    agentIds,
  };
}

/** Phase 0：Control 工具权限工厂 */
export function controlToolPermission(
  capability: ToolCapability,
  agentIds?: string[]
): ToolPermission {
  return {
    readOnly: true,
    concurrencySafe: true,
    requiresConfirmation: false,
    capability,
    agentIds,
  };
}

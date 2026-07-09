/**
 * 工具层统一导出
 *
 * @module agents/tools
 * @description Phase 3 工具层重构：统一导出新的工具注册表、权限模型和所有只读工具。
 *
 * @phase Phase 3 — 工具层重构
 */

// 权限模型
export {
  type ToolPermission,
  type ToolCapability,
  READ_ONLY_TOOL,
  readOnlyPermission,
  writeProposalPermission,
  controlToolPermission,
} from "./permissions";

// 注册表
export {
  type ToolDefinition,
  type ToolExecutorFn,
  registerTool,
  getTool,
  getAllTools,
  getToolsByCapability,
  getToolsByAgent,
  executeTool,
  getOpenAITools,
  getWriteToolNames,
} from "./registry";

// 只读工具（导入触发注册）
import "./read/novel-tools";
import "./read/character-tools";
import "./read/lore-tools";
import "./read/plot-tools";
import "./read/artifact-tools";
import "./read/reference-tools";

// Proposal 工具（Phase 7）
import "./proposals/update-proposal-tools";

// Control 工具（Phase 0）
import "./control/control-tools";

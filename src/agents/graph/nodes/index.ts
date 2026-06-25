/**
 * Agent Node 统一导出（v3.0 四Agent架构）
 *
 * @module agents/graph/nodes
 * @description 所有 Agent Node 的统一导出
 *
 * ## v5.3 五Agent架构
 * - 设定顾问 (loreAdvisorNode) - 设定讨论/修改/冲突检测
 * - 剧情顾问 (plotAdvisorNode) - 剧情讨论/大纲管理
 * - 作家 (authorNode) - 正文生成
 * - 校验员 (validatorNode) - 一致性检查/触发重写
 * - 网文编辑 (editorNode) - 商业性评审/返工 brief
 */

// 五Agent核心节点
export { loreAdvisorNode } from "./lore-advisor-node";
export { plotAdvisorNode } from "./plot-advisor-node";
export { authorNode } from "./author-node";
export { validatorNode } from "./validator-node";
export { editorNode } from "./editor-node";

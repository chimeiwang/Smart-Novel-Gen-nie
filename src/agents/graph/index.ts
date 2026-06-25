/**
 * LangGraph 模块统一导出（v5.3 五Agent架构）
 *
 * @module agents/graph
 * @description LangGraph 工作流的统一导出
 */

// 状态定义
export type {
  WritingState,
  WritingPhase,
  AgentOutput,
  NovelData,
  CoreAgentId,
  AgentMessage,
  ConflictDetail,
  PendingAgentCall,
} from "./state";
export {
  CORE_AGENT_IDS,
  ALL_AGENT_IDS,
  AGENT_NAMES,
  AGENT_ID_TO_KEY,
  KEY_TO_AGENT_ID,
  AGENT_TO_OUTPUT_FIELD,
  getAgentOutputField,
  getAgentOutput,
  setAgentOutput,
  generateMessageId,
  createAgentOutput,
  isValidAgentId,
  getAgentName,
} from "./state";

// Schema（已移除，使用 state.ts 中的定义）
// export { writingStateReducer, EMPTY_WRITING_STATE } from "./schema";

// Node
export * from "./nodes";

// 执行器
export {
  executeWritingWorkflow,
  resumeWriting,
  createInitialState,
  persistUpdates,
  rollbackTaskUpdates,
  previewUpdates,
  type WorkflowInitialState,
} from "./executor";

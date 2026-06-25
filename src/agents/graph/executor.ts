/**
 * LangGraph 工作流执行器（Phase 5 重构：兼容重导出层）
 *
 * @module agents/graph/executor
 * @description Phase 5 拆分后，此文件只做重导出，保持向后兼容。
 *  实际逻辑分布在：
 *  - graph-definition.ts：LangGraph StateGraph 定义
 *  - sse-adapter.ts：SSE 事件转换
 *  - task-state.ts：WritingTask 持久化
 *  - workflow-runner.ts：HTTP 入口（executeWritingWorkflow / resumeWriting / createInitialState）
 *
 * @phase Phase 5 — 拆分 LangGraph 执行器
 */

// 核心入口（API 路由使用）
export {
  executeWritingWorkflow,
  resumeWriting,
  createInitialState,
  type WorkflowInitialState,
} from "./workflow-runner";

// 图定义（测试/调试使用）
export { getGraph, type GraphState } from "./graph-definition";

// SSE 适配器（测试/调试使用）
export {
  SSE_HEADERS,
  STREAM_MODES,
  createDirectStreamCallbacks,
  createSSEController,
  sendAgentDoneFallback,
  sanitizeStateUpdate,
  type SendEventFn,
} from "./sse-adapter";

// 任务持久化
export {
  updateTaskState,
  persistUpdates,
  rollbackTaskUpdates,
  previewUpdates,
} from "./task-state";

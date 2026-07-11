/**
 * LangSmith 追踪器模块（GraphOS Dashboard 监控）
 *
 * @module agents/lib/langsmith-tracer
 */

import { logger } from "@/shared/lib/logger";
import type { CoreAgentId } from "@/agents/graph/state";
import { getAgentObservabilityConfig } from "@/shared/env";

let isEnabled = false;
let isInitialized = false;

type TraceRunner = <T>(
  name: string,
  metadata: Record<string, unknown>,
  fn: () => Promise<T>
) => Promise<T>;

let injectedTraceRunner: TraceRunner | null = null;

interface LangSmithConfig {
  apiKey?: string;
  project?: string;
  tracing?: boolean;
}

function getLangSmithConfig(): LangSmithConfig {
  const observability = getAgentObservabilityConfig();
  return {
    apiKey: process.env.LANGSMITH_API_KEY || process.env.LANGCHAIN_API_KEY,
    project: process.env.LANGSMITH_PROJECT || process.env.LANGCHAIN_PROJECT || "inkforge",
    tracing: observability.langSmithTracingEnabled &&
      (process.env.LANGSMITH_TRACING === "true" || process.env.LANGCHAIN_TRACING_V2 === "true"),
  };
}

/** @6.2 */
export function isLangSmithEnabled(): boolean {
  return isEnabled;
}

/** @6.2 */
export async function initLangSmithTracer(): Promise<void> {
  if (isInitialized) return;

  const config = getLangSmithConfig();

  if (!config.apiKey) {
    logger.info("LANGSMITH", "未配置 API Key，跳过追踪器初始化");
    isEnabled = false;
    isInitialized = true;
    return;
  }

  if (!config.tracing) {
    logger.info("LANGSMITH", "追踪已禁用（LANGSMITH_TRACING_ENABLED 或 LANGSMITH_TRACING 未启用）");
    isEnabled = false;
    isInitialized = true;
    return;
  }

  process.env.LANGSMITH_API_KEY = config.apiKey;
  process.env.LANGCHAIN_API_KEY = config.apiKey;
  process.env.LANGSMITH_PROJECT = config.project || "inkforge";
  process.env.LANGCHAIN_PROJECT = config.project || "inkforge";
  process.env.LANGSMITH_TRACING = "true";
  process.env.LANGCHAIN_TRACING_V2 = "true";

  isEnabled = true;
  isInitialized = true;

  logger.info("LANGSMITH", "追踪器初始化成功", {
    project: config.project,
    endpoint: "https://api.smith.langchain.com",
  });
  logger.info("LANGSMITH", "请在 https://smith.langchain.com/ 查看追踪数据");
}

/**
 * 通用追踪包装器
 * @6.2 — 被 traceAgent/traceLLM/traceWorkflow/traceTool 调用
 */
export async function trace<T>(
  name: string,
  metadata: Record<string, unknown>,
  fn: () => Promise<T>
): Promise<T> {
  const startTime = Date.now();

  if (!isEnabled) {
    return fn();
  }

  try {
    const traceMetadata = {
      ...metadata,
      service: "inkforge",
    };

    if (injectedTraceRunner) {
      return injectedTraceRunner(name, traceMetadata, fn);
    }

    const { traceable } = await import("langsmith/traceable");

    const tracedFn = traceable(fn, {
      name,
      metadata: traceMetadata,
    });

    const result = await tracedFn();

    const duration = Date.now() - startTime;
    logger.debug("LANGSMITH", `追踪完成: ${name}`, {
      durationMs: duration,
    });

    return result;
  } catch (error) {
    const duration = Date.now() - startTime;
    logger.error("LANGSMITH", `追踪执行失败: ${name}`, {
      durationMs: duration,
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
}

/** @6.2 — 被 @5.1 agentNode 调用 */
export async function traceAgent<T>(
  agentId: CoreAgentId | string,
  metadata: Record<string, unknown>,
  fn: () => Promise<T>
): Promise<T> {
  return trace(`agent:${agentId}`, metadata, fn);
}

/** @6.2 — 被 @5.2 callLLM/callLLMWithTools/callLLMSync 调用 */
export async function traceLLM<T>(
  callType: string,
  metadata: Record<string, unknown>,
  fn: () => Promise<T>
): Promise<T> {
  return trace(`llm:${callType}`, metadata, fn);
}

/** @6.2 — 被 @5.1 runWritingWorkflow/resumeWritingWorkflow 调用 */
export async function traceWorkflow<T>(
  workflowType: string,
  metadata: Record<string, unknown>,
  fn: () => Promise<T>
): Promise<T> {
  return trace(`workflow:${workflowType}`, metadata, fn);
}

/** @6.2 */
export async function traceTool<T>(
  toolName: string,
  metadata: Record<string, unknown>,
  fn: () => Promise<T>
): Promise<T> {
  return trace(`tool:${toolName}`, metadata, fn);
}

/** @6.2 */
export function getTracingStats(): {
  enabled: boolean;
  initialized: boolean;
  project?: string;
} {
  const config = getLangSmithConfig();
  return {
    enabled: isEnabled,
    initialized: isInitialized,
    project: config.project,
  };
}

/** @6.2 */
export function formatAgentName(agentId: CoreAgentId | string): string {
  const nameMap: Record<string, string> = {
    "设定": "设定顾问",
    "剧情": "剧情顾问",
    "写作": "作家",
    "校验": "校验员",
  };
  return nameMap[agentId] || agentId;
}

/** @6.2 — 被 @5.1 @5.2 调用 */
export function createTraceMetadata(params: {
  taskId?: string;
  novelId?: string;
  chapterId?: string;
  agentId?: string;
  callType?: string;
}): Record<string, unknown> {
  return {
    taskId: params.taskId,
    novelId: params.novelId,
    chapterId: params.chapterId,
    agentId: params.agentId,
    callType: params.callType,
    timestamp: new Date().toISOString(),
    service: "inkforge",
  };
}

// 保留旧 API 兼容性
export {
  traceAgent as traceAgentExecution,
  traceLLM as traceLLMCall,
  traceWorkflow as traceWorkflowExecution,
};

export function __setLangSmithTraceRunnerForTests(runner: TraceRunner | null): void {
  injectedTraceRunner = runner;
}

export function __resetLangSmithTracerForTests(): void {
  isEnabled = false;
  isInitialized = false;
  injectedTraceRunner = null;
}

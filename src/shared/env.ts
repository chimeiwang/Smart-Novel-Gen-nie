export type AiConfig = {
  apiKey: string;
  baseUrl: string;
  model: string;
};

export type LLMRuntimeName = "langchain" | "legacy-openai";
export type LLMLogMode = "off" | "summary" | "full";

export type AgentObservabilityConfig = {
  workflowEventLogEnabled: boolean;
  workflowEventDebugEnabled: boolean;
  langGraphStreamEventsEnabled: boolean;
  langGraphStudioEnabled: boolean;
  langSmithTracingEnabled: boolean;
  langGraphMemorySaverEnabled: boolean;
  langGraphMemorySaverCleanupOnDone: boolean;
};

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["0", "false", "no", "off"]);

export function getAiConfig(): AiConfig {
  return {
    apiKey: process.env.OPENAI_API_KEY ?? "",
    baseUrl: process.env.OPENAI_BASE_URL ?? "https://api.deepseek.com/v1",
    model: process.env.OPENAI_MODEL ?? "deepseek-v4-flash",
  };
}

export function getLLMRuntimeName(): LLMRuntimeName {
  const runtime = process.env.LLM_RUNTIME ?? "langchain";
  if (runtime === "langchain") return "langchain";
  if (runtime === "legacy-openai") return "legacy-openai";
  throw new Error(`未知 LLM_RUNTIME: ${runtime}`);
}

export function getLLMLogMode(): LLMLogMode {
  const mode = process.env.LLM_LOG_MODE?.trim().toLowerCase() || "summary";
  if (mode === "off" || mode === "summary" || mode === "full") return mode;
  return "summary";
}

export function isEnvFlagEnabled(value: string | undefined, defaultValue: boolean): boolean {
  if (value === undefined || value.trim() === "") return defaultValue;
  const normalized = value.trim().toLowerCase();
  if (TRUE_VALUES.has(normalized)) return true;
  if (FALSE_VALUES.has(normalized)) return false;
  return defaultValue;
}

export function getAgentObservabilityConfig(): AgentObservabilityConfig {
  return {
    workflowEventLogEnabled: isEnvFlagEnabled(process.env.WORKFLOW_EVENT_LOG_ENABLED, false),
    workflowEventDebugEnabled: isEnvFlagEnabled(process.env.WORKFLOW_EVENT_DEBUG_ENABLED, false),
    langGraphStreamEventsEnabled: isEnvFlagEnabled(process.env.LANGGRAPH_STREAM_EVENTS_ENABLED, true),
    langGraphStudioEnabled: isEnvFlagEnabled(process.env.LANGGRAPH_STUDIO_ENABLED, false),
    langSmithTracingEnabled: isEnvFlagEnabled(process.env.LANGSMITH_TRACING_ENABLED, false),
    langGraphMemorySaverEnabled: isEnvFlagEnabled(process.env.LANGGRAPH_MEMORY_SAVER_ENABLED, true),
    langGraphMemorySaverCleanupOnDone: isEnvFlagEnabled(process.env.LANGGRAPH_MEMORY_SAVER_CLEANUP_ON_DONE, true),
  };
}

export function isAiConfigured() {
  return Boolean(getAiConfig().apiKey);
}

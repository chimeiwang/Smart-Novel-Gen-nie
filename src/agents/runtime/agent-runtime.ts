/**
 * Agent Runtime.
 *
 * Project-specific Agent protocol lives here. ModelRuntimePort only performs a
 * single model/tool-call turn; this class owns the tool-call loop, control tool
 * interception, terminal control handling, and visible-content aggregation.
 */

import type OpenAI from "openai";
import { traceLLMCall, traceTool } from "@/agents/lib/langsmith-tracer";
import { logger } from "@/shared/lib/logger";
import { getTool } from "@/agents/tools/registry";
import {
  CONTROL_TOOL_NAMES,
  formatControlToolValidationMessage,
  parseControlEventArgsDetailed,
} from "@/shared/contracts/agent-control";
import {
  aggregateVisibleParts,
  getModelRuntime,
  LegacyOpenAIRuntime,
  type AgentRuntimeOptions,
  type ModelToolCall,
  type ModelRuntimePort,
} from "./model-runtime";
import type {
  AgentControlEvent,
  AgentTurnResult,
  RuntimeToolCallRecord,
  RuntimeToolResultRecord,
  TokenUsage,
} from "./turn-result";
import { parseToolCallArguments } from "./tool-arguments";

export type { AgentRuntimeOptions } from "./model-runtime";

const MAX_INVALID_CONTROL_TOOL_ATTEMPTS = 2;
const MAX_PARALLEL_SAFE_TOOLS = 5;
const DEFAULT_MODEL_TOOL_RESULT_CHAR_LIMIT = 6000;
const HEAVY_MODEL_TOOL_RESULT_CHAR_LIMIT = 3000;
const HEAVY_TOOL_RESULT_NAMES = new Set([
  "get_active_review_artifact",
  "get_review_artifact",
  "get_recent_chapters",
  "get_novel_info",
  "list_outline_summary",
  "list_characters_summary",
]);

interface ToolExecutionResult {
  content: string;
  fatal?: boolean;
  terminal?: boolean;
  unauthorized?: boolean;
}

interface AgentRoundToolExecutionResult extends ToolExecutionResult {
  id: string;
  toolName: string;
  parseError?: boolean;
}

interface AgentRuntimeImplDeps {
  client?: OpenAI;
  isAiConfigured?: () => boolean;
  runtime?: ModelRuntimePort;
}

export interface AgentRuntime {
  runTurn(options: AgentRuntimeOptions): Promise<AgentTurnResult>;
}

export class AgentRuntimeImpl implements AgentRuntime {
  private readonly runtime?: ModelRuntimePort;
  private readonly injectedClient?: OpenAI;
  private readonly isConfigured?: () => boolean;

  constructor(deps: AgentRuntimeImplDeps = {}) {
    this.runtime = deps.runtime;
    this.injectedClient = deps.client;
    this.isConfigured = deps.isAiConfigured;
  }

  async runTurn(options: AgentRuntimeOptions): Promise<AgentTurnResult> {
    const meta = options.metadata ?? {};
    return traceLLMCall(
      (meta.callType as string) || "agent-runtime",
      meta as Record<string, unknown>,
      async () => this.runToolLoop(options)
    );
  }

  private async runToolLoop(options: AgentRuntimeOptions): Promise<AgentTurnResult> {
    const runtime = this.resolveRuntime();
    const requestId = logger.generateRequestId();
    const messages = [...options.messages];
    const maxIterations = options.maxIterations ?? 10;

    const controlEvents: AgentControlEvent[] = [];
    const toolCalls: RuntimeToolCallRecord[] = [];
    const toolResults: RuntimeToolResultRecord[] = [];
    const visibleContentParts: string[] = [];
    const invalidControlToolAttempts = new Map<string, number>();

    let finalUsage: TokenUsage | undefined;
    let lastAssistantText = "";
    let finishReason: string | undefined = "stop";

    for (let iteration = 1; iteration <= maxIterations; iteration++) {
      logger.info("AGENT_RUNTIME", `tool-call loop 第 ${iteration} 轮`, {
        messageCount: messages.length,
      });

      const roundOptions: AgentRuntimeOptions = {
        ...options,
        metadata: {
          ...(options.metadata ?? {}),
          agentRunId: requestId,
          modelTurn: iteration,
        },
      };
      const round = await runtime.runToolCallTurn({
        messages,
        tools: options.tools,
        onChunk: options.onChunk,
        metadata: roundOptions.metadata,
        reasoningEffort: options.reasoningEffort ?? "medium",
        profile: options.profile ?? "normal",
      });

      finalUsage = round.usage ?? finalUsage;
      finishReason = round.finishReason;
      if (round.content) lastAssistantText = round.content;

      const result = await this.finishAgentRound({
        messages,
        options: roundOptions,
        requestId,
        controlEvents,
        toolCalls,
        toolResults,
        visibleContentParts,
        invalidControlToolAttempts,
        modelToolCalls: round.toolCalls,
        fullTextContent: round.content,
        finishReason,
        finalUsage,
      });
      if (result.done) return result.result;
    }

    return this.maxIterationFallback({
      requestId,
      visibleContentParts,
      lastAssistantText,
      context: options.metadata,
      controlEvents,
      toolCalls,
      toolResults,
      finalUsage,
      maxIterations,
    });
  }

  private async finishAgentRound(params: {
    messages: OpenAI.Chat.ChatCompletionMessageParam[];
    options: AgentRuntimeOptions;
    requestId: string;
    controlEvents: AgentControlEvent[];
    toolCalls: RuntimeToolCallRecord[];
    toolResults: RuntimeToolResultRecord[];
    visibleContentParts: string[];
    invalidControlToolAttempts: Map<string, number>;
    modelToolCalls: ModelToolCall[];
    fullTextContent: string;
    finishReason: string | undefined;
    finalUsage: TokenUsage | undefined;
  }): Promise<{ done: true; result: AgentTurnResult } | { done: false }> {
    const {
      messages,
      options,
      requestId,
      controlEvents,
      toolCalls,
      toolResults,
      visibleContentParts,
      invalidControlToolAttempts,
      modelToolCalls,
      fullTextContent,
      finishReason,
      finalUsage,
    } = params;

    if (modelToolCalls.length === 0) {
      const lastText =
        fullTextContent ||
        "模型未生成可见回复，请重试或缩小请求范围。";
      const visibleContent = aggregateVisibleParts(visibleContentParts, lastText);
      messages.push({ role: "assistant", content: lastText });
      logger.agentRunFinal(requestId, visibleContent, {
        context: options.metadata,
        usage: finalUsage,
        finishReason,
        toolCallCount: toolCalls.length,
        controlEventTypes: controlEvents.map((event) => event.type),
      });
      return {
        done: true,
        result: { visibleContent, controlEvents, toolCalls, toolResults, usage: finalUsage, finishReason },
      };
    }

    if (fullTextContent.trim()) visibleContentParts.push(fullTextContent.trim());

    messages.push({
      role: "assistant",
      content: fullTextContent || "",
      tool_calls: modelToolCalls as unknown as OpenAI.Chat.ChatCompletionMessageToolCall[],
    } as any);

    const results = await this.executeRoundToolCalls({
      modelToolCalls,
      options,
      requestId,
      controlEvents,
      toolCalls,
      toolResults,
      invalidControlToolAttempts,
    });

    const parseErrorResult = results.find((result) => result.parseError);
    if (parseErrorResult) {
      const visibleContent = aggregateVisibleParts(visibleContentParts, parseErrorResult.content);
      logger.agentRunFinal(requestId, visibleContent, {
        context: options.metadata,
        usage: finalUsage,
        finishReason: "tool_parse_error",
        toolCallCount: toolCalls.length,
        controlEventTypes: controlEvents.map((event) => event.type),
      });
      return {
        done: true,
        result: {
          visibleContent,
          controlEvents,
          toolCalls,
          toolResults,
          usage: finalUsage,
          finishReason: "tool_parse_error",
        },
      };
    }

    const fatalResult = results.find((result) => result.fatal);
    if (fatalResult) {
      const visibleContent = aggregateVisibleParts(visibleContentParts, fatalResult.content);
      const fatalFinishReason = fatalResult.unauthorized
        ? "tool_authorization_error"
        : "tool_validation_error";
      logger.warn("AGENT_RUNTIME", "control tool 参数连续失败，提前停止工具循环", {
        requestId,
        result: fatalResult.content,
      });
      logger.agentRunFinal(requestId, visibleContent, {
        context: options.metadata,
        usage: finalUsage,
        finishReason: fatalFinishReason,
        toolCallCount: toolCalls.length,
        controlEventTypes: controlEvents.map((event) => event.type),
      });
      return {
        done: true,
        result: {
          visibleContent,
          controlEvents,
          toolCalls,
          toolResults,
          usage: finalUsage,
          finishReason: fatalFinishReason,
        },
      };
    }

    if (results.some((result) => result.terminal)) {
      const visibleContent = fullTextContent.trim()
        ? aggregateVisibleParts(visibleContentParts, "")
        : buildTerminalControlFallback(controlEvents) || aggregateVisibleParts(visibleContentParts, "");
      logger.info("AGENT_RUNTIME", "terminal control tool 已触发，结束当前 Agent 回合", {
        requestId,
        controlEventTypes: controlEvents.map((event) => event.type),
      });
      logger.agentRunFinal(requestId, visibleContent, {
        context: options.metadata,
        usage: finalUsage,
        finishReason: "terminal_control_event",
        toolCallCount: toolCalls.length,
        controlEventTypes: controlEvents.map((event) => event.type),
      });
      return {
        done: true,
        result: {
          visibleContent,
          controlEvents,
          toolCalls,
          toolResults,
          usage: finalUsage,
          finishReason: "terminal_control_event",
        },
      };
    }

    for (const result of results) {
      messages.push({
        role: "tool",
        tool_call_id: result.id,
        content: compactToolResultForModel(result.toolName, result.content),
      });
    }
    return { done: false };
  }

  private async executeRoundToolCalls(params: {
    modelToolCalls: ModelToolCall[];
    options: AgentRuntimeOptions;
    requestId: string;
    controlEvents: AgentControlEvent[];
    toolCalls: RuntimeToolCallRecord[];
    toolResults: RuntimeToolResultRecord[];
    invalidControlToolAttempts: Map<string, number>;
  }): Promise<AgentRoundToolExecutionResult[]> {
    const {
      modelToolCalls,
      options,
      requestId,
      controlEvents,
      toolCalls,
      toolResults,
      invalidControlToolAttempts,
    } = params;
    const results: AgentRoundToolExecutionResult[] = new Array(modelToolCalls.length);

    for (let index = 0; index < modelToolCalls.length;) {
      if (this.canExecuteToolCallInParallel(modelToolCalls[index], options.tools)) {
        const safeBatch: ModelToolCall[] = [];
        while (
          safeBatch.length < MAX_PARALLEL_SAFE_TOOLS &&
          index + safeBatch.length < modelToolCalls.length &&
          this.canExecuteToolCallInParallel(modelToolCalls[index + safeBatch.length], options.tools)
        ) {
          safeBatch.push(modelToolCalls[index + safeBatch.length]);
        }

        const batchResults = await Promise.all(
          safeBatch.map((tc) => this.executeOneRoundToolCall({
            tc,
            options,
            requestId,
            controlEvents,
            toolCalls,
            toolResults,
            invalidControlToolAttempts,
          }))
        );
        batchResults.forEach((result, offset) => {
          results[index + offset] = result;
        });
        index += safeBatch.length;
        continue;
      }

      results[index] = await this.executeOneRoundToolCall({
        tc: modelToolCalls[index],
        options,
        requestId,
        controlEvents,
        toolCalls,
        toolResults,
        invalidControlToolAttempts,
      });
      if (results[index].terminal) {
        return results.slice(0, index + 1);
      }
      index += 1;
    }

    return results;
  }

  private async executeOneRoundToolCall(params: {
    tc: ModelToolCall;
    options: AgentRuntimeOptions;
    requestId: string;
    controlEvents: AgentControlEvent[];
    toolCalls: RuntimeToolCallRecord[];
    toolResults: RuntimeToolResultRecord[];
    invalidControlToolAttempts: Map<string, number>;
  }): Promise<AgentRoundToolExecutionResult> {
    const startedAt = Date.now();
    const {
      tc,
      options,
      requestId,
      controlEvents,
      toolCalls,
      toolResults,
      invalidControlToolAttempts,
    } = params;
        const toolName = tc.function.name;
        if (!this.isToolExposed(toolName, options.tools)) {
          const result = formatUnauthorizedToolMessage(toolName, options.tools);
          const args = { __unauthorizedTool: true };
          toolCalls.push({
            name: toolName,
            toolKind: CONTROL_TOOL_NAMES.includes(toolName) ? "control" : getTool(toolName)?.toolKind ?? "read",
            args,
            timestamp: Date.now(),
          });
          toolResults.push({ name: toolName, result, timestamp: Date.now() });
          logger.warn("AGENT_RUNTIME", "模型调用了未向当前 Agent 暴露的工具", {
            requestId,
            toolName,
            exposedToolNames: getExposedToolNames(options.tools),
          });
          logger.llmToolCall(requestId, toolName, args, result, {
            context: options.metadata,
            durationMs: Date.now() - startedAt,
          });
          return { id: tc.id, toolName, content: result, fatal: true, unauthorized: true };
        }
        const parsedArgs = parseToolCallArguments(tc.function.arguments || "");
        if (!parsedArgs.success) {
          const result = formatToolArgumentsParseError(toolName, parsedArgs.error);
          const args = {
            __parseError: true,
            rawArgumentsPreview: parsedArgs.error.rawArgumentsPreview,
          };
          toolCalls.push({
            name: toolName,
            toolKind: CONTROL_TOOL_NAMES.includes(toolName) ? "control" : getTool(toolName)?.toolKind ?? "read",
            args,
            timestamp: Date.now(),
          });
          toolResults.push({ name: toolName, result, timestamp: Date.now() });
          logger.warn("AGENT_RUNTIME", "tool arguments JSON 解析失败", {
            requestId,
            toolName,
            rawArgumentsPreview: parsedArgs.error.rawArgumentsPreview,
            parseError: parsedArgs.error.message,
          });
          logger.llmToolCall(requestId, toolName, args, result, {
            context: options.metadata,
            durationMs: Date.now() - startedAt,
          });
          return { id: tc.id, toolName, content: result, fatal: true, parseError: true };
        }
        const args = parsedArgs.args;
        options.onToolCall?.(toolName, args);
        const result = await this.executeTool(
          toolName,
          args,
          options,
          controlEvents,
          toolCalls,
          toolResults,
          invalidControlToolAttempts
        );
        logger.llmToolCall(requestId, toolName, args, result.content, {
          context: options.metadata,
          durationMs: Date.now() - startedAt,
        });
        return { id: tc.id, toolName, content: result.content, fatal: result.fatal, terminal: result.terminal };
  }

  private canExecuteToolCallInParallel(
    tc: ModelToolCall,
    tools: OpenAI.Chat.ChatCompletionTool[]
  ): boolean {
    const toolName = tc.function.name;
    if (!this.isToolExposed(toolName, tools)) return false;
    const toolDef = getTool(toolName);
    return toolDef?.permission.readOnly === true &&
      toolDef.permission.concurrencySafe === true &&
      toolDef.toolKind !== "control";
  }

  private async executeTool(
    toolName: string,
    args: Record<string, unknown>,
    options: AgentRuntimeOptions,
    controlEvents: AgentControlEvent[],
    toolCalls: RuntimeToolCallRecord[],
    toolResults: RuntimeToolResultRecord[],
    invalidControlToolAttempts: Map<string, number>
  ): Promise<ToolExecutionResult> {
    const now = Date.now();
    const toolDef = getTool(toolName);
    const toolKind = CONTROL_TOOL_NAMES.includes(toolName)
      ? "control"
      : toolDef?.toolKind ?? "read";
    toolCalls.push({ name: toolName, toolKind, args, timestamp: now });

    if (toolKind === "control") {
      const parsed = parseControlEventArgsDetailed(toolName, args);
      if (!parsed.success) {
        const attempts = (invalidControlToolAttempts.get(toolName) ?? 0) + 1;
        invalidControlToolAttempts.set(toolName, attempts);
        const fatal = attempts >= MAX_INVALID_CONTROL_TOOL_ATTEMPTS;
        const errorMsg = formatControlToolValidationMessage(
          parsed.error,
          attempts,
          MAX_INVALID_CONTROL_TOOL_ATTEMPTS,
          fatal
        );
        logger.warn("AGENT_RUNTIME", "control tool 参数校验失败", {
          toolName,
          args,
          attempts,
          fatal,
          issues: parsed.error.issues,
        });
        toolResults.push({ name: toolName, result: errorMsg, timestamp: Date.now() });
        return { content: errorMsg, fatal };
      }

      invalidControlToolAttempts.delete(toolName);
      controlEvents.push(parsed.event);
      const ack = JSON.stringify({ acknowledged: true, tool: toolName });
      toolResults.push({ name: toolName, result: ack, timestamp: Date.now() });
      logger.info("AGENT_RUNTIME", `control tool "${toolName}" 已拦截`, {
        eventType: parsed.event.type,
      });
      return {
        content: ack,
        terminal: options.terminalControlTools?.includes(toolName) ?? false,
      };
    }

    try {
      const result = await traceTool(
        toolName,
        {
          ...(options.metadata ?? {}),
          toolName,
          toolKind,
        },
        async () => options.toolExecutor(toolName, args)
      );
      toolResults.push({ name: toolName, result, timestamp: Date.now() });
      options.onToolResult?.(toolName, args, result);
      return { content: result };
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : "未知错误";
      const result = `工具执行错误: ${errorMsg}`;
      toolResults.push({ name: toolName, result, timestamp: Date.now() });
      return { content: result };
    }
  }

  private isToolExposed(toolName: string, tools: OpenAI.Chat.ChatCompletionTool[]): boolean {
    return getExposedToolNames(tools).includes(toolName);
  }

  private maxIterationFallback(params: {
    requestId: string;
    visibleContentParts: string[];
    lastAssistantText: string;
    context?: Record<string, unknown>;
    controlEvents: AgentControlEvent[];
    toolCalls: RuntimeToolCallRecord[];
    toolResults: RuntimeToolResultRecord[];
    finalUsage: TokenUsage | undefined;
    maxIterations: number;
  }): AgentTurnResult {
    const fallback = aggregateVisibleParts(
      params.visibleContentParts,
      params.lastAssistantText ||
        "模型在多轮工具查询后仍未产出最终回复，请重试或缩小请求范围。"
    );
    logger.warn("AGENT_RUNTIME", "达到最大工具调用轮次，返回兜底内容", {
      maxIterations: params.maxIterations,
      fallbackLength: fallback.length,
    });
    logger.agentRunFinal(params.requestId, fallback, {
      context: params.context,
      usage: params.finalUsage,
      finishReason: "length",
      toolCallCount: params.toolCalls.length,
      controlEventTypes: params.controlEvents.map((event) => event.type),
    });
    return {
      visibleContent: fallback,
      controlEvents: params.controlEvents,
      toolCalls: params.toolCalls,
      toolResults: params.toolResults,
      usage: params.finalUsage,
      finishReason: "length",
    };
  }

  private resolveRuntime(): ModelRuntimePort {
    if (this.runtime) return this.runtime;
    if (this.injectedClient || this.isConfigured) {
      return new LegacyOpenAIRuntime({
        client: this.injectedClient,
        isAiConfigured: this.isConfigured,
      });
    }
    return getModelRuntime();
  }
}

function compactToolResultForModel(toolName: string, content: string): string {
  const limit = HEAVY_TOOL_RESULT_NAMES.has(toolName)
    ? HEAVY_MODEL_TOOL_RESULT_CHAR_LIMIT
    : DEFAULT_MODEL_TOOL_RESULT_CHAR_LIMIT;
  if (content.length <= limit) return content;

  return [
    content.slice(0, limit),
    "",
    `[工具结果已截断：${toolName} 原始长度 ${content.length} 字符，已回灌前 ${limit} 字符。需要更精确内容时，请用更具体的参数重新查询，不要要求系统一次性返回全文。]`,
  ].join("\n");
}

function buildTerminalControlFallback(controlEvents: AgentControlEvent[]): string {
  const evaluation = [...controlEvents].reverse().find((event) => event.type === "submit_evaluation");
  if (!evaluation || evaluation.type !== "submit_evaluation") return "";
  const lines = [evaluation.summary.trim()];
  if (evaluation.requiredChanges?.trim()) {
    lines.push(evaluation.verdict === "pass" ? "建议：" : "需要修改：");
    lines.push(evaluation.requiredChanges.trim());
  }
  return lines.filter(Boolean).join("\n\n");
}

function formatUnauthorizedToolMessage(
  toolName: string,
  tools: OpenAI.Chat.ChatCompletionTool[]
): string {
  const exposedToolNames = getExposedToolNames(tools);
  return [
    `工具 "${toolName}" 未向当前 Agent 暴露，已停止本轮工具调用。`,
    "",
    "这通常表示当前 Agent 没有执行该职责的权限。不要尝试绕过工具边界。",
    "请改用当前 Agent 已暴露的工具，或在正文中说明职责边界并等待工作流重新分派。",
    "",
    "当前可用工具：",
    exposedToolNames.length > 0 ? exposedToolNames.join(", ") : "(none)",
  ].join("\n");
}

function getExposedToolNames(tools: OpenAI.Chat.ChatCompletionTool[]): string[] {
  return tools
    .filter((tool): tool is OpenAI.Chat.ChatCompletionFunctionTool => tool.type === "function")
    .map((tool) => tool.function.name);
}

function formatToolArgumentsParseError(
  toolName: string,
  error: { message: string; rawArgumentsPreview: string }
): string {
  return [
    `工具 "${toolName}" 参数 JSON 解析失败，已停止本轮工具调用。`,
    "",
    `解析错误：${error.message}`,
    "",
    "Raw arguments preview:",
    "```text",
    error.rawArgumentsPreview || "(empty)",
    "```",
    "",
    "请重新调用该工具，并提供合法 JSON 对象参数。tool arguments 只能放短结构化命令；长正文、长总纲、世界设定、故事背景、章节组梗概、角色长设定或伏笔长说明，请使用对应 block 工具并放在 assistant 正文的 ARTIFACT_OUTPUT_START/END 标记块中。",
  ].join("\n");
}

/**
 * LLM 调用兼容封装。
 *
 * 对外 API 保持不变；普通文本/结构化调用委托 ModelRuntimePort，
 * 历史 tool-call 入口委托 AgentRuntimeImpl，避免绕过统一 Agent loop。
 */

import OpenAI from "openai";
import type { ZodSchema } from "zod";
import { logger } from "@/shared/lib/logger";
import { traceLLMCall } from "@/agents/lib/langsmith-tracer";
import {
  generateMockResponse,
  getModelCallBudget,
  getModelRuntime,
  type LLMCallMetadata,
  type LLMResult,
  type ModelCallProfile,
  type StreamCallback,
} from "@/agents/runtime/model-runtime";

export type { LLMCallMetadata, LLMResult, StreamCallback } from "@/agents/runtime/model-runtime";
export {
  aggregateVisibleParts,
  enqueueTokenUsageRecord,
  recordTokenUsage,
} from "@/agents/runtime/model-runtime";

function buildMessages(
  promptOrOptions: string | { messages: OpenAI.Chat.ChatCompletionMessageParam[] },
  systemPrompt?: string
): { messages: OpenAI.Chat.ChatCompletionMessageParam[]; mockPrompt: string } {
  if (typeof promptOrOptions !== "string") {
    return {
      messages: [...promptOrOptions.messages],
      mockPrompt: "",
    };
  }

  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [];
  if (systemPrompt) {
    messages.push({
      role: "system",
      content: systemPrompt,
    });
  }
  messages.push({ role: "user", content: promptOrOptions });
  return { messages, mockPrompt: promptOrOptions };
}

export async function callLLM(
  promptOrOptions: string | { messages: OpenAI.Chat.ChatCompletionMessageParam[] },
  onChunk?: StreamCallback,
  systemPrompt?: string,
  metadata?: LLMCallMetadata
): Promise<LLMResult> {
  const startTime = Date.now();
  const requestId = logger.generateRequestId();
  const { messages, mockPrompt } = buildMessages(promptOrOptions, systemPrompt);
  logger.llmRequest(requestId, messages, { context: metadata });

  return traceLLMCall(
    metadata?.callType || "通用",
    metadata || {},
    async () => {
      try {
        const result = await getModelRuntime().streamText({
          messages,
          onChunk,
          metadata,
          mockPrompt,
          reasoningEffort: "high",
        });
        logger.llmResponse(requestId, result.content, result.usage, {
          context: metadata,
          durationMs: Date.now() - startTime,
          finishReason: result.finishReason,
        });
        logger.info("LLM", `LLM 调用完成，耗时 ${Date.now() - startTime}ms`, {
          tokens: result.usage?.totalTokens,
          length: result.content.length,
        });
        return result;
      } catch (error) {
        logger.llmError(requestId, error, metadata);
        throw error;
      }
    }
  );
}

export async function callLLMSync(
  prompt: string,
  systemPrompt?: string,
  metadata?: LLMCallMetadata
): Promise<LLMResult> {
  const startTime = Date.now();
  const requestId = logger.generateRequestId();
  const { messages } = buildMessages(prompt, systemPrompt);
  logger.llmRequest(requestId, messages, { context: metadata });

  return traceLLMCall(
    metadata?.callType || "通用",
    metadata || {},
    async () => {
      try {
        const result = await getModelRuntime().completeText({
          messages,
          metadata,
          mockPrompt: prompt,
          reasoningEffort: "high",
        });
        logger.llmResponse(requestId, result.content, result.usage, {
          context: metadata,
          durationMs: Date.now() - startTime,
          finishReason: result.finishReason,
        });
        logger.info("LLM", `LLM 调用完成（非流式），耗时 ${Date.now() - startTime}ms`, {
          tokens: result.usage?.totalTokens,
          length: result.content.length,
        });
        return result;
      } catch (error) {
        logger.llmError(requestId, error, metadata);
        throw error;
      }
    }
  );
}

export async function callLLMStructured<TSchema extends ZodSchema>(
  schema: TSchema,
  options: {
    prompt: string;
    systemPrompt?: string;
    metadata?: LLMCallMetadata;
    profile?: ModelCallProfile;
  }
): Promise<{
  data: ReturnType<TSchema["parse"]>;
  usage?: LLMResult["usage"];
}> {
  const requestId = logger.generateRequestId();
  const startTime = Date.now();
  let systemContent = options.systemPrompt ?? "";
  systemContent += "\n\n【重要】你必须只返回一个合法的 JSON 对象，不要包含任何其他文字、注释或 Markdown 标记。";
  const baseMessages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: "system", content: systemContent },
    { role: "user", content: options.prompt },
  ];
  const messages = baseMessages;
  logger.llmRequest(requestId, messages, { context: options.metadata });

  return traceLLMCall(
    options.metadata?.callType || "structured-output",
    options.metadata || {},
    async () => {
      try {
        const result = await getModelRuntime().completeStructured(schema, {
          messages,
          metadata: options.metadata,
          profile: options.profile,
        });
        logger.llmResponse(requestId, JSON.stringify(result.data), result.usage, {
          context: options.metadata,
          durationMs: Date.now() - startTime,
          finishReason: "structured_output",
        });
        logger.info("LLM", "结构化输出成功", {
          requestId,
          profile: options.profile ?? "normal",
          maxOutputTokens: getModelCallBudget(options.profile),
          tokens: result.usage?.totalTokens,
        });
        return result;
      } catch (error) {
        logger.llmError(requestId, error, options.metadata);
        throw error;
      }
    }
  );
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: string;
}

export interface ToolCallResult {
  toolCallId: string;
  output: string;
}

export async function callLLMWithTools(options: {
  messages: OpenAI.Chat.ChatCompletionMessageParam[];
  tools: OpenAI.Chat.ChatCompletionTool[];
  maxIterations?: number;
  toolExecutor: (toolName: string, args: Record<string, unknown>) => Promise<string>;
  onToolCall?: (toolName: string, args: Record<string, unknown>) => void;
  onChunk?: StreamCallback;
  metadata?: LLMCallMetadata;
}): Promise<LLMResult> {
  const meta = options.metadata ?? {};
  return traceLLMCall(
    (meta.callType as string) || "tool-call",
    meta as Record<string, unknown>,
    async () => {
      const { AgentRuntimeImpl } = await import("@/agents/runtime/agent-runtime");
      const result = await new AgentRuntimeImpl().runTurn(options);
      return {
        content: result.visibleContent,
        usage: result.usage,
        finishReason: result.finishReason,
      };
    }
  );
}

export { generateMockResponse };

export function cleanup(): void {
  // no-op
}

/**
 * 统一 LLM runtime port。
 *
 * 业务 Agent 协议仍由本项目控制；这里仅承接模型调用、流式文本、
 * 结构化 JSON 和 tool-call turn 的通用运行时能力。
 */

import OpenAI from "openai";
import { ChatOpenAI } from "@langchain/openai";
import {
  AIMessage,
  HumanMessage,
  SystemMessage,
  ToolMessage,
  type BaseMessage,
  type AIMessageChunk,
} from "@langchain/core/messages";
import { wrapOpenAI } from "langsmith/wrappers";
import type { ZodSchema } from "zod";
import { prisma } from "@/shared/db/prisma";
import { getAiConfig, getLLMRuntimeName, isAiConfigured } from "@/shared/env";
import { enqueueDbWrite } from "@/shared/lib/db-write-queue";
import { logger } from "@/shared/lib/logger";
import type { TokenUsage } from "./turn-result";

export interface LLMResult {
  content: string;
  usage?: TokenUsage;
  finishReason?: string;
}

export interface LLMCallMetadata {
  taskId?: string;
  agentId?: string;
  callType?: string;
  tags?: string[];
  userId?: string;
  novelId?: string;
  [key: string]: unknown;
}

export type StreamCallback = (chunk: string) => void;

export interface AgentRuntimeOptions {
  messages: OpenAI.Chat.ChatCompletionMessageParam[];
  tools: OpenAI.Chat.ChatCompletionTool[];
  toolExecutor: (toolName: string, args: Record<string, unknown>) => Promise<string>;
  maxIterations?: number;
  onChunk?: StreamCallback;
  onToolCall?: (toolName: string, args: Record<string, unknown>) => void;
  metadata?: LLMCallMetadata;
}

export interface ToolCallTurnOptions {
  messages: OpenAI.Chat.ChatCompletionMessageParam[];
  tools: OpenAI.Chat.ChatCompletionTool[];
  onChunk?: StreamCallback;
  metadata?: LLMCallMetadata;
  reasoningEffort?: "medium" | "high";
}

export interface ModelToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
}

export interface ModelToolCallTurnResult {
  content: string;
  reasoningContent: string;
  toolCalls: ModelToolCall[];
  usage?: TokenUsage;
  finishReason?: string;
}

export interface TextRuntimeOptions {
  messages: OpenAI.Chat.ChatCompletionMessageParam[];
  onChunk?: StreamCallback;
  metadata?: LLMCallMetadata;
  mockPrompt?: string;
  reasoningEffort?: "medium" | "high";
}

export interface StructuredRuntimeOptions {
  messages: OpenAI.Chat.ChatCompletionMessageParam[];
  metadata?: LLMCallMetadata;
}

export interface ModelRuntimePort {
  streamText(options: TextRuntimeOptions): Promise<LLMResult>;
  completeText(options: TextRuntimeOptions): Promise<LLMResult>;
  completeStructured<TSchema extends ZodSchema>(
    schema: TSchema,
    options: StructuredRuntimeOptions
  ): Promise<{ data: ReturnType<TSchema["parse"]>; usage?: TokenUsage }>;
  runToolCallTurn(options: ToolCallTurnOptions): Promise<ModelToolCallTurnResult>;
}

interface RuntimeDeps {
  client?: OpenAI;
  isAiConfigured?: () => boolean;
}

const MAX_OUTPUT_TOKENS = 384000;
const REASONING_EFFORT_MARKER = "Reasoning Effort: Absolute maximum";
const REASONING_EFFORT_PROMPT = `Reasoning Effort: Absolute maximum with no shortcuts permitted.
You MUST be very thorough in your thinking and comprehensively decompose the problem to resolve the root cause, rigorously stress-testing your logic against all potential paths, edge cases, and adversarial scenarios.
Explicitly write out your entire deliberation process, documenting every intermediate step, considered alternative, and rejected hypothesis to ensure absolutely no assumption is left unchecked.

`;

export function hasReasoningEffortPrompt(content: string | undefined): boolean {
  return content?.includes(REASONING_EFFORT_MARKER) ?? false;
}

export function ensureReasoningEffortPrompt(
  messages: OpenAI.Chat.ChatCompletionMessageParam[]
): OpenAI.Chat.ChatCompletionMessageParam[] {
  const next = [...messages];
  const hasPrompt = next.some((msg) =>
    msg.role === "system" &&
    typeof msg.content === "string" &&
    hasReasoningEffortPrompt(msg.content)
  );
  if (hasPrompt) return next;

  if (next.length > 0 && next[0].role === "system") {
    const first = next[0];
    next[0] = {
      ...first,
      content: REASONING_EFFORT_PROMPT + (typeof first.content === "string" ? first.content : ""),
    } as OpenAI.Chat.ChatCompletionMessageParam;
  } else {
    next.unshift({ role: "system", content: REASONING_EFFORT_PROMPT });
  }
  return next;
}

export function aggregateVisibleParts(parts: string[], lastText: string): string {
  if (parts.length === 0) return lastText.trim();

  const trimmedLast = lastText.trim();
  if (!trimmedLast) return parts.join("\n\n").trim();

  const exactDuplicate = parts.some((p) => p.trim() === trimmedLast);
  if (exactDuplicate) {
    return parts.join("\n\n").trim();
  }

  if (trimmedLast.length < 100 && trimmedLast.length > 0) {
    const lastLower = trimmedLast.toLowerCase();
    const alreadyCovered = parts.some((p) => p.toLowerCase().includes(lastLower));
    if (alreadyCovered) {
      return parts.join("\n\n").trim();
    }
  }

  return [...parts, trimmedLast].join("\n\n").trim();
}

export function extractCachedTokens(usage: unknown): number {
  if (!usage || typeof usage !== "object") return 0;
  const u = usage as Record<string, unknown>;
  const hit = u.prompt_cache_hit_tokens;
  if (typeof hit === "number" && hit > 0) return hit;
  const promptTokens = u.prompt_tokens;
  const miss = u.prompt_cache_miss_tokens;
  if (typeof promptTokens === "number" && typeof miss === "number") {
    return Math.max(0, promptTokens - miss);
  }
  return 0;
}

export function usageFromLangChain(value: unknown): TokenUsage | undefined {
  if (!value || typeof value !== "object") return undefined;
  const usage = value as Record<string, unknown>;
  const promptTokens = Number(usage.input_tokens ?? usage.prompt_tokens ?? 0);
  const completionTokens = Number(usage.output_tokens ?? usage.completion_tokens ?? 0);
  const totalTokens = Number(usage.total_tokens ?? promptTokens + completionTokens);
  if (promptTokens === 0 && completionTokens === 0 && totalTokens === 0) return undefined;
  return {
    promptTokens,
    completionTokens,
    totalTokens,
  };
}

export interface LangChainStreamAccumulator {
  content: string;
  reasoningContent: string;
  usage?: TokenUsage;
  finishReason?: string;
  toolCallAccumulator: Map<number, { id: string; name: string; arguments: string }>;
}

export function createLangChainStreamAccumulator(): LangChainStreamAccumulator {
  return {
    content: "",
    reasoningContent: "",
    finishReason: "stop",
    toolCallAccumulator: new Map(),
  };
}

export function applyLangChainStreamChunk(
  accumulator: LangChainStreamAccumulator,
  chunk: Partial<AIMessageChunk>,
  onChunk?: StreamCallback
): void {
  const delta = textFromAIContent(chunk.content);
  if (delta) {
    accumulator.content += delta;
    onChunk?.(delta);
  }

  const additional = chunk.additional_kwargs as Record<string, unknown> | undefined;
  if (typeof additional?.reasoning_content === "string") {
    accumulator.reasoningContent += additional.reasoning_content;
  }

  for (const tc of chunk.tool_call_chunks ?? []) {
    const idx = tc.index ?? 0;
    if (!accumulator.toolCallAccumulator.has(idx)) {
      accumulator.toolCallAccumulator.set(idx, { id: "", name: "", arguments: "" });
    }
    const acc = accumulator.toolCallAccumulator.get(idx)!;
    if (tc.id) acc.id += tc.id;
    if (tc.name) acc.name += tc.name;
    if (tc.args) acc.arguments += tc.args;
  }

  accumulator.usage = usageFromLangChain(chunk.usage_metadata) ?? accumulator.usage;
  const metadata = chunk.response_metadata as Record<string, unknown> | undefined;
  if (typeof metadata?.finish_reason === "string") {
    accumulator.finishReason = metadata.finish_reason;
  }
}

export async function recordTokenUsage(params: {
  userId?: string;
  model?: string;
  usage?: TokenUsage;
  agentId?: string;
  novelId?: string;
}): Promise<void> {
  const { userId, model, usage, agentId, novelId } = params;
  if (!userId || !usage || (usage.promptTokens === 0 && usage.completionTokens === 0)) {
    return;
  }

  const config = getAiConfig();
  try {
    await prisma.tokenUsage.create({
      data: {
        userId,
        model: model || config.model,
        promptTokens: usage.promptTokens,
        completionTokens: usage.completionTokens,
        cachedTokens: usage.cachedTokens ?? 0,
        totalTokens: usage.totalTokens,
        agentId: agentId || null,
        novelId: novelId || null,
      },
    });
  } catch (error) {
    logger.warn("TOKEN_USAGE", "记录 token 使用失败", { error: String(error) });
  }
}

export function enqueueTokenUsageRecord(params: {
  userId?: string;
  model?: string;
  usage?: TokenUsage;
  agentId?: string;
  novelId?: string;
}): boolean {
  if (
    !params.userId ||
    !params.usage ||
    (params.usage.promptTokens === 0 && params.usage.completionTokens === 0)
  ) {
    return false;
  }

  return enqueueDbWrite(
    () => recordTokenUsage(params),
    `token_usage:${params.agentId ?? "unknown"}`
  );
}

export function generateMockResponse(prompt: string, _metadata?: LLMCallMetadata): string {
  if (prompt.includes("设定顾问")) {
    return `## 主体回复

根据您提供的信息，我已经分析了当前的设定情况。

### 设定分析

1. **角色设定**：目前有 ${Math.floor(Math.random() * 5) + 1} 个角色定义完整，${Math.floor(Math.random() * 3) + 1} 个角色需要补充背景信息。

2. **地点设定**：主要场景已经建立，建议补充一些次要场景以丰富世界观。

3. **冲突检测**：未发现明显的设定冲突。

### 建议

- 建议为关键角色补充更详细的性格描写
- 某些角色之间的关系可以进一步明确

### 调用建议

如果需要校验文章一致性，可以调用 @校验 进行检查。`;
  }

  if (prompt.includes("剧情顾问")) {
    return `## 主体回复

根据当前大纲和剧情进度，以下是我的分析：

### 剧情进度

- 当前阶段：${["开局", "发展", "高潮", "尾声"][Math.floor(Math.random() * 4)]}
- 已完成节点：${Math.floor(Math.random() * 10) + 1} 个
- 活跃伏笔：${Math.floor(Math.random() * 5) + 1} 个

### 下一步建议

根据当前剧情走向，建议：

1. 推进主要冲突的发展
2. 考虑伏笔的回收时机
3. 保持角色动机的合理性

### 可用指令

- 输入 "@写作" 开始生成正文
- 输入 "@设定" 讨论角色设定
- 输入 "@校验" 检查文章一致性`;
  }

  if (prompt.includes("作家") || prompt.includes("写作")) {
    return `## 主体回复

根据您提供的大纲和设定，我生成了以下正文内容。

（这是 Mock 响应，实际需要配置 AI 才能生成真正的正文）

### 正文内容

夜幕降临，小镇沉浸在一片静谧之中。街道两旁的灯笼散发着昏黄的光芒，将石板路上的影子拉得老长。

主角站在窗前，望着远方的山峦，心中思绪万千。过去的种种经历如潮水般涌来，让他不禁陷入了沉思。

"接下来该怎么办？"他低声自语，声音在空旷的房间里回荡。

### 调用建议

- 需要调用 @校验 检查内容一致性`;
  }

  if (prompt.includes("校验")) {
    return `## 校验结果

### 校验通过

经过检查，未发现明显的设定冲突。

### 冲突详情

（无）

### 建议

内容基本符合设定要求，可以继续使用。`;
  }

  return `## 回复

我已经收到您的请求。

当前系统处于 Mock 模式，需要配置 AI 才能进行实际处理。

请配置 OPENAI_API_KEY 环境变量以启用完整的 AI 功能。`;
}

function createOpenAIClient(): OpenAI {
  const config = getAiConfig();
  return wrapOpenAI(new OpenAI({
    apiKey: config.apiKey,
    baseURL: config.baseUrl,
  }));
}

function createChatModel() {
  const config = getAiConfig();
  return new ChatOpenAI({
    model: config.model,
    apiKey: config.apiKey,
    maxTokens: MAX_OUTPUT_TOKENS,
    streamUsage: true,
    configuration: {
      baseURL: config.baseUrl,
    },
  });
}

function messageContentToString(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && "text" in part) {
        return String((part as { text?: unknown }).text ?? "");
      }
      return "";
    }).join("");
  }
  return "";
}

export function openAIMessageToLangChain(message: OpenAI.Chat.ChatCompletionMessageParam): BaseMessage {
  const content = messageContentToString((message as { content?: unknown }).content);
  if (message.role === "system") return new SystemMessage(content);
  if (message.role === "user") return new HumanMessage(content);
  if (message.role === "tool") {
    return new ToolMessage({
      content,
      tool_call_id: (message as OpenAI.Chat.ChatCompletionToolMessageParam).tool_call_id,
    });
  }
  if (message.role === "assistant") {
    const assistant = message as OpenAI.Chat.ChatCompletionAssistantMessageParam;
    const toolCalls = assistant.tool_calls?.map((tc) => {
      const fn = (tc as OpenAI.Chat.ChatCompletionMessageFunctionToolCall).function;
      let args: Record<string, unknown> = {};
      try {
        args = JSON.parse(fn.arguments || "{}");
      } catch {
        args = {};
      }
      return {
        id: tc.id,
        name: fn.name,
        args,
      };
    });
    return new AIMessage({
      content,
      tool_calls: toolCalls,
      additional_kwargs: {
        reasoning_content: (assistant as unknown as { reasoning_content?: string }).reasoning_content,
      },
    } as never);
  }
  return new HumanMessage(content);
}

export function openAIMessagesToLangChain(messages: OpenAI.Chat.ChatCompletionMessageParam[]): BaseMessage[] {
  return messages.map(openAIMessageToLangChain);
}

function textFromAIContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && "text" in part) {
        return String((part as { text?: unknown }).text ?? "");
      }
      return "";
    }).join("");
  }
  return "";
}

abstract class BaseRuntime implements ModelRuntimePort {
  protected readonly isConfigured: () => boolean;

  protected constructor(deps: RuntimeDeps = {}) {
    this.isConfigured = deps.isAiConfigured ?? isAiConfigured;
  }

  abstract streamText(options: TextRuntimeOptions): Promise<LLMResult>;
  abstract completeText(options: TextRuntimeOptions): Promise<LLMResult>;
  abstract completeStructured<TSchema extends ZodSchema>(
    schema: TSchema,
    options: StructuredRuntimeOptions
  ): Promise<{ data: ReturnType<TSchema["parse"]>; usage?: TokenUsage }>;
  abstract runToolCallTurn(options: ToolCallTurnOptions): Promise<ModelToolCallTurnResult>;

  protected async handleMockText(options: TextRuntimeOptions, streaming: boolean): Promise<LLMResult> {
    const content = generateMockResponse(options.mockPrompt ?? "", options.metadata);
    if (streaming && options.onChunk) {
      for (const char of content.split("")) {
        options.onChunk(char);
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
    }
    return {
      content,
      usage: { promptTokens: 100, completionTokens: 100, totalTokens: 200 },
      finishReason: "stop",
    };
  }

  protected recordUsage(metadata: LLMCallMetadata | undefined, usage: TokenUsage | undefined): void {
    const config = getAiConfig();
    enqueueTokenUsageRecord({
      userId: metadata?.userId,
      model: config.model,
      usage,
      agentId: metadata?.agentId,
      novelId: metadata?.novelId,
    });
  }
}

export class LegacyOpenAIRuntime extends BaseRuntime {
  private readonly injectedClient?: OpenAI;

  constructor(deps: RuntimeDeps = {}) {
    super(deps);
    this.injectedClient = deps.client;
  }

  private getClient(): OpenAI {
    return this.injectedClient ?? createOpenAIClient();
  }

  async streamText(options: TextRuntimeOptions): Promise<LLMResult> {
    const config = getAiConfig();
    if (!this.isConfigured()) {
      return this.handleMockText(options, true);
    }

    const client = this.getClient();
    let fullContent = "";
    let usage: TokenUsage | undefined;
    let finishReason = "stop";
    const response = await client.chat.completions.create({
      model: config.model,
      messages: options.messages,
      stream: true,
      max_tokens: MAX_OUTPUT_TOKENS,
      reasoning_effort: options.reasoningEffort ?? "high",
    } as any);

    for await (const chunk of response as any) {
      const choice = chunk.choices?.[0];
      const delta = choice?.delta?.content ?? "";
      if (delta) {
        fullContent += delta;
        options.onChunk?.(delta);
      }
      if (choice?.finish_reason) finishReason = choice.finish_reason;
      if (chunk.usage) {
        usage = {
          promptTokens: chunk.usage.prompt_tokens ?? 0,
          completionTokens: chunk.usage.completion_tokens ?? 0,
          cachedTokens: extractCachedTokens(chunk.usage),
          totalTokens: chunk.usage.total_tokens ?? 0,
        };
      }
    }

    this.recordUsage(options.metadata, usage);
    return { content: fullContent, usage, finishReason };
  }

  async completeText(options: TextRuntimeOptions): Promise<LLMResult> {
    const config = getAiConfig();
    if (!this.isConfigured()) {
      return this.handleMockText(options, false);
    }

    const response = await this.getClient().chat.completions.create({
      model: config.model,
      messages: options.messages,
      stream: false,
      max_tokens: MAX_OUTPUT_TOKENS,
      reasoning_effort: options.reasoningEffort ?? "high",
    } as any);

    const content = response.choices[0]?.message?.content ?? "";
    const usage = response.usage
      ? {
          promptTokens: response.usage.prompt_tokens,
          completionTokens: response.usage.completion_tokens,
          cachedTokens: extractCachedTokens(response.usage),
          totalTokens: response.usage.total_tokens,
        }
      : undefined;

    this.recordUsage(options.metadata, usage);
    return { content, usage, finishReason: response.choices[0]?.finish_reason };
  }

  async completeStructured<TSchema extends ZodSchema>(
    schema: TSchema,
    options: StructuredRuntimeOptions
  ): Promise<{ data: ReturnType<TSchema["parse"]>; usage?: TokenUsage }> {
    if (!this.isConfigured()) {
      throw new Error("AI 未配置，无法使用结构化输出");
    }

    const config = getAiConfig();
    const messages = [...options.messages];
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const response = await this.getClient().chat.completions.create({
          model: config.model,
          messages,
          stream: false,
          max_tokens: MAX_OUTPUT_TOKENS,
          response_format: { type: "json_object" },
          reasoning_effort: "medium",
        } as any);

        const content = response.choices[0]?.message?.content ?? "";
        const usage = response.usage
          ? {
              promptTokens: response.usage.prompt_tokens,
              completionTokens: response.usage.completion_tokens,
              cachedTokens: extractCachedTokens(response.usage),
              totalTokens: response.usage.total_tokens,
            }
          : undefined;
        let json: unknown;
        try {
          json = JSON.parse(content.trim());
        } catch {
          throw new Error(`LLM 返回的不是合法 JSON: ${content.slice(0, 200)}`);
        }
        const data = schema.parse(json) as ReturnType<TSchema["parse"]>;
        this.recordUsage(options.metadata, usage);
        return { data, usage };
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        logger.warn("LLM", `结构化输出 attempt ${attempt + 1} 失败: ${lastError.message}`);
        if (attempt === 0) {
          messages.push(
            { role: "assistant", content: "（上一次输出格式错误，请返回合法 JSON）" },
            {
              role: "user",
              content: `请重新输出，必须是一个合法的 JSON 对象。上一次的错误: ${lastError.message}`,
            }
          );
        }
      }
    }

    throw new Error(`结构化输出失败（已重试 1 次）: ${lastError?.message || "未知错误"}`);
  }

  async runToolCallTurn(options: ToolCallTurnOptions): Promise<ModelToolCallTurnResult> {
    const config = getAiConfig();
    const requestId = logger.generateRequestId();
    const messages = ensureReasoningEffortPrompt(options.messages);
    const client = this.getClient();

    logger.llmRequest(requestId, messages);

    if (!this.isConfigured()) {
      const content = "（Mock 模式：需要配置 AI 才能使用工具调用功能）";
      logger.warn("MODEL_RUNTIME", "AI 未配置，返回 Mock tool-call turn");
      logger.llmResponse(requestId, content);
      return {
        content,
        reasoningContent: "",
        toolCalls: [],
        usage: { promptTokens: 100, completionTokens: 100, totalTokens: 200 },
        finishReason: "stop",
      };
    }

    logger.info("MODEL_RUNTIME", "执行单轮 OpenAI tool-call turn", {
      runtime: "legacy-openai",
      messageCount: messages.length,
    });

    const stream = await client.chat.completions.create({
      model: config.model,
      messages,
      tools: options.tools,
      tool_choice: "auto",
      stream: true,
      max_tokens: MAX_OUTPUT_TOKENS,
      reasoning_effort: options.reasoningEffort ?? "medium",
    } as any);

    let content = "";
    let reasoningContent = "";
    let finishReason: string | undefined = "stop";
    let usage: TokenUsage | undefined;
    const toolCallAccumulator = new Map<number, { id: string; name: string; arguments: string }>();

    for await (const chunk of stream as any) {
      const choice = chunk.choices?.[0];
      const delta = choice?.delta;
      if (!delta) continue;

      if (delta.content) {
        content += delta.content;
        options.onChunk?.(delta.content);
      }
      if (delta.reasoning_content) reasoningContent += delta.reasoning_content;
      if (delta.tool_calls) {
        for (const tc of delta.tool_calls) {
          const idx = tc.index ?? 0;
          if (!toolCallAccumulator.has(idx)) {
            toolCallAccumulator.set(idx, { id: "", name: "", arguments: "" });
          }
          const acc = toolCallAccumulator.get(idx)!;
          if (tc.id) acc.id = tc.id;
          if (tc.function?.name) acc.name += tc.function.name;
          if (tc.function?.arguments) acc.arguments += tc.function.arguments;
        }
      }
      if (choice?.finish_reason) {
        finishReason = choice.finish_reason;
      }
      if (chunk.usage) {
        usage = {
          promptTokens: chunk.usage.prompt_tokens ?? 0,
          completionTokens: chunk.usage.completion_tokens ?? 0,
          cachedTokens: extractCachedTokens(chunk.usage),
          totalTokens: chunk.usage.total_tokens ?? 0,
        };
      }
    }

    const toolCalls = Array.from(toolCallAccumulator.values()).map((tc, idx) => ({
      id: tc.id || `call_turn_${idx}`,
      type: "function" as const,
      function: { name: tc.name, arguments: tc.arguments },
    }));

    logger.llmResponse(requestId, content || reasoningContent.slice(-500));
    this.recordUsage(options.metadata, usage);
    return {
      content,
      reasoningContent,
      toolCalls,
      usage,
      finishReason,
    };
  }
}

export class LangChainModelRuntime extends LegacyOpenAIRuntime {
  async streamText(options: TextRuntimeOptions): Promise<LLMResult> {
    if (!this.isConfigured()) {
      return this.handleMockText(options, true);
    }

    const model = createChatModel().withConfig({
      reasoning_effort: options.reasoningEffort ?? "high",
      stream_options: { include_usage: true },
    } as any);
    const stream = await model.stream(openAIMessagesToLangChain(options.messages));
    const accumulator = createLangChainStreamAccumulator();

    for await (const chunk of stream as AsyncIterable<AIMessageChunk>) {
      applyLangChainStreamChunk(accumulator, chunk, options.onChunk);
    }

    this.recordUsage(options.metadata, accumulator.usage);
    return {
      content: accumulator.content,
      usage: accumulator.usage,
      finishReason: accumulator.finishReason,
    };
  }

  async completeText(options: TextRuntimeOptions): Promise<LLMResult> {
    if (!this.isConfigured()) {
      return this.handleMockText(options, false);
    }

    const model = createChatModel().withConfig({
      reasoning_effort: options.reasoningEffort ?? "high",
    } as any);
    const message = await model.invoke(openAIMessagesToLangChain(options.messages));
    const content = textFromAIContent(message.content);
    const usage = usageFromLangChain(message.usage_metadata);
    const metadata = message.response_metadata as Record<string, unknown> | undefined;
    const finishReason = typeof metadata?.finish_reason === "string" ? metadata.finish_reason : "stop";
    this.recordUsage(options.metadata, usage);
    return { content, usage, finishReason };
  }

  async completeStructured<TSchema extends ZodSchema>(
    schema: TSchema,
    options: StructuredRuntimeOptions
  ): Promise<{ data: ReturnType<TSchema["parse"]>; usage?: TokenUsage }> {
    if (!this.isConfigured()) {
      throw new Error("AI 未配置，无法使用结构化输出");
    }

    const messages = [...options.messages];
    let lastError: Error | null = null;

    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        const model = createChatModel().withConfig({
          response_format: { type: "json_object" },
          reasoning_effort: "medium",
        } as any);
        const message = await model.invoke(openAIMessagesToLangChain(messages));
        const content = textFromAIContent(message.content);
        const usage = usageFromLangChain(message.usage_metadata);
        let json: unknown;
        try {
          json = JSON.parse(content.trim());
        } catch {
          throw new Error(`LLM 返回的不是合法 JSON: ${content.slice(0, 200)}`);
        }
        const data = schema.parse(json) as ReturnType<TSchema["parse"]>;
        this.recordUsage(options.metadata, usage);
        return { data, usage };
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        logger.warn("LLM", `结构化输出 attempt ${attempt + 1} 失败: ${lastError.message}`);
        if (attempt === 0) {
          messages.push(
            { role: "assistant", content: "（上一次输出格式错误，请返回合法 JSON）" },
            {
              role: "user",
              content: `请重新输出，必须是一个合法的 JSON 对象。上一次的错误: ${lastError.message}`,
            }
          );
        }
      }
    }

    throw new Error(`结构化输出失败（已重试 1 次）: ${lastError?.message || "未知错误"}`);
  }

  async runToolCallTurn(options: ToolCallTurnOptions): Promise<ModelToolCallTurnResult> {
    const requestId = logger.generateRequestId();
    const messages = ensureReasoningEffortPrompt(options.messages);

    logger.llmRequest(requestId, messages);

    if (!this.isConfigured()) {
      return super.runToolCallTurn(options);
    }

    logger.info("MODEL_RUNTIME", "执行单轮 LangChain tool-call turn", {
      runtime: "langchain",
      messageCount: messages.length,
    });

    const model = createChatModel();
    const runnable = options.tools.length > 0
      ? model.bindTools(options.tools as any, {
          tool_choice: "auto",
          reasoning_effort: options.reasoningEffort ?? "medium",
          stream_options: { include_usage: true },
        } as any)
      : model.withConfig({
          reasoning_effort: options.reasoningEffort ?? "medium",
          stream_options: { include_usage: true },
        } as any);
    const stream = await runnable.stream(openAIMessagesToLangChain(messages));
    const accumulator = createLangChainStreamAccumulator();

    for await (const chunk of stream as AsyncIterable<AIMessageChunk>) {
      applyLangChainStreamChunk(accumulator, chunk, options.onChunk);
    }

    const toolCalls = Array.from(accumulator.toolCallAccumulator.values()).map((tc, idx) => ({
      id: tc.id || `call_turn_${idx}`,
      type: "function" as const,
      function: { name: tc.name, arguments: tc.arguments },
    }));

    logger.llmResponse(requestId, accumulator.content || accumulator.reasoningContent.slice(-500));
    this.recordUsage(options.metadata, accumulator.usage);
    return {
      content: accumulator.content,
      reasoningContent: accumulator.reasoningContent,
      toolCalls,
      usage: accumulator.usage,
      finishReason: accumulator.finishReason,
    };
  }
}

let runtimeSingleton: ModelRuntimePort | null = null;

export function getModelRuntime(): ModelRuntimePort {
  if (runtimeSingleton) return runtimeSingleton;

  const runtimeName = getLLMRuntimeName();
  if (runtimeName === "legacy-openai") {
    runtimeSingleton = new LegacyOpenAIRuntime();
    return runtimeSingleton;
  }
  if (runtimeName === "langchain") {
    runtimeSingleton = new LangChainModelRuntime();
    return runtimeSingleton;
  }

  throw new Error(`未知 LLM_RUNTIME: ${runtimeName}`);
}

export function resetModelRuntimeForTests(): void {
  runtimeSingleton = null;
}

"use server";

import OpenAI from "openai";

import { getAiConfig, isAiConfigured } from "@/shared/env";
import { chargeAiUsage, ensureCanStartModelCall } from "@/shared/lib/billing";

type ContinuationLength = "short" | "medium" | "long";

type ContinuationContext = {
  novelName: string;
  chapterTitle: string;
  content: string;
  outlineSummary: string;
  plotProgress: string;
  loreSummary: string;
  referenceSummary: string;
  styleProfile: string;
  length: ContinuationLength;
};

export interface ContinuationCaller {
  userId?: string;
  novelId?: string;
}

function createClient() {
  const config = getAiConfig();

  return new OpenAI({
    apiKey: config.apiKey,
    baseURL: config.baseUrl,
  });
}

function getLengthGuide(length: ContinuationLength) {
  if (length === "short") {
    return "续写约 200 字";
  }

  if (length === "long") {
    return "续写约 1000 字";
  }

  return "续写约 500 字";
}

/**
 * 生成 AI 续写内容
 *
 * @3.1
 *
 * @param context - 续写上下文（小说名、章节、大纲、设定、文风等）
 * @param caller - 调用者信息（用于 token 使用记录）
 * @returns 续写文本。API Key 未配置时返回 Mock 响应。
 */
export async function generateContinuation(
  context: ContinuationContext,
  caller?: ContinuationCaller
) {
  if (!isAiConfigured()) {
    return `【Mock 续写】\n${context.chapterTitle}之后，故事沿着既定冲突继续推进。主角在当前局势中做出更主动的选择，人物关系被进一步拉紧，场景氛围也朝着下一段剧情目标收束。`;
  }

  const client = createClient();
  const { model } = getAiConfig();

  const prompt = [
    `小说名：${context.novelName}`,
    `章节：${context.chapterTitle}`,
    `续写长度：${getLengthGuide(context.length)}`,
    `文风画像：${context.styleProfile || "未提供文风画像，请保持中文小说自然叙事风格。"}`,
    `大纲摘要：${context.outlineSummary || "暂无大纲摘要。"}`,
    `剧情进度：${context.plotProgress || "暂无剧情进度。"}`,
    `相关设定：${context.loreSummary || "暂无命中设定。"}`,
    `参考资料：${context.referenceSummary || "暂无参考资料。"}`,
    "已有正文：",
    context.content.slice(-4000),
    "请直接输出可接在正文后面的续写内容，不要解释，不要分点，不要加标题。",
  ].join("\n\n");

  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    {
      role: "system",
      content:
        "你是一个中文小说续写助手。你必须严格参考提供的设定、剧情进度和文风画像进行续写，避免出现设定冲突。",
    },
    {
      role: "user",
      content: prompt,
    },
  ];

  const { maxOutputTokens } = await ensureCanStartModelCall({
    metadata: {
      userId: caller?.userId,
      model,
      agentId: "Continuation",
      novelId: caller?.novelId,
    },
    messages,
    maxOutputTokens: 384000,
  });

  const response = await client.chat.completions.create({
    model,
    messages,
    max_tokens: maxOutputTokens,
    reasoning_effort: "high",
  } as any);

  if (response.usage) {
    const cachedTokens = (response.usage as any).prompt_cache_hit_tokens ?? 0;
    await chargeAiUsage({
      metadata: {
        userId: caller?.userId,
        model,
        agentId: "Continuation",
        novelId: caller?.novelId,
      },
      usage: {
        promptTokens: response.usage.prompt_tokens,
        completionTokens: response.usage.completion_tokens,
        cachedTokens: typeof cachedTokens === "number" ? cachedTokens : 0,
        totalTokens: response.usage.total_tokens,
      },
    });
  }

  return response.choices[0]?.message?.content ?? "";
}

/**
 * 文风画像生成 Agent（流式版本）
 *
 * @module PortraitAgentStream
 * @description 分析样本文本，从 5 个维度生成作者文风画像，支持实时流式输出
 *
 * ## 功能
 * - 从样本文本中提取作者独特的写作风格特征
 * - 支持 5 个画像维度的独立生成
 * - 流式输出，适合需要实时反馈的 UI 场景
 * - 自动处理超长文本（分层抽样）
 *
 * ## 画像维度
 * 1. creativeMethodology - 创作方法论：作者的叙事策略和创作方法
 * 2. uniqueMarkers - 独特标记：识别度高的写作标识和签名式表达
 * 3. generationStyle - 生成风格：整体风格取向和基调
 * 4. expressionFeatures - 表达特征：句式、用词、修辞等特点
 * 5. styleTraits - 风格特质：风格的核心本质和深层特征
 *
 * ## 使用示例
 * ```ts
 * const agent = await createPortraitAgentStream();
 * const result = await agent.generateSectionStream(
 *   'creativeMethodology',
 *   sampleText,
 *   (chunk) => console.log(chunk)
 * );
 * ```
 *
 * ## 技术细节
 * - 使用 OpenAI 兼容 API（默认 DeepSeek）
 * - 超过 50000 字时自动分层抽样（开头 20% + 中间抽样 60% + 结尾 20%）
 * - 未配置 API Key 时返回 Mock 数据用于测试
 */
import fs from "node:fs/promises";
import path from "node:path";
import OpenAI from "openai";

import { getAiConfig, isAiConfigured } from "@/shared/env";

/** 最大处理字数，超过此值触发分层抽样 */
const MAX_PORTAIT_CHARS = 50000;

/** 分层抽样阈值 */
const SAMPLING_THRESHOLD = 50000;
// 不限制输出长度，让 AI 根据提示词自由生成

/** 画像维度与提示词文件的映射 */
const portraitPromptFiles = {
  creativeMethodology: "创作方法论.md",
  uniqueMarkers: "独特标记.md",
  generationStyle: "生成风格.md",
  expressionFeatures: "表达特征.md",
  styleTraits: "风格特质.md",
} as const;

/** 画像维度 key 类型 */
type PortraitPromptKey = keyof typeof portraitPromptFiles;
/** 提示词映射表类型 */
type PortraitPromptMap = Record<PortraitPromptKey, string>;

/** 导出维度 key 类型供外部使用 */
export type SectionKey = PortraitPromptKey;

/**
 * 标准化段落文本
 * - 统一换行符为 \n
 * - 合并多余空行
 * - 去除首尾空白
 */
function normalizeSectionText(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * 创建 OpenAI 客户端
 * 从环境变量读取 API 配置
 */
function createClient(): OpenAI {
  const config = getAiConfig();
  return new OpenAI({
    apiKey: config.apiKey,
    baseURL: config.baseUrl,
  });
}

/**
 * 分层抽样：从大文本中提取代表性片段
 *
 * @param text - 原始文本
 * @param targetChars - 目标字数（默认 50000）
 * @returns 抽样后的文本，各片段用 "……" 分隔
 *
 * @description 抽样策略：
 * - 开头 20%：保留开篇部分，通常包含风格奠基
 * - 中间 60%：均匀抽样 5 个片段，覆盖全文风格变化
 * - 结尾 20%：保留结尾部分，通常风格趋于稳定
 */
function stratifiedSampling(text: string, targetChars: number = MAX_PORTAIT_CHARS): string {
  if (text.length <= targetChars) {
    return text;
  }

  const totalLength = text.length;
  const startRatio = 0.2;
  const endRatio = 0.2;

  const startLength = Math.floor(targetChars * startRatio);
  const endLength = Math.floor(targetChars * endRatio);
  const middleLength = targetChars - startLength - endLength;

  const startPart = text.slice(0, startLength);
  const endPart = text.slice(-endLength);

  const middleStart = startLength;
  const middleEnd = totalLength - endLength;
  const middleRange = middleEnd - middleStart;

  if (middleRange <= middleLength) {
    const middlePart = text.slice(middleStart, middleEnd);
    return `${startPart}\n\n……\n\n${middlePart}\n\n……\n\n${endPart}`;
  }

  const sampleCount = 5;
  const sampleLength = Math.floor(middleLength / sampleCount);
  const samples: string[] = [];

  for (let i = 0; i < sampleCount; i++) {
    const sampleStart = middleStart + Math.floor((middleRange * i) / sampleCount);
    const sampleEnd = sampleStart + sampleLength;
    samples.push(text.slice(sampleStart, sampleEnd));
  }

  const middlePart = samples.join("\n\n……\n\n");
  return `${startPart}\n\n……\n\n${middlePart}\n\n……\n\n${endPart}`;
}

/**
 * 加载画像提示词
 *
 * @returns 五个维度的提示词内容映射
 * @description 从 prompts/画像/ 目录加载各维度的分析提示词
 */
async function loadPortraitPrompts(): Promise<PortraitPromptMap> {
  const promptsDir = path.join(process.cwd(), "prompts", "画像");

  const promptEntries = await Promise.all(
    Object.entries(portraitPromptFiles).map(async ([key, fileName]) => {
      const filePath = path.join(promptsDir, fileName);
      const content = await fs.readFile(filePath, "utf-8");
      return [key as PortraitPromptKey, content.trim()] as const;
    }),
  );

  return Object.fromEntries(promptEntries) as PortraitPromptMap;
}

/**
 * PortraitAgentStream：文风画像流式生成器
 *
 * @class
 * @description 支持实时流式输出的文风画像生成 Agent
 * 适用于需要逐步展示生成结果的 UI 场景
 *
 * @example
 * ```ts
 * const agent = await createPortraitAgentStream();
 *
 * // 流式生成单个维度
 * await agent.generateSectionStream(
 *   'creativeMethodology',
 *   novelContent,
 *   (chunk) => {
 *     // 实时更新 UI
 *     updateUI(chunk);
 *   }
 * );
 * ```
 */
export class PortraitAgentStream {
  /** OpenAI 客户端实例 */
  private client: OpenAI;
  /** 当前使用的模型 */
  private model: string;
  /** 加载的提示词映射（延迟加载） */
  private prompts: PortraitPromptMap | null = null;

  constructor() {
    this.client = createClient();
    this.model = getAiConfig().model;
  }

  /**
   * 初始化 Agent
   * 加载所有画像维度的提示词文件
   */
  async init(): Promise<void> {
    this.prompts = await loadPortraitPrompts();
  }

  /**
   * 流式生成单个画像维度
   *
   * @param promptKey - 画像维度 key（如 'creativeMethodology'）
   * @param sourceText - 样本文本
   * @param onChunk - 流式输出回调，每次收到新内容时触发
   * @returns 完整生成内容（标准化后）
   */
  async generateSectionStream(
    promptKey: PortraitPromptKey,
    sourceText: string,
    onChunk: (chunk: string) => void,
  ): Promise<string> {
    if (!this.prompts) {
      await this.init();
    }

    const sampledText = stratifiedSampling(sourceText);
    const systemPrompt = this.prompts![promptKey];

    if (!isAiConfigured()) {
      const mockContent = `【Mock】${systemPrompt.split("\n")[0]}\n\n基于以下文本生成的模拟画像内容...`;
      onChunk(mockContent);
      return mockContent;
    }

    // DeepSeek 思考模式参数
    const completionParams = {
      model: this.model,
      messages: [
        { role: "system", content: systemPrompt },
        {
          role: "user",
          content: `请仅基于以下参考资料完成分析，如果证据不足请明确说明，不要编造。\n\n${sampledText}`,
        },
      ],
      stream: true,
      reasoning_effort: "high",
    };
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const stream = await this.client.chat.completions.create(completionParams as any) as any;

    let fullContent = "";

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta?.content || "";
      if (delta) {
        fullContent += delta;
        onChunk(delta);
      }
    }

    return normalizeSectionText(fullContent);
  }
}

/**
 * 创建流式 PortraitAgent 实例
 *
 * @returns 已初始化的 PortraitAgentStream 实例
 * @description 推荐使用此工厂函数创建 Agent，会自动完成初始化
 */
export async function createPortraitAgentStream(): Promise<PortraitAgentStream> {
  const agent = new PortraitAgentStream();
  await agent.init();
  return agent;
}

// 保留原有的非流式版本供其他地方使用
export { PortraitAgent, createPortraitAgent } from "./portrait-agent-legacy";
export type { PortraitResult } from "./portrait-agent-legacy";
/**
 * 文风画像生成 Agent（非流式版本）
 *
 * @module PortraitAgent
 * @description 分析样本文本，从 5 个维度生成作者文风画像，一次性返回完整结果
 *
 * ## 功能
 * - 从样本文本中提取作者独特的写作风格特征
 * - 生成完整的 5 维画像结果
 * - 自动处理超长文本（分层抽样）
 * - 输出 Markdown 格式的画像报告
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
 * const agent = await createPortraitAgent();
 * const result = await agent.generatePortrait(novelContent);
 * const markdown = agent.getPortraitMarkdown(result);
 * ```
 *
 * ## 与流式版的区别
 * - 流式版：逐块输出，适合实时 UI 展示
 * - 非流式版：一次性返回，适合批量处理或后台任务
 * - 非流式版有输出长度限制（每节最多 800 字）
 *
 * ## 技术细节
 * - 使用 OpenAI 兼容 API（默认 DeepSeek）
 * - 超过 50000 字时自动分层抽样
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

/** 每节最大输出字数（非流式版限制） */
const MAX_SECTION_CHARS = 800;

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

/**
 * 画像生成结果
 *
 * @typedef PortraitResult
 * @property creativeMethodology - 创作方法论分析
 * @property uniqueMarkers - 独特标记分析
 * @property generationStyle - 生成风格分析
 * @property expressionFeatures - 表达特征分析
 * @property styleTraits - 风格特质分析
 * @property usedCharCount - 实际使用的字数（抽样后）
 * @property truncated - 是否进行了截断/抽样
 */
export type PortraitResult = {
  creativeMethodology: string;
  uniqueMarkers: string;
  generationStyle: string;
  expressionFeatures: string;
  styleTraits: string;
  usedCharCount: number;
  truncated: boolean;
};

/**
 * 标准化段落文本并限制长度
 * - 统一换行符为 \n
 * - 合并多余空行
 * - 去除首尾空白
 * - 超过 800 字时截断并添加省略号
 */
function normalizeSectionText(text: string): string {
  const normalizedText = text
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (normalizedText.length <= MAX_SECTION_CHARS) {
    return normalizedText;
  }
  return `${normalizedText.slice(0, MAX_SECTION_CHARS).trim()}…`;
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
  const middleRatio = 0.6;

  const startLength = Math.floor(targetChars * startRatio);
  const endLength = Math.floor(targetChars * endRatio);
  const middleLength = targetChars - startLength - endLength;

  // 开头部分
  const startPart = text.slice(0, startLength);

  // 结尾部分
  const endPart = text.slice(-endLength);

  // 中间部分：均匀抽样
  const middleStart = startLength;
  const middleEnd = totalLength - endLength;
  const middleRange = middleEnd - middleStart;

  if (middleRange <= middleLength) {
    // 中间范围不够，直接取全部
    const middlePart = text.slice(middleStart, middleEnd);
    return `${startPart}\n\n……\n\n${middlePart}\n\n……\n\n${endPart}`;
  }

  // 均匀抽样：分成多个片段
  const sampleCount = 5; // 抽样片段数
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
 * 生成单个画像维度
 *
 * @param client - OpenAI 客户端
 * @param model - 模型名称
 * @param systemPrompt - 该维度的系统提示词
 * @param sourceText - 样本文本
 * @returns 生成的画像内容
 */
async function generateSection(
  client: OpenAI,
  model: string,
  systemPrompt: string,
  sourceText: string,
): Promise<string> {
  if (!isAiConfigured()) {
    return `【Mock】${systemPrompt.split("\n")[0]}\n\n基于以下文本生成的模拟画像内容...`;
  }

  const response = await client.chat.completions.create({
    model,
    messages: [
      {
        role: "system",
        content: systemPrompt,
      },
      {
        role: "user",
        content: `请仅基于以下参考资料完成分析，如果证据不足请明确说明，不要编造。输出必须精炼、可验证、中文不超过800字。\n\n${sourceText}`,
      },
    ],
    reasoning_effort: "high",
    // DeepSeek 思考模式参数
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);

  return response.choices[0]?.message?.content?.trim() ?? "";
}

/**
 * 聚合画像结果为 Markdown 格式
 *
 * @param result - 画像生成结果
 * @returns Markdown 格式的画像报告
 */
function buildPortraitMarkdown(result: PortraitResult): string {
  return [
    "# 创作方法论",
    result.creativeMethodology,
    "",
    "# 独特标记",
    result.uniqueMarkers,
    "",
    "# 生成风格",
    result.generationStyle,
    "",
    "# 表达特征",
    result.expressionFeatures,
    "",
    "# 风格特质",
    result.styleTraits,
  ].join("\n");
}

/**
 * PortraitAgent：文风画像生成器（非流式版本）
 *
 * @class
 * @description 一次性生成完整的 5 维画像，适合批量处理或后台任务
 *
 * @example
 * ```ts
 * const agent = await createPortraitAgent();
 * const result = await agent.generatePortrait(novelContent);
 * console.log(agent.getPortraitMarkdown(result));
 * ```
 */
export class PortraitAgent {
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
   * 生成完整画像
   *
   * @param sourceText - 样本文本
   * @returns 包含 5 个维度分析结果的完整画像
   */
  async generatePortrait(sourceText: string): Promise<PortraitResult> {
    if (!this.prompts) {
      await this.init();
    }

    // 分层抽样处理大文本
    const sampledText = stratifiedSampling(sourceText, MAX_PORTAIT_CHARS);
    const truncated = sourceText.length > SAMPLING_THRESHOLD;

    // 生成五个维度
    const creativeMethodology = normalizeSectionText(
      await generateSection(this.client, this.model, this.prompts!.creativeMethodology, sampledText),
    );

    const uniqueMarkers = normalizeSectionText(
      await generateSection(this.client, this.model, this.prompts!.uniqueMarkers, sampledText),
    );

    const generationStyle = normalizeSectionText(
      await generateSection(this.client, this.model, this.prompts!.generationStyle, sampledText),
    );

    const expressionFeatures = normalizeSectionText(
      await generateSection(this.client, this.model, this.prompts!.expressionFeatures, sampledText),
    );

    const styleTraits = normalizeSectionText(
      await generateSection(this.client, this.model, this.prompts!.styleTraits, sampledText),
    );

    return {
      creativeMethodology,
      uniqueMarkers,
      generationStyle,
      expressionFeatures,
      styleTraits,
      usedCharCount: sampledText.length,
      truncated,
    };
  }

  /**
   * 获取画像的 Markdown 格式
   *
   * @param result - 画像生成结果
   * @returns 格式化的 Markdown 文本
   */
  getPortraitMarkdown(result: PortraitResult): string {
    return buildPortraitMarkdown(result);
  }
}

/**
 * 创建 PortraitAgent 实例
 *
 * @returns 已初始化的 PortraitAgent 实例
 * @description 使用此工厂函数创建 Agent，会自动完成初始化
 */
export async function createPortraitAgent(): Promise<PortraitAgent> {
  const agent = new PortraitAgent();
  await agent.init();
  return agent;
}
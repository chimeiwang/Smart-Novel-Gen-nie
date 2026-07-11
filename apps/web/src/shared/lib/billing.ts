import type OpenAI from "openai";

import { prisma } from "@/shared/db/prisma";

export interface BillingTokenUsage {
  promptTokens: number;
  cachedTokens?: number;
  completionTokens: number;
  totalTokens: number;
}

export interface ModelBillingMetadata {
  userId?: string;
  model?: string;
  agentId?: string;
  novelId?: string;
  requestId?: string;
  note?: string;
}

export type CreditLedgerType =
  | "signup_bonus"
  | "manual_recharge"
  | "ai_charge"
  | "ai_refund";

export class BillingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BillingError";
  }
}

export class InsufficientCreditsError extends BillingError {
  constructor(message = "积分不足，请充值后再使用 AI 功能。") {
    super(message);
    this.name = "InsufficientCreditsError";
  }
}

export class MissingBillingUserError extends BillingError {
  constructor(message = "真实 AI 调用需要登录用户用于积分计费。") {
    super(message);
    this.name = "MissingBillingUserError";
  }
}

const ZERO = BigInt(0);
const ONE_MILLION = BigInt(1_000_000);

export const CREDIT_MICROS_PER_CREDIT = BigInt(1_000_000);
export const SIGNUP_BONUS_CREDITS = BigInt(1000);
export const SIGNUP_BONUS_MICROS = SIGNUP_BONUS_CREDITS * CREDIT_MICROS_PER_CREDIT;

export const DEEPSEEK_FLASH_CREDITS_PER_MILLION = {
  input: BigInt(1000),
  cachedInput: BigInt(20),
  output: BigInt(2000),
} as const;

const DEEPSEEK_FLASH_MICROS_PER_TOKEN = {
  input:
    (DEEPSEEK_FLASH_CREDITS_PER_MILLION.input * CREDIT_MICROS_PER_CREDIT) /
    ONE_MILLION,
  cachedInput:
    (DEEPSEEK_FLASH_CREDITS_PER_MILLION.cachedInput * CREDIT_MICROS_PER_CREDIT) /
    ONE_MILLION,
  output:
    (DEEPSEEK_FLASH_CREDITS_PER_MILLION.output * CREDIT_MICROS_PER_CREDIT) /
    ONE_MILLION,
} as const;

const MIN_OUTPUT_TOKEN_BUDGET = 128;

export function creditsToMicros(credits: number | bigint): bigint {
  if (typeof credits === "bigint") return credits * CREDIT_MICROS_PER_CREDIT;
  return BigInt(Math.round(credits * Number(CREDIT_MICROS_PER_CREDIT)));
}

export function formatCreditMicros(value: bigint | number | string): string {
  const micros = typeof value === "bigint" ? value : BigInt(value);
  const negative = micros < ZERO;
  const abs = negative ? -micros : micros;
  const whole = abs / CREDIT_MICROS_PER_CREDIT;
  const fraction = abs % CREDIT_MICROS_PER_CREDIT;
  if (fraction === ZERO) return `${negative ? "-" : ""}${whole.toString()}`;

  const fractionText = fraction.toString().padStart(6, "0").replace(/0+$/, "").slice(0, 3);
  return `${negative ? "-" : ""}${whole.toString()}.${fractionText}`;
}

export function calculateDeepSeekFlashCreditCostMicros(usage: BillingTokenUsage): bigint {
  const promptTokens = BigInt(Math.max(usage.promptTokens, 0));
  const cachedTokens = BigInt(
    Math.min(Math.max(usage.cachedTokens ?? 0, 0), Math.max(usage.promptTokens, 0))
  );
  const uncachedInputTokens = promptTokens - cachedTokens;
  const completionTokens = BigInt(Math.max(usage.completionTokens, 0));

  return (
    uncachedInputTokens * DEEPSEEK_FLASH_MICROS_PER_TOKEN.input +
    cachedTokens * DEEPSEEK_FLASH_MICROS_PER_TOKEN.cachedInput +
    completionTokens * DEEPSEEK_FLASH_MICROS_PER_TOKEN.output
  );
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

export function estimateTokensFromText(text: string): number {
  const normalized = text.replace(/\s+/g, "");
  return Math.max(1, Math.ceil(normalized.length));
}

export function estimatePromptTokens(
  messages: OpenAI.Chat.ChatCompletionMessageParam[],
  extraPromptText = ""
): number {
  const messageText = messages
    .map((message) => `${message.role}:${messageContentToString((message as { content?: unknown }).content)}`)
    .join("\n");
  return estimateTokensFromText(`${messageText}\n${extraPromptText}`) + messages.length * 8 + 256;
}

export async function getUserCreditBalanceMicros(userId: string): Promise<bigint> {
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { creditBalanceMicros: true },
  });
  return user?.creditBalanceMicros ?? ZERO;
}

export async function grantSignupCredits(userId: string): Promise<void> {
  await prisma.$transaction(async (tx) => {
    const user = await tx.user.update({
      where: { id: userId },
      data: { creditBalanceMicros: { increment: SIGNUP_BONUS_MICROS } },
      select: { creditBalanceMicros: true },
    });

    await tx.creditLedger.create({
      data: {
        userId,
        type: "signup_bonus",
        amountMicros: SIGNUP_BONUS_MICROS,
        balanceAfterMicros: user.creditBalanceMicros,
        note: "注册赠送 1000 积分",
      },
    });
  });
}

export async function ensureCanStartModelCall(input: {
  metadata?: ModelBillingMetadata;
  messages?: OpenAI.Chat.ChatCompletionMessageParam[];
  extraPromptText?: string;
  maxOutputTokens?: number;
}): Promise<{ maxOutputTokens: number }> {
  const userId = input.metadata?.userId;
  if (!userId) throw new MissingBillingUserError();

  const balance = await getUserCreditBalanceMicros(userId);
  if (balance <= ZERO) throw new InsufficientCreditsError();

  const estimatedPromptTokens = input.messages
    ? estimatePromptTokens(input.messages, input.extraPromptText)
    : 0;
  const estimatedPromptCost =
    BigInt(estimatedPromptTokens) * DEEPSEEK_FLASH_MICROS_PER_TOKEN.input;
  const availableForOutput = balance - estimatedPromptCost;
  if (availableForOutput <= ZERO) throw new InsufficientCreditsError();

  const affordableOutputTokens = Number(
    availableForOutput / DEEPSEEK_FLASH_MICROS_PER_TOKEN.output
  );
  if (affordableOutputTokens < MIN_OUTPUT_TOKEN_BUDGET) {
    throw new InsufficientCreditsError();
  }

  return {
    maxOutputTokens: Math.min(input.maxOutputTokens ?? affordableOutputTokens, affordableOutputTokens),
  };
}

export async function chargeAiUsage(input: {
  metadata?: ModelBillingMetadata;
  usage?: BillingTokenUsage;
}): Promise<void> {
  const { metadata, usage } = input;
  const userId = metadata?.userId;
  if (!userId) throw new MissingBillingUserError();
  if (!usage || (usage.promptTokens === 0 && usage.completionTokens === 0)) return;

  const amountMicros = calculateDeepSeekFlashCreditCostMicros(usage);
  if (amountMicros <= ZERO) return;

  await prisma.$transaction(async (tx) => {
    const updated = await tx.user.updateMany({
      where: {
        id: userId,
        creditBalanceMicros: { gte: amountMicros },
      },
      data: {
        creditBalanceMicros: { decrement: amountMicros },
      },
    });

    if (updated.count === 0) {
      throw new InsufficientCreditsError();
    }

    const user = await tx.user.findUniqueOrThrow({
      where: { id: userId },
      select: { creditBalanceMicros: true },
    });

    await tx.creditLedger.create({
      data: {
        userId,
        type: "ai_charge",
        amountMicros: -amountMicros,
        balanceAfterMicros: user.creditBalanceMicros,
        model: metadata?.model ?? null,
        promptTokens: usage.promptTokens,
        completionTokens: usage.completionTokens,
        cachedTokens: usage.cachedTokens ?? 0,
        totalTokens: usage.totalTokens,
        agentId: metadata?.agentId ?? null,
        novelId: metadata?.novelId ?? null,
        requestId: metadata?.requestId ?? null,
        note: metadata?.note ?? null,
      },
    });

    await tx.tokenUsage.create({
      data: {
        userId,
        model: metadata?.model ?? "",
        promptTokens: usage.promptTokens,
        completionTokens: usage.completionTokens,
        cachedTokens: usage.cachedTokens ?? 0,
        totalTokens: usage.totalTokens,
        agentId: metadata?.agentId ?? null,
        novelId: metadata?.novelId ?? null,
      },
    });
  });
}

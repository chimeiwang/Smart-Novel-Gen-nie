export interface TokenUsageBreakdown {
  promptTokens: number;
  cachedTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface TokenCostBreakdown {
  inputYuan: number;
  cachedInputYuan: number;
  outputYuan: number;
  totalYuan: number;
}

const ONE_MILLION = 1_000_000;

export const DEEPSEEK_FLASH_PRICING_CNY_PER_MILLION = {
  input: 1,
  cachedInput: 0.02,
  output: 2,
} as const;

export function normalizeTokenUsageBreakdown(
  usage?: Partial<TokenUsageBreakdown> | null
): TokenUsageBreakdown {
  return {
    promptTokens: usage?.promptTokens ?? 0,
    cachedTokens: usage?.cachedTokens ?? 0,
    completionTokens: usage?.completionTokens ?? 0,
    totalTokens: usage?.totalTokens ?? 0,
  };
}

export function calculateDeepSeekFlashCostCny(
  usage: TokenUsageBreakdown
): TokenCostBreakdown {
  const cachedTokens = Math.min(Math.max(usage.cachedTokens, 0), Math.max(usage.promptTokens, 0));
  const uncachedInputTokens = Math.max(usage.promptTokens - cachedTokens, 0);
  const inputYuan = (uncachedInputTokens / ONE_MILLION) * DEEPSEEK_FLASH_PRICING_CNY_PER_MILLION.input;
  const cachedInputYuan =
    (cachedTokens / ONE_MILLION) * DEEPSEEK_FLASH_PRICING_CNY_PER_MILLION.cachedInput;
  const outputYuan =
    (Math.max(usage.completionTokens, 0) / ONE_MILLION) *
    DEEPSEEK_FLASH_PRICING_CNY_PER_MILLION.output;

  return {
    inputYuan,
    cachedInputYuan,
    outputYuan,
    totalYuan: inputYuan + cachedInputYuan + outputYuan,
  };
}

export function formatTokenCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function formatYuanAmount(amount: number): string {
  if (amount > 0 && amount < 0.01) return `¥${amount.toFixed(4)}`;
  return `¥${amount.toFixed(2)}`;
}

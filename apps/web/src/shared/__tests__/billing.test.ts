import { describe, it } from "node:test";
import assert from "node:assert/strict";

import {
  calculateDeepSeekFlashCreditCostMicros,
  CREDIT_MICROS_PER_CREDIT,
  formatCreditMicros,
  SIGNUP_BONUS_MICROS,
} from "../lib/billing";

describe("billing credit conversion", () => {
  it("uses 1000 credits as the signup bonus", () => {
    assert.equal(SIGNUP_BONUS_MICROS, BigInt(1000) * CREDIT_MICROS_PER_CREDIT);
    assert.equal(formatCreditMicros(SIGNUP_BONUS_MICROS), "1000");
  });

  it("charges DeepSeek v4 flash usage in credits", () => {
    const cost = calculateDeepSeekFlashCreditCostMicros({
      promptTokens: 1_000_000,
      cachedTokens: 100_000,
      completionTokens: 1_000_000,
      totalTokens: 2_000_000,
    });

    // 900k cache-miss input = 900 credits; 100k cache-hit input = 2 credits; output = 2000 credits.
    assert.equal(cost, BigInt(2902) * CREDIT_MICROS_PER_CREDIT);
  });

  it("formats fractional credit balances without exposing token details", () => {
    assert.equal(formatCreditMicros(BigInt(123_456_000)), "123.456");
    assert.equal(formatCreditMicros(BigInt(-2_500_000)), "-2.5");
  });
});

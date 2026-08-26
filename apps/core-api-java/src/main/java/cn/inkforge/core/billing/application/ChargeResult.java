package cn.inkforge.core.billing.application;

/** 原子结算或安全重放后的稳定回执。 */
public record ChargeResult(
        String requestId,
        long chargedMicros,
        long balanceAfterMicros,
        boolean idempotent) {}

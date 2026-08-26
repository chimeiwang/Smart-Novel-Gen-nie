package cn.inkforge.core.billing.domain;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** 当前冻结积分定价；micros 使用 long，禁止浮点金额进入结算。 */
public final class BillingPricing {

    public static final long CREDIT_MICROS_PER_CREDIT = 1_000_000L;
    public static final long UNCACHED_INPUT_MICROS_PER_TOKEN = 1_000L;
    public static final long CACHED_INPUT_MICROS_PER_TOKEN = 20L;
    public static final long OUTPUT_MICROS_PER_TOKEN = 2_000L;
    public static final int MIN_OUTPUT_TOKEN_BUDGET = 128;

    private BillingPricing() {}

    public static long usageCostMicros(
            int promptTokens, int cachedTokens, int completionTokens) {
        long prompt = Math.max(promptTokens, 0);
        long cached = Math.min(Math.max(cachedTokens, 0), prompt);
        long completion = Math.max(completionTokens, 0);
        return (prompt - cached) * UNCACHED_INPUT_MICROS_PER_TOKEN
                + cached * CACHED_INPUT_MICROS_PER_TOKEN
                + completion * OUTPUT_MICROS_PER_TOKEN;
    }

    public static String formatCreditMicros(long value) {
        boolean negative = value < 0;
        long absolute = Math.abs(value);
        long whole = absolute / CREDIT_MICROS_PER_CREDIT;
        long fraction = absolute % CREDIT_MICROS_PER_CREDIT;
        String prefix = negative ? "-" : "";
        if (fraction == 0) {
            return prefix + whole;
        }
        String fractionText = "%06d".formatted(fraction).replaceFirst("0+$", "");
        if (fractionText.length() > 3) {
            fractionText = fractionText.substring(0, 3);
        }
        return prefix + whole + "." + fractionText;
    }

    public static String videoRequestPrefix(String taskId) {
        return "video-task-" + sha256(taskId).substring(0, 32) + "-";
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }
}

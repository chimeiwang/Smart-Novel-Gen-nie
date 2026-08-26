package cn.inkforge.core.billing.application;

public record UsageSnapshot(
        int promptTokens, int cachedTokens, int completionTokens, int totalTokens) {
    public static final UsageSnapshot ZERO = new UsageSnapshot(0, 0, 0, 0);
}

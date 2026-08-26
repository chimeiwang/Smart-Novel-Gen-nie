package cn.inkforge.core.billing.application;

import java.time.OffsetDateTime;

public record TaskUsageCallSnapshot(
        String requestId,
        String runId,
        String agentId,
        String model,
        int promptTokens,
        int cachedTokens,
        Integer promptCacheMissTokens,
        int completionTokens,
        Integer reasoningTokens,
        int totalTokens,
        OffsetDateTime createdAt) {}

package cn.inkforge.core.billing.application;

/** grant 校验后交给 PostgreSQL 原子结算的完整用量身份。 */
public record ChargeUsage(
        String requestId,
        String userId,
        String novelId,
        String taskId,
        String runId,
        String model,
        String agentId,
        int promptTokens,
        int cachedTokens,
        int completionTokens,
        int totalTokens,
        Integer promptCacheMissTokens,
        Integer reasoningTokens) {}

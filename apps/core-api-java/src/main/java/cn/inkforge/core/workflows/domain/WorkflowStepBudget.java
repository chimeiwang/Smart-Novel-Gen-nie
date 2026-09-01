package cn.inkforge.core.workflows.domain;

import java.util.Objects;

/** Run 创建时冻结的单 Step 硬预算；执行途中不能由 Provider 或 Agent 放宽。 */
public record WorkflowStepBudget(
        int maxModelCalls,
        long maxInputTokens,
        long maxPromptCacheMissTokens,
        long maxCompletionTokens,
        long maxReasoningTokens,
        long maxVisibleOutputTokens,
        long maxCostMicros,
        long maxWallClockSeconds,
        int maxProviderRetries,
        int maxProtocolCorrections) {

    public WorkflowStepBudget {
        if (maxModelCalls != 1) {
            throw new IllegalArgumentException("一个 WorkflowStep 必须且只能包含一次主模型调用");
        }
        if (maxInputTokens < 1
                || maxInputTokens > 10_000_000
                || maxPromptCacheMissTokens < 1
                || maxPromptCacheMissTokens > 10_000_000
                || maxWallClockSeconds < 1
                || maxWallClockSeconds > 86_400) {
            throw new IllegalArgumentException("输入和墙钟预算必须为正数");
        }
        if (maxCompletionTokens < 0
                || maxCompletionTokens > 10_000_000
                || maxReasoningTokens < 0
                || maxReasoningTokens > 10_000_000
                || maxVisibleOutputTokens < 0
                || maxVisibleOutputTokens > 10_000_000
                || maxCostMicros < 0
                || maxCostMicros > 1_000_000_000) {
            throw new IllegalArgumentException("缓存、reasoning、可见输出与金额预算不能为负数");
        }
        if (maxPromptCacheMissTokens > maxInputTokens) {
            throw new IllegalArgumentException("cache miss 预算不能超过完整输入预算");
        }
        if (Math.addExact(maxReasoningTokens, maxVisibleOutputTokens)
                > maxCompletionTokens) {
            throw new IllegalArgumentException("reasoning 与可见输出预算之和不能超过 completion 预算");
        }
        if (maxProviderRetries < 0 || maxProviderRetries > 2) {
            throw new IllegalArgumentException("供应商重试预算只允许 0..2");
        }
        if (maxProtocolCorrections < 0 || maxProtocolCorrections > 1) {
            throw new IllegalArgumentException("协议纠正预算只允许 0..1");
        }
    }

    public WorkflowStepUsage requireWithin(WorkflowStepUsage usage) {
        Objects.requireNonNull(usage, "步骤用量不能为空");
        if (usage.inputTokens() != null && usage.inputTokens() > maxInputTokens) {
            throw exceeded(WorkflowBudgetDimension.INPUT_TOKENS);
        }
        if (usage.promptCacheMissTokens() != null
                && usage.promptCacheMissTokens() > maxPromptCacheMissTokens) {
            throw exceeded(WorkflowBudgetDimension.PROMPT_CACHE_MISS_TOKENS);
        }
        if (usage.completionTokens() != null
                && usage.completionTokens() > maxCompletionTokens) {
            throw exceeded(WorkflowBudgetDimension.COMPLETION_TOKENS);
        }
        if (usage.reasoningTokens() != null
                && usage.reasoningTokens() > maxReasoningTokens) {
            throw exceeded(WorkflowBudgetDimension.REASONING_TOKENS);
        }
        if (usage.visibleOutputTokens() != null
                && usage.visibleOutputTokens() > maxVisibleOutputTokens) {
            throw exceeded(WorkflowBudgetDimension.VISIBLE_OUTPUT_TOKENS);
        }
        if (usage.costMicros() != null && usage.costMicros() > maxCostMicros) {
            throw exceeded(WorkflowBudgetDimension.COST_MICROS);
        }
        if (usage.providerAttempts() > maxProviderRetries + 1) {
            throw exceeded(WorkflowBudgetDimension.PROVIDER_ATTEMPTS);
        }
        if (usage.protocolCorrections() > maxProtocolCorrections) {
            throw exceeded(WorkflowBudgetDimension.PROTOCOL_CORRECTIONS);
        }
        if (usage.wallTimeMillis() > Math.multiplyExact(maxWallClockSeconds, 1_000L)) {
            throw exceeded(WorkflowBudgetDimension.WALL_TIME);
        }
        return usage;
    }

    private static WorkflowBudgetExceededException exceeded(
            WorkflowBudgetDimension dimension) {
        return new WorkflowBudgetExceededException(dimension);
    }
}

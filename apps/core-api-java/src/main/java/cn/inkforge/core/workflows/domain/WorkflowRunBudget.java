package cn.inkforge.core.workflows.domain;

import java.util.Collection;
import java.util.Objects;

/** Run 创建时冻结的累计硬预算；并行 Step 必须在同一 Run 锁内合并核算。 */
public record WorkflowRunBudget(
        int maxModelCalls,
        long maxInputTokens,
        long maxPromptCacheMissTokens,
        long maxCompletionTokens,
        long maxReasoningTokens,
        long maxVisibleOutputTokens,
        long maxCostMicros,
        long maxWallClockSeconds,
        int maxProviderRetriesPerStep,
        int maxProtocolCorrectionSteps) {

    public WorkflowRunBudget {
        if (maxModelCalls < 1
                || maxModelCalls > 64
                || maxInputTokens < 1
                || maxInputTokens > 10_000_000
                || maxPromptCacheMissTokens < 1
                || maxPromptCacheMissTokens > 10_000_000
                || maxWallClockSeconds < 1
                || maxWallClockSeconds > 86_400) {
            throw new IllegalArgumentException("Run 模型调用、输入和墙钟预算必须为正数");
        }
        if (maxCompletionTokens < 0
                || maxCompletionTokens > 10_000_000
                || maxReasoningTokens < 0
                || maxReasoningTokens > 10_000_000
                || maxVisibleOutputTokens < 0
                || maxVisibleOutputTokens > 10_000_000
                || maxCostMicros < 0
                || maxCostMicros > 1_000_000_000
                || maxProviderRetriesPerStep < 0
                || maxProviderRetriesPerStep > 2
                || maxProtocolCorrectionSteps < 0
                || maxProtocolCorrectionSteps > 1) {
            throw new IllegalArgumentException("Run 预算不能为负数或无界");
        }
        if (maxPromptCacheMissTokens > maxInputTokens
                || Math.addExact(maxReasoningTokens, maxVisibleOutputTokens)
                        > maxCompletionTokens) {
            throw new IllegalArgumentException("Run token 预算内部不一致");
        }
    }

    public WorkflowRunBudgetCharge requireWithin(
            Collection<WorkflowRunBudgetCharge> charges) {
        Objects.requireNonNull(charges, "Run 预算占用集合不能为空");
        WorkflowRunBudgetCharge total = WorkflowRunBudgetCharge.zero();
        for (WorkflowRunBudgetCharge charge : charges) {
            total = total.plus(Objects.requireNonNull(charge));
        }
        return requireWithin(total);
    }

    public WorkflowRunBudgetCharge requireWithin(WorkflowRunBudgetCharge charge) {
        Objects.requireNonNull(charge, "Run 预算占用不能为空");
        if (charge.modelCalls() > maxModelCalls) {
            throw exceeded(WorkflowBudgetDimension.MODEL_CALLS);
        }
        if (charge.inputTokens() > maxInputTokens) {
            throw exceeded(WorkflowBudgetDimension.INPUT_TOKENS);
        }
        if (charge.promptCacheMissTokens() > maxPromptCacheMissTokens) {
            throw exceeded(WorkflowBudgetDimension.PROMPT_CACHE_MISS_TOKENS);
        }
        if (charge.completionTokens() > maxCompletionTokens) {
            throw exceeded(WorkflowBudgetDimension.COMPLETION_TOKENS);
        }
        if (charge.reasoningTokens() > maxReasoningTokens) {
            throw exceeded(WorkflowBudgetDimension.REASONING_TOKENS);
        }
        if (charge.visibleOutputTokens() > maxVisibleOutputTokens) {
            throw exceeded(WorkflowBudgetDimension.VISIBLE_OUTPUT_TOKENS);
        }
        if (charge.costMicros() > maxCostMicros) {
            throw exceeded(WorkflowBudgetDimension.COST_MICROS);
        }
        if (charge.wallTimeMillis() > Math.multiplyExact(maxWallClockSeconds, 1_000L)) {
            throw exceeded(WorkflowBudgetDimension.WALL_TIME);
        }
        if (charge.protocolCorrectionSteps() > maxProtocolCorrectionSteps) {
            throw exceeded(WorkflowBudgetDimension.PROTOCOL_CORRECTIONS);
        }
        return charge;
    }

    public WorkflowStepBudget requireStepFits(WorkflowStepBudget step) {
        Objects.requireNonNull(step, "Step 预算不能为空");
        if (step.maxProviderRetries() > maxProviderRetriesPerStep) {
            throw exceeded(WorkflowBudgetDimension.PROVIDER_ATTEMPTS);
        }
        requireWithin(WorkflowRunBudgetCharge.active(step));
        return step;
    }

    private static WorkflowBudgetExceededException exceeded(
            WorkflowBudgetDimension dimension) {
        return new WorkflowBudgetExceededException(dimension);
    }
}

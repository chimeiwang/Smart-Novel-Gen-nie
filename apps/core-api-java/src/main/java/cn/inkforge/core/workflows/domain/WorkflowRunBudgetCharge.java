package cn.inkforge.core.workflows.domain;

import java.util.Objects;

/** Run 预算核算使用的保守占用；未知供应商事实按该 Step 已授权上限计入。 */
public record WorkflowRunBudgetCharge(
        int modelCalls,
        long inputTokens,
        long promptCacheMissTokens,
        long completionTokens,
        long reasoningTokens,
        long visibleOutputTokens,
        long costMicros,
        long wallTimeMillis,
        int protocolCorrectionSteps) {

    public WorkflowRunBudgetCharge {
        if (modelCalls < 0
                || inputTokens < 0
                || promptCacheMissTokens < 0
                || completionTokens < 0
                || reasoningTokens < 0
                || visibleOutputTokens < 0
                || costMicros < 0
                || wallTimeMillis < 0
                || protocolCorrectionSteps < 0) {
            throw new IllegalArgumentException("Run 预算占用不能为负数");
        }
    }

    public static WorkflowRunBudgetCharge active(WorkflowStepBudget budget) {
        return active(budget, false);
    }

    public static WorkflowRunBudgetCharge active(
            WorkflowStepBudget budget, boolean protocolCorrectionStep) {
        Objects.requireNonNull(budget, "Step 预算不能为空");
        return new WorkflowRunBudgetCharge(
                1,
                budget.maxInputTokens(),
                budget.maxPromptCacheMissTokens(),
                budget.maxCompletionTokens(),
                budget.maxReasoningTokens(),
                budget.maxVisibleOutputTokens(),
                budget.maxCostMicros(),
                Math.multiplyExact(budget.maxWallClockSeconds(), 1_000L),
                protocolCorrectionStep ? 1 : 0);
    }

    public static WorkflowRunBudgetCharge terminal(
            WorkflowStepBudget budget, WorkflowStepUsage usage) {
        return terminal(budget, usage, false);
    }

    public static WorkflowRunBudgetCharge terminal(
            WorkflowStepBudget budget,
            WorkflowStepUsage usage,
            boolean protocolCorrectionStep) {
        // 预算是调用前授权边界；供应商已经产生的真实超额用量仍必须进入 Run 事实，
        // 再由 Run 预算/终报策略收敛，不能在这里丢弃而让 callback 永久重试。
        Objects.requireNonNull(budget, "Step 预算不能为空");
        Objects.requireNonNull(usage, "Step 用量不能为空");
        return new WorkflowRunBudgetCharge(
                1,
                knownOrReserved(usage.inputTokens(), budget.maxInputTokens()),
                knownOrReserved(
                        usage.promptCacheMissTokens(),
                        budget.maxPromptCacheMissTokens()),
                knownOrReserved(
                        usage.completionTokens(),
                        budget.maxCompletionTokens()),
                knownOrReserved(usage.reasoningTokens(), budget.maxReasoningTokens()),
                knownOrReserved(
                        usage.visibleOutputTokens(),
                        budget.maxVisibleOutputTokens()),
                knownOrReserved(usage.costMicros(), budget.maxCostMicros()),
                usage.wallTimeMillis(),
                protocolCorrectionStep ? 1 : 0);
    }

    public WorkflowRunBudgetCharge plus(WorkflowRunBudgetCharge other) {
        Objects.requireNonNull(other, "Run 预算占用不能为空");
        return new WorkflowRunBudgetCharge(
                Math.addExact(modelCalls, other.modelCalls),
                Math.addExact(inputTokens, other.inputTokens),
                Math.addExact(promptCacheMissTokens, other.promptCacheMissTokens),
                Math.addExact(completionTokens, other.completionTokens),
                Math.addExact(reasoningTokens, other.reasoningTokens),
                Math.addExact(visibleOutputTokens, other.visibleOutputTokens),
                Math.addExact(costMicros, other.costMicros),
                Math.addExact(wallTimeMillis, other.wallTimeMillis),
                Math.addExact(protocolCorrectionSteps, other.protocolCorrectionSteps));
    }

    public static WorkflowRunBudgetCharge zero() {
        return new WorkflowRunBudgetCharge(0, 0, 0, 0, 0, 0, 0, 0, 0);
    }

    private static long knownOrReserved(Long known, long reserved) {
        return known == null ? reserved : known;
    }
}

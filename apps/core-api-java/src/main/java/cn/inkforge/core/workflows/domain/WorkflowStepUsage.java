package cn.inkforge.core.workflows.domain;

import java.util.Objects;

/** Step 已发生的完整用量；reasoning 已包含在 outputTokens 中，不能重复计费。 */
public record WorkflowStepUsage(
        WorkflowUsageStatus usageStatus,
        Long inputTokens,
        Long cachedTokens,
        Long promptCacheMissTokens,
        Long completionTokens,
        Long reasoningTokens,
        Long visibleOutputTokens,
        Long costMicros,
        int providerAttempts,
        int protocolCorrections,
        long wallTimeMillis) {

    public WorkflowStepUsage {
        if (usageStatus == null) throw new IllegalArgumentException("用量状态不能为空");
        if (providerAttempts < 0
                || providerAttempts > 3
                || protocolCorrections < 0
                || protocolCorrections > 1
                || wallTimeMillis < 0) {
            throw new IllegalArgumentException("工作流步骤用量不能为负数");
        }
        Long[] providerFields = {
            inputTokens,
            cachedTokens,
            promptCacheMissTokens,
            completionTokens,
            reasoningTokens,
            visibleOutputTokens,
            costMicros
        };
        int knownCount = 0;
        for (Long value : providerFields) {
            if (value != null) {
                if (value < 0) throw new IllegalArgumentException("工作流步骤用量不能为负数");
                knownCount++;
            }
        }
        if (providerAttempts == 0
                && (usageStatus != WorkflowUsageStatus.UNKNOWN
                        || knownCount != 0
                        || protocolCorrections != 0)) {
            throw new IllegalArgumentException(
                    "零供应商尝试必须使用 unknown usage，且不能携带供应商字段或协议纠正");
        }
        if (usageStatus == WorkflowUsageStatus.COMPLETE && knownCount != providerFields.length) {
            throw new IllegalArgumentException("complete usage 必须包含全部 token 与金额字段");
        }
        if (usageStatus == WorkflowUsageStatus.PARTIAL
                && (knownCount == 0 || knownCount == providerFields.length)) {
            throw new IllegalArgumentException("partial usage 必须且只能包含部分供应商字段");
        }
        if (usageStatus == WorkflowUsageStatus.UNKNOWN && knownCount != 0) {
            throw new IllegalArgumentException("unknown usage 不能伪装供应商字段");
        }
        if (inputTokens != null
                && cachedTokens != null
                && promptCacheMissTokens != null
                && Math.addExact(cachedTokens, promptCacheMissTokens) != inputTokens) {
            throw new IllegalArgumentException("缓存命中与未命中 token 之和必须等于完整输入 token");
        }
        if (completionTokens != null
                && reasoningTokens != null
                && visibleOutputTokens != null
                && Math.addExact(reasoningTokens, visibleOutputTokens) != completionTokens) {
            throw new IllegalArgumentException("reasoning 与可见输出 token 之和必须等于完整 completion token");
        }
    }

    /**
     * 校验当前累计快照没有遗忘、缩小或降级任何已接受事实。
     *
     * <p>Provider 回调可能补齐未知字段，但不能把已知字段重新变成 {@code null}，也不能把累计数值倒退。
     */
    public WorkflowStepUsage requireMonotonicAfter(WorkflowStepUsage previous) {
        Objects.requireNonNull(previous, "上一份用量快照不能为空");
        if (usageRank(usageStatus) < usageRank(previous.usageStatus)) {
            throw new IllegalArgumentException("用量完整性状态不能倒退");
        }
        requireNonDecreasing("inputTokens", previous.inputTokens, inputTokens);
        requireNonDecreasing("cachedTokens", previous.cachedTokens, cachedTokens);
        requireNonDecreasing(
                "promptCacheMissTokens",
                previous.promptCacheMissTokens,
                promptCacheMissTokens);
        requireNonDecreasing("completionTokens", previous.completionTokens, completionTokens);
        requireNonDecreasing("reasoningTokens", previous.reasoningTokens, reasoningTokens);
        requireNonDecreasing(
                "visibleOutputTokens",
                previous.visibleOutputTokens,
                visibleOutputTokens);
        requireNonDecreasing("costMicros", previous.costMicros, costMicros);
        if (providerAttempts < previous.providerAttempts
                || protocolCorrections < previous.protocolCorrections
                || wallTimeMillis < previous.wallTimeMillis) {
            throw new IllegalArgumentException("累计用量计数不能倒退");
        }
        return this;
    }

    private static int usageRank(WorkflowUsageStatus status) {
        return switch (status) {
            case UNKNOWN -> 0;
            case PARTIAL -> 1;
            case COMPLETE -> 2;
        };
    }

    private static void requireNonDecreasing(String field, Long previous, Long current) {
        if (previous != null && (current == null || current < previous)) {
            throw new IllegalArgumentException(field + " 累计事实不能消失或倒退");
        }
    }
}

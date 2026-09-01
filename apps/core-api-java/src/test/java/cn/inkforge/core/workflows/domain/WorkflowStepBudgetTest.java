package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class WorkflowStepBudgetTest {

    private static final WorkflowStepBudget BUDGET = new WorkflowStepBudget(
            1, 20_000, 12_000, 12_000, 4_000, 8_000, 20_000_000, 120, 2, 1);

    @Test
    void 接受预算内用量() {
        WorkflowStepUsage usage = new WorkflowStepUsage(
                WorkflowUsageStatus.COMPLETE,
                19_000L,
                8_000L,
                11_000L,
                10_000L,
                3_000L,
                7_000L,
                18_000_000L,
                3,
                1,
                119_000);

        assertThat(BUDGET.requireWithin(usage)).isSameAs(usage);
    }

    @Test
    void 精确报告越界维度() {
        assertExceeded(
                usage(20_001, 8_000, 12_001, 10_000, 3_000, 7_000, 0, 1, 0, 1),
                WorkflowBudgetDimension.INPUT_TOKENS);
        assertExceeded(
                usage(19_000, 6_999, 12_001, 10_000, 3_000, 7_000, 0, 1, 0, 1),
                WorkflowBudgetDimension.PROMPT_CACHE_MISS_TOKENS);
        assertExceeded(
                usage(1, 0, 1, 12_001, 4_000, 8_001, 0, 1, 0, 1),
                WorkflowBudgetDimension.COMPLETION_TOKENS);
        assertExceeded(
                usage(1, 0, 1, 10_000, 4_001, 5_999, 0, 1, 0, 1),
                WorkflowBudgetDimension.REASONING_TOKENS);
        assertExceeded(
                usage(1, 0, 1, 10_000, 1_999, 8_001, 0, 1, 0, 1),
                WorkflowBudgetDimension.VISIBLE_OUTPUT_TOKENS);
        assertExceeded(
                usage(1, 0, 1, 1, 0, 1, 20_000_001, 1, 0, 1),
                WorkflowBudgetDimension.COST_MICROS);
        assertExceeded(
                usage(1, 0, 1, 1, 0, 1, 0, 1, 0, 120_001),
                WorkflowBudgetDimension.WALL_TIME);
    }

    @Test
    void 供应商重试和协议纠正上限不能被配置为无界() {
        assertThatThrownBy(() -> new WorkflowStepBudget(
                        1, 1, 1, 1, 0, 1, 0, 1, 3, 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("供应商重试");
        assertThatThrownBy(() -> new WorkflowStepBudget(
                        1, 1, 1, 1, 0, 1, 0, 1, 0, 2))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("协议纠正");
    }

    @Test
    void 单步配置可以收紧供应商尝试和协议纠正() {
        WorkflowStepBudget strict = new WorkflowStepBudget(
                1, 10, 10, 10, 0, 10, 100, 10, 0, 0);

        assertThatThrownBy(() -> strict.requireWithin(
                        usage(1, 0, 1, 1, 0, 1, 0, 2, 0, 1)))
                .isInstanceOfSatisfying(
                        WorkflowBudgetExceededException.class,
                        exception -> assertThat(exception.dimension())
                                .isEqualTo(WorkflowBudgetDimension.PROVIDER_ATTEMPTS));
        assertThatThrownBy(() -> strict.requireWithin(
                        usage(1, 0, 1, 1, 0, 1, 0, 1, 1, 1)))
                .isInstanceOfSatisfying(
                        WorkflowBudgetExceededException.class,
                        exception -> assertThat(exception.dimension())
                                .isEqualTo(WorkflowBudgetDimension.PROTOCOL_CORRECTIONS));
    }

    @Test
    void 非生成步骤允许冻结为零输出和零金额() {
        WorkflowStepBudget embedding = new WorkflowStepBudget(
                1, 20_000, 20_000, 0, 0, 0, 0, 60, 2, 0);
        WorkflowStepUsage usage = usage(
                10_000, 0, 10_000, 0, 0, 0, 0, 1, 0, 1_000);

        assertThat(embedding.requireWithin(usage)).isSameAs(usage);
    }

    @Test
    void 取消和断流允许未知字段但不会把未知伪装成零() {
        WorkflowStepUsage unknown = new WorkflowStepUsage(
                WorkflowUsageStatus.UNKNOWN,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                1,
                0,
                1_000);

        assertThat(BUDGET.requireWithin(unknown)).isSameAs(unknown);
        assertThatThrownBy(() -> new WorkflowStepUsage(
                        WorkflowUsageStatus.UNKNOWN,
                        0L,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        1,
                        0,
                        1_000))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("不能伪装");
    }

    @Test
    void 零供应商尝试只能携带完全未知且未经纠正的用量() {
        assertThatThrownBy(() -> new WorkflowStepUsage(
                        WorkflowUsageStatus.COMPLETE,
                        0L,
                        0L,
                        0L,
                        0L,
                        0L,
                        0L,
                        0L,
                        0,
                        0,
                        1L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("零供应商尝试");
        assertThatThrownBy(() -> new WorkflowStepUsage(
                        WorkflowUsageStatus.UNKNOWN,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        0,
                        1,
                        1L))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("零供应商尝试");

        assertThat(new WorkflowStepUsage(
                        WorkflowUsageStatus.UNKNOWN,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        0,
                        0,
                        1L))
                .isNotNull();
    }

    @Test
    void 单步骤不能隐藏多个主模型调用() {
        assertThatThrownBy(() -> new WorkflowStepBudget(
                        2, 1, 1, 1, 0, 1, 0, 1, 0, 0))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("一次主模型调用");
    }

    @Test
    void 累计用量只允许补齐或增加() {
        WorkflowStepUsage unknown = new WorkflowStepUsage(
                WorkflowUsageStatus.UNKNOWN,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                1,
                0,
                1_000);
        WorkflowStepUsage partial = new WorkflowStepUsage(
                WorkflowUsageStatus.PARTIAL,
                100L,
                null,
                null,
                null,
                null,
                null,
                50L,
                2,
                0,
                2_000);
        WorkflowStepUsage complete = usage(
                120, 20, 100, 30, 10, 20, 60, 2, 0, 3_000);

        assertThat(partial.requireMonotonicAfter(unknown)).isSameAs(partial);
        assertThat(complete.requireMonotonicAfter(partial)).isSameAs(complete);
        assertThat(complete.requireMonotonicAfter(complete)).isSameAs(complete);
    }

    @Test
    void 累计用量拒绝状态降级字段消失和计数倒退() {
        WorkflowStepUsage partial = new WorkflowStepUsage(
                WorkflowUsageStatus.PARTIAL,
                100L,
                null,
                null,
                null,
                null,
                null,
                50L,
                2,
                1,
                2_000);
        WorkflowStepUsage regressedState = new WorkflowStepUsage(
                WorkflowUsageStatus.UNKNOWN,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                2,
                1,
                2_000);
        WorkflowStepUsage missingKnownFact = new WorkflowStepUsage(
                WorkflowUsageStatus.PARTIAL,
                null,
                10L,
                null,
                null,
                null,
                null,
                50L,
                2,
                1,
                2_000);
        WorkflowStepUsage regressedCounter = new WorkflowStepUsage(
                WorkflowUsageStatus.PARTIAL,
                100L,
                null,
                null,
                null,
                null,
                null,
                50L,
                1,
                1,
                2_000);

        assertThatThrownBy(() -> regressedState.requireMonotonicAfter(partial))
                .hasMessageContaining("完整性状态");
        assertThatThrownBy(() -> missingKnownFact.requireMonotonicAfter(partial))
                .hasMessageContaining("inputTokens");
        assertThatThrownBy(() -> regressedCounter.requireMonotonicAfter(partial))
                .hasMessageContaining("累计用量计数");
    }

    private static void assertExceeded(
            WorkflowStepUsage usage, WorkflowBudgetDimension dimension) {
        assertThatThrownBy(() -> BUDGET.requireWithin(usage))
                .isInstanceOfSatisfying(
                        WorkflowBudgetExceededException.class,
                        exception -> assertThat(exception.dimension()).isEqualTo(dimension));
    }

    private static WorkflowStepUsage usage(
            long input,
            long cached,
            long cacheMiss,
            long completion,
            long reasoning,
            long visible,
            long cost,
            int providerAttempts,
            int protocolCorrections,
            long wallTime) {
        return new WorkflowStepUsage(
                WorkflowUsageStatus.COMPLETE,
                input,
                cached,
                cacheMiss,
                completion,
                reasoning,
                visible,
                cost,
                providerAttempts,
                protocolCorrections,
                wallTime);
    }
}

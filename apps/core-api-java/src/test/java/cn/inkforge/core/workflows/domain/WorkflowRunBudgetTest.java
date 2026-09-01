package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;

class WorkflowRunBudgetTest {

    private static final WorkflowRunBudget RUN_BUDGET = new WorkflowRunBudget(
            3, 300, 240, 180, 60, 120, 3_000, 300, 2, 1);
    private static final WorkflowStepBudget STEP_BUDGET = new WorkflowStepBudget(
            1, 100, 80, 60, 20, 40, 1_000, 100, 2, 1);

    @Test
    void 并行步骤按完整授权原子保留预算() {
        WorkflowRunBudgetCharge active = WorkflowRunBudgetCharge.active(STEP_BUDGET);

        assertThat(RUN_BUDGET.requireWithin(List.of(active, active, active)).modelCalls())
                .isEqualTo(3);
        assertThatThrownBy(() -> RUN_BUDGET.requireWithin(
                        List.of(active, active, active, active)))
                .isInstanceOfSatisfying(
                        WorkflowBudgetExceededException.class,
                        exception -> assertThat(exception.dimension())
                                .isEqualTo(WorkflowBudgetDimension.MODEL_CALLS));
    }

    @Test
    void 完整终报按实际用量结算并释放剩余额度() {
        WorkflowStepUsage usage = new WorkflowStepUsage(
                WorkflowUsageStatus.COMPLETE,
                60L,
                10L,
                50L,
                30L,
                10L,
                20L,
                500L,
                1,
                0,
                20_000);

        WorkflowRunBudgetCharge settled =
                WorkflowRunBudgetCharge.terminal(STEP_BUDGET, usage);

        assertThat(settled.inputTokens()).isEqualTo(60);
        assertThat(settled.costMicros()).isEqualTo(500);
        assertThat(settled.wallTimeMillis()).isEqualTo(20_000);
    }

    @Test
    void 未知终报对未知维度按授权上限保守计费() {
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
                12_000);

        WorkflowRunBudgetCharge settled =
                WorkflowRunBudgetCharge.terminal(STEP_BUDGET, unknown);

        assertThat(settled.inputTokens()).isEqualTo(STEP_BUDGET.maxInputTokens());
        assertThat(settled.completionTokens()).isEqualTo(STEP_BUDGET.maxCompletionTokens());
        assertThat(settled.costMicros()).isEqualTo(STEP_BUDGET.maxCostMicros());
        assertThat(settled.wallTimeMillis()).isEqualTo(12_000);
    }

    @Test
    void 已发生的超预算终报保留真实用量并由Run预算拒绝后续授权() {
        WorkflowStepUsage exceeded = new WorkflowStepUsage(
                WorkflowUsageStatus.COMPLETE,
                101L,
                10L,
                91L,
                30L,
                10L,
                20L,
                1_001L,
                1,
                0,
                20_000);

        WorkflowRunBudgetCharge charge =
                WorkflowRunBudgetCharge.terminal(STEP_BUDGET, exceeded);

        assertThat(charge.inputTokens()).isEqualTo(101L);
        assertThat(charge.costMicros()).isEqualTo(1_001L);
        WorkflowRunBudget strict = new WorkflowRunBudget(
                1, 100, 100, 100, 50, 50, 1_000, 100, 2, 1);
        assertThatThrownBy(() -> strict.requireWithin(charge))
                .isInstanceOf(WorkflowBudgetExceededException.class);
    }

    @Test
    void 单步重试上限不能超过Run策略() {
        WorkflowStepBudget tooManyRetries = new WorkflowStepBudget(
                1, 100, 80, 60, 20, 40, 1_000, 100, 2, 1);
        WorkflowRunBudget strict = new WorkflowRunBudget(
                3, 300, 240, 180, 60, 120, 3_000, 300, 1, 1);

        assertThatThrownBy(() -> strict.requireStepFits(tooManyRetries))
                .isInstanceOfSatisfying(
                        WorkflowBudgetExceededException.class,
                        exception -> assertThat(exception.dimension())
                                .isEqualTo(WorkflowBudgetDimension.PROVIDER_ATTEMPTS));
    }

    @Test
    void Run只限制显式协议纠正Step而不重复统计各Step的确定性闭合() {
        WorkflowRunBudgetCharge normal = WorkflowRunBudgetCharge.active(STEP_BUDGET);
        WorkflowRunBudgetCharge correction =
                WorkflowRunBudgetCharge.active(STEP_BUDGET, true);

        assertThat(RUN_BUDGET.requireWithin(List.of(normal, correction))
                        .protocolCorrectionSteps())
                .isEqualTo(1);
        assertThatThrownBy(() -> RUN_BUDGET.requireWithin(
                        List.of(correction, correction)))
                .isInstanceOfSatisfying(
                        WorkflowBudgetExceededException.class,
                        exception -> assertThat(exception.dimension())
                                .isEqualTo(WorkflowBudgetDimension.PROTOCOL_CORRECTIONS));
    }
}

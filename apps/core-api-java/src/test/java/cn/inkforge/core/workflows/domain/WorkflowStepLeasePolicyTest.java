package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;

class WorkflowStepLeasePolicyTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 8, 31, 12, 0);

    @Test
    void 只领取未租约或租约已过期的待执行步骤() {
        assertThat(WorkflowStepLeasePolicy.canClaim(
                        WorkflowStepState.PENDING, null, NOW, false))
                .isTrue();
        assertThat(WorkflowStepLeasePolicy.canClaim(
                        WorkflowStepState.PENDING, NOW.minusNanos(1), NOW, false))
                .isTrue();
        assertThat(WorkflowStepLeasePolicy.canClaim(
                        WorkflowStepState.PENDING, NOW.plusSeconds(1), NOW, false))
                .isFalse();
        assertThat(WorkflowStepLeasePolicy.canClaim(
                        WorkflowStepState.RUNNING, NOW.minusMinutes(1), NOW, false))
                .isTrue();
        assertThat(WorkflowStepLeasePolicy.canClaim(
                        WorkflowStepState.RUNNING, NOW.minusMinutes(1), NOW, true))
                .isFalse();
    }

    @Test
    void 每次重新派发都递增防护令牌() {
        assertThat(WorkflowStepLeasePolicy.nextFencingToken(0)).isEqualTo(1);
        assertThat(WorkflowStepLeasePolicy.nextFencingToken(41)).isEqualTo(42);
        assertThatThrownBy(() -> WorkflowStepLeasePolicy.nextFencingToken(Long.MAX_VALUE))
                .isInstanceOf(ArithmeticException.class);
    }

    @Test
    void 旧令牌和错误输入哈希不能提交结果() {
        assertThatThrownBy(() -> WorkflowStepLeasePolicy.requireCurrentResult(
                        8, 7, "expected", "expected", false))
                .isInstanceOf(StaleWorkflowStepResultException.class)
                .hasMessageContaining("fencing");
        assertThatThrownBy(() -> WorkflowStepLeasePolicy.requireCurrentResult(
                        8, 8, "expected", "other", false))
                .isInstanceOf(StaleWorkflowStepResultException.class)
                .hasMessageContaining("输入哈希");
        assertThatThrownBy(() -> WorkflowStepLeasePolicy.requireCurrentResult(
                        8, 8, "expected", "expected", true))
                .isInstanceOf(StaleWorkflowStepResultException.class)
                .hasMessageContaining("取消");
    }

    @Test
    void 当前租约的取消终报即使运行已取消也能提交用量() {
        WorkflowStepLeasePolicy.requireCurrentCancellation(
                8, 8, "expected", "expected", true);

        assertThatThrownBy(() -> WorkflowStepLeasePolicy.requireCurrentCancellation(
                        8, 7, "expected", "expected", true))
                .isInstanceOf(StaleWorkflowStepResultException.class)
                .hasMessageContaining("fencing");
        assertThatThrownBy(() -> WorkflowStepLeasePolicy.requireCurrentCancellation(
                        8, 8, "expected", "expected", false))
                .isInstanceOf(StaleWorkflowStepResultException.class)
                .hasMessageContaining("未请求取消");
    }

    @Test
    void 运行中租约先回放journal再按真实供应商幂等事实分类() {
        assertThat(WorkflowStepLeasePolicy.expiredRunningDisposition(
                        true, true, false, false))
                .isEqualTo(ExpiredRunningDisposition.REPLAY_TERMINAL);
        assertThat(WorkflowStepLeasePolicy.expiredRunningDisposition(
                        false, false, false, false))
                .isEqualTo(ExpiredRunningDisposition.RETRYABLE);
        assertThat(WorkflowStepLeasePolicy.expiredRunningDisposition(
                        false, true, false, false))
                .isEqualTo(ExpiredRunningDisposition.OUTCOME_UNKNOWN);
        assertThat(WorkflowStepLeasePolicy.expiredRunningDisposition(
                        false, true, true, true))
                .isEqualTo(ExpiredRunningDisposition.RETRYABLE);
        assertThat(WorkflowStepLeasePolicy.expiredRunningDisposition(
                        false, true, true, false))
                .isEqualTo(ExpiredRunningDisposition.OUTCOME_UNKNOWN);
    }
}

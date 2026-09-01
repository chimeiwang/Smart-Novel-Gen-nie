package cn.inkforge.core.workflows.domain;

import java.time.LocalDateTime;
import java.util.Objects;

/** Step 派发与结果接收的 fencing 规则；它不把租约状态误当成业务完成状态。 */
public final class WorkflowStepLeasePolicy {

    private WorkflowStepLeasePolicy() {}

    public static boolean canClaim(
            WorkflowStepState state,
            LocalDateTime leaseExpiresAt,
            LocalDateTime now,
            boolean cancelRequested) {
        Objects.requireNonNull(state, "步骤状态不能为空");
        Objects.requireNonNull(now, "当前时间不能为空");
        if (cancelRequested || (leaseExpiresAt != null && leaseExpiresAt.isAfter(now))) {
            return false;
        }
        if (state == WorkflowStepState.PENDING) return true;
        // 这里领取的是 journal 恢复，不等同再次调用 Provider。Agent 先回放已持久终报；只有
        // journal 停在 started 时才依据已冻结的供应商幂等事实决定安全重试或 outcome unknown。
        return state == WorkflowStepState.RUNNING;
    }

    public static long nextFencingToken(long current) {
        if (current < 0) throw new IllegalArgumentException("fencing token 不能为负数");
        return Math.addExact(current, 1L);
    }

    public static void requireCurrentResult(
            long currentFencingToken,
            long submittedFencingToken,
            String expectedInputHash,
            String submittedInputHash,
            boolean cancelRequested) {
        if (currentFencingToken != submittedFencingToken) {
            throw new StaleWorkflowStepResultException("执行结果 fencing token 已过期");
        }
        if (!Objects.equals(expectedInputHash, submittedInputHash)) {
            throw new StaleWorkflowStepResultException("执行结果输入哈希与耐久步骤不一致");
        }
        if (cancelRequested) {
            throw new StaleWorkflowStepResultException("运行已请求取消，迟到结果不能改变业务状态");
        }
    }

    /** 已取消 Run 仍接收当前 lease 的取消终报与 usage，但不能接收普通业务结果。 */
    public static void requireCurrentCancellation(
            long currentFencingToken,
            long submittedFencingToken,
            String expectedInputHash,
            String submittedInputHash,
            boolean cancelRequested) {
        if (currentFencingToken != submittedFencingToken) {
            throw new StaleWorkflowStepResultException("取消终报 fencing token 已过期");
        }
        if (!Objects.equals(expectedInputHash, submittedInputHash)) {
            throw new StaleWorkflowStepResultException("取消终报输入哈希与耐久步骤不一致");
        }
        if (!cancelRequested) {
            throw new StaleWorkflowStepResultException("运行未请求取消，不能提交取消终报");
        }
    }

    public static ExpiredRunningDisposition expiredRunningDisposition(
            boolean journalHasTerminal,
            boolean journalStarted,
            boolean providerSupportsIdempotency,
            boolean providerIdempotencyKeyPersisted) {
        if (journalHasTerminal) return ExpiredRunningDisposition.REPLAY_TERMINAL;
        if (!journalStarted) return ExpiredRunningDisposition.RETRYABLE;
        return providerSupportsIdempotency
                        && providerIdempotencyKeyPersisted
                ? ExpiredRunningDisposition.RETRYABLE
                : ExpiredRunningDisposition.OUTCOME_UNKNOWN;
    }
}

package cn.inkforge.core.workflows.application;

import java.time.Duration;

/** Workflow SSE 共享 observer 的单一超时配置源。 */
public record WorkflowEventObserverTimeouts(
        Duration statementTimeout,
        Duration networkTimeout,
        Duration wallClockTimeout,
        Duration statementCancelGrace,
        Duration connectionAbortGrace,
        Duration shutdownTimeout) {

    public WorkflowEventObserverTimeouts {
        requirePositive(statementTimeout, "statementTimeout");
        requirePositive(networkTimeout, "networkTimeout");
        requirePositive(wallClockTimeout, "wallClockTimeout");
        requirePositive(statementCancelGrace, "statementCancelGrace");
        requirePositive(connectionAbortGrace, "connectionAbortGrace");
        requirePositive(shutdownTimeout, "shutdownTimeout");
        if (statementTimeout.compareTo(networkTimeout) >= 0
                || networkTimeout.compareTo(wallClockTimeout) >= 0
                || statementCancelGrace.plus(connectionAbortGrace).compareTo(shutdownTimeout) >= 0
                || statementTimeout.toMillis() > Integer.MAX_VALUE
                || networkTimeout.toMillis() > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Workflow SSE observer 超时配置无效");
        }
    }

    public static WorkflowEventObserverTimeouts productionDefaults() {
        return new WorkflowEventObserverTimeouts(
                Duration.ofSeconds(2),
                Duration.ofSeconds(3),
                Duration.ofSeconds(4),
                Duration.ofMillis(500),
                Duration.ofSeconds(1),
                Duration.ofSeconds(5));
    }

    public int jdbcQueryTimeoutSeconds() {
        long seconds = Math.floorDiv(statementTimeout.toMillis() + 999L, 1_000L);
        return Math.toIntExact(seconds);
    }

    private static void requirePositive(Duration value, String field) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException("Workflow SSE observer " + field + " 必须大于 0");
        }
    }
}

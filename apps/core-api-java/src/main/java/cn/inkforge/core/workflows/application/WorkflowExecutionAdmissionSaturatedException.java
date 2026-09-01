package cn.inkforge.core.workflows.application;

import java.time.Duration;
import java.util.Objects;

/** Agent 明确证明尚未创建 execution journal；Core 可安全释放当前 lease 后退避重派。 */
public final class WorkflowExecutionAdmissionSaturatedException extends RuntimeException {

    private final Duration retryAfter;

    public WorkflowExecutionAdmissionSaturatedException(Duration retryAfter) {
        super("Agent execution admission 已饱和");
        this.retryAfter = Objects.requireNonNull(retryAfter);
        if (retryAfter.isZero()
                || retryAfter.isNegative()
                || retryAfter.compareTo(Duration.ofSeconds(60)) > 0) {
            throw new IllegalArgumentException("Agent admission 重试时间必须在 1 毫秒到 60 秒之间");
        }
    }

    public Duration retryAfter() {
        return retryAfter;
    }
}

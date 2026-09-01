package cn.inkforge.core.workflows.domain;

/** 运行中租约失联后的确定性处理；无供应商幂等时不能以重试猜测结果。 */
public enum ExpiredRunningDisposition {
    REPLAY_TERMINAL,
    RETRYABLE,
    OUTCOME_UNKNOWN
}

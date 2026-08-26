package cn.inkforge.core.quality.domain;

/** Python Agent 队列对稳定质量任务身份返回的状态。 */
public enum QualityDispatchStatus {
    QUEUED,
    RUNNING,
    COMPLETED,
    FAILED,
    CANCELLED
}

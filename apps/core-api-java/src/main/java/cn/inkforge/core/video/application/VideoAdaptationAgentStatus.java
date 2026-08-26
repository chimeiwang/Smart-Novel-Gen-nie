package cn.inkforge.core.video.application;

/** Agent 队列提交响应中可观察的五种状态。 */
public enum VideoAdaptationAgentStatus {
    QUEUED,
    RUNNING,
    COMPLETED,
    FAILED,
    CANCELLED
}

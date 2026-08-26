package cn.inkforge.core.styles.domain;

/** Agent 接受画像任务后可观察的状态。 */
public enum PortraitDispatchStatus {
    QUEUED,
    RUNNING,
    COMPLETED,
    FAILED,
    CANCELLED
}

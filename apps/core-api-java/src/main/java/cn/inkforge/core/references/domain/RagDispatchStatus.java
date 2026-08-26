package cn.inkforge.core.references.domain;

/** Agent 接受索引任务后可观察的状态。 */
public enum RagDispatchStatus {
    QUEUED,
    RUNNING,
    COMPLETED,
    FAILED,
    CANCELLED
}

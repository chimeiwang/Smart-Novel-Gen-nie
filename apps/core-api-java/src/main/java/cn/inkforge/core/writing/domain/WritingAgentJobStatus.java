package cn.inkforge.core.writing.domain;

/** Python Agent 受理写作 job 后返回的冻结状态集合。 */
public enum WritingAgentJobStatus {
    QUEUED("queued"),
    RUNNING("running"),
    COMPLETED("completed"),
    FAILED("failed"),
    CANCELLED("cancelled");

    private final String value;

    WritingAgentJobStatus(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}

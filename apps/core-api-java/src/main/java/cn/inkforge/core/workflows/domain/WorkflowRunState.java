package cn.inkforge.core.workflows.domain;

import java.util.Arrays;

/** Core 权威工作流运行状态；字符串值与 PostgreSQL 既有枚举一致。 */
public enum WorkflowRunState {
    PENDING("pending"),
    RUNNING("running"),
    WAITING_USER("waiting_user"),
    COMPLETED("completed"),
    FAILED("failed"),
    CANCELLED("cancelled");

    private final String databaseValue;

    WorkflowRunState(String databaseValue) {
        this.databaseValue = databaseValue;
    }

    public String databaseValue() {
        return databaseValue;
    }

    public static WorkflowRunState fromDatabaseValue(String value) {
        return Arrays.stream(values())
                .filter(state -> state.databaseValue.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("未知工作流运行状态：" + value));
    }
}

package cn.inkforge.core.workflows.domain;

import java.util.Arrays;

/** 一次可独立结算和恢复的工作流步骤状态；字符串值与 PostgreSQL 既有枚举一致。 */
public enum WorkflowStepState {
    PENDING("pending"),
    RUNNING("running"),
    COMPLETED("completed"),
    FAILED("failed"),
    SKIPPED("skipped");

    private final String databaseValue;

    WorkflowStepState(String databaseValue) {
        this.databaseValue = databaseValue;
    }

    public String databaseValue() {
        return databaseValue;
    }

    public static WorkflowStepState fromDatabaseValue(String value) {
        return Arrays.stream(values())
                .filter(state -> state.databaseValue.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("未知工作流步骤状态：" + value));
    }
}

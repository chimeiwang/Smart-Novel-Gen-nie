package cn.inkforge.core.workflows.domain;

import java.util.Arrays;

/** 供应商用量事实的完整程度；未知字段绝不以 0 伪装。 */
public enum WorkflowUsageStatus {
    COMPLETE("complete"),
    PARTIAL("partial"),
    UNKNOWN("unknown");

    private final String wireValue;

    WorkflowUsageStatus(String wireValue) {
        this.wireValue = wireValue;
    }

    public String wireValue() {
        return wireValue;
    }

    public static WorkflowUsageStatus fromWireValue(String value) {
        return Arrays.stream(values())
                .filter(status -> status.wireValue.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("未知用量状态：" + value));
    }
}

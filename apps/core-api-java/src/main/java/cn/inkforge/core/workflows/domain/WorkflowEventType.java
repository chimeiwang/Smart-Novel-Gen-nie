package cn.inkforge.core.workflows.domain;

import java.util.Arrays;

/** V2 只发布可由 Core 耐久事实证明的语义事件。 */
public enum WorkflowEventType {
    RUN_ACCEPTED("run_accepted"),
    INTENT_RESOLVED("intent_resolved"),
    CLARIFICATION_REQUIRED("clarification_required"),
    EVIDENCE_READY("evidence_ready"),
    STEP_QUEUED("step_queued"),
    STEP_STARTED("step_started"),
    STEP_PROGRESS("step_progress"),
    STEP_FINISHED("step_finished"),
    CANDIDATE_READY("candidate_ready"),
    REVIEW_STARTED("review_started"),
    REVIEW_COMPLETED("review_completed"),
    AWAITING_USER("awaiting_user"),
    APPLYING("applying"),
    COMPLETED("completed"),
    FAILED("failed"),
    CANCELLED("cancelled");

    private final String wireValue;

    WorkflowEventType(String wireValue) {
        this.wireValue = wireValue;
    }

    public String wireValue() {
        return wireValue;
    }

    public static WorkflowEventType fromWireValue(String value) {
        return Arrays.stream(values())
                .filter(type -> type.wireValue.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("未知 V2 工作流事件：" + value));
    }
}

package cn.inkforge.core.workflows.domain;

/** 迟到、错版本或已取消的执行结果，必须在任何业务副作用前拒绝。 */
public final class StaleWorkflowStepResultException extends IllegalStateException {

    public StaleWorkflowStepResultException(String message) {
        super(message);
    }
}

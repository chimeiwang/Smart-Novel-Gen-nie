package cn.inkforge.core.workflows.domain;

import java.util.Objects;

/** Step 超过冻结预算；调用方必须收敛当前 Step，不能静默扩大额度。 */
public final class WorkflowBudgetExceededException extends IllegalStateException {

    private final WorkflowBudgetDimension dimension;

    public WorkflowBudgetExceededException(WorkflowBudgetDimension dimension) {
        super("工作流步骤超过冻结预算：" + Objects.requireNonNull(dimension));
        this.dimension = dimension;
    }

    public WorkflowBudgetDimension dimension() {
        return dimension;
    }
}

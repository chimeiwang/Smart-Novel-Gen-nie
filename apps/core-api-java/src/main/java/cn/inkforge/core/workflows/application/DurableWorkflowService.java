package cn.inkforge.core.workflows.application;

import java.util.Objects;

/** Core 权威 Workflow 用例；异步派发不属于创建事务。 */
public final class DurableWorkflowService {

    private final WorkflowStartRepository starts;

    public DurableWorkflowService(WorkflowStartRepository starts) {
        this.starts = Objects.requireNonNull(starts);
    }

    public WorkflowRunStartResult startFresh(
            WorkflowStartPlan plan, Runnable finalFreshStartAuthorization) {
        return starts.start(plan, finalFreshStartAuthorization);
    }
}

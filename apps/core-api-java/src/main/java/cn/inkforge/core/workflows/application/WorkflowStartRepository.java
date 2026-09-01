package cn.inkforge.core.workflows.application;

/** Run/Evidence/Step/Event 首次提交的单事务端口。 */
public interface WorkflowStartRepository {
    WorkflowRunStartResult start(WorkflowStartPlan plan);

    default WorkflowRunStartResult start(
            WorkflowStartPlan plan, Runnable finalFreshStartAuthorization) {
        finalFreshStartAuthorization.run();
        return start(plan);
    }
}

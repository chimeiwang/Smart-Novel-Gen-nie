package cn.inkforge.core.workflows.application;

/** V2 未知用量的唯一受支持持久结算端口。 */
public interface WorkflowBillingReconciliationRepository {

    WorkflowBillingReconciliationResult reconcile(
            WorkflowBillingReconciliationCommand command);
}

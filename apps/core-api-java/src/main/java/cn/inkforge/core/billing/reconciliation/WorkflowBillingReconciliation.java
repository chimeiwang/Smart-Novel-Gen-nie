package cn.inkforge.core.billing.reconciliation;

import cn.inkforge.contracts.api.BillingReconciliationReceipt;
import cn.inkforge.contracts.api.BillingReconciliationRequest;

/** Billing 模块暴露给自身 API 的单一受审计对账端口；实现位于 Workflow 模块。 */
@FunctionalInterface
public interface WorkflowBillingReconciliation {

    BillingReconciliationReceipt reconcile(BillingReconciliationRequest request);
}

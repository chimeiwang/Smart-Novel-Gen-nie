package cn.inkforge.core.workflows.application;

import cn.inkforge.core.workflows.domain.WorkflowStepUsage;

/** 已完成共享契约校验并计算 canonical SHA 的计费对账命令。 */
public record WorkflowBillingReconciliationCommand(
        String protocolVersion,
        String reconciliationId,
        String runId,
        String novelId,
        String stepId,
        String reservationRequestId,
        String supplierEvidenceRef,
        String supplierReportSha256,
        String decision,
        WorkflowStepUsage usage,
        String requestSha256) {}

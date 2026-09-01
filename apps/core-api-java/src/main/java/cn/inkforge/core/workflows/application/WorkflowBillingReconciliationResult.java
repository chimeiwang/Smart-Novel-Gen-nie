package cn.inkforge.core.workflows.application;

import java.time.OffsetDateTime;

/** PostgreSQL 同事务结算结果。 */
public record WorkflowBillingReconciliationResult(
        String reconciliationId,
        String reservationRequestId,
        String decision,
        String reservationStatus,
        long chargedMicros,
        long balanceAfterMicros,
        OffsetDateTime settledAt,
        boolean duplicate) {}

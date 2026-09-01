package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationCommand;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationRepository;
import cn.inkforge.core.workflows.application.WorkflowBillingReconciliationResult;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.domain.WorkflowStepUsage;
import cn.inkforge.core.workflows.domain.WorkflowUsageStatus;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import org.jooq.impl.DSL;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** PostgreSQL 14 上按固定锁序完成未知用量对账，不修改任何 Workflow 终态。 */
final class JooqWorkflowBillingReconciliationRepository
        implements WorkflowBillingReconciliationRepository {

    private static final TypeReference<Map<String, Object>> JSON_OBJECT = new TypeReference<>() {};
    private static final List<String> TERMINAL_STEP_STATUSES =
            List.of("completed", "failed", "skipped");
    private static final long RECONCILIATION_LOCK_NAMESPACE = 20_260_901L;

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;
    private final WorkflowBillingCoordinator billing;

    JooqWorkflowBillingReconciliationRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json,
            ExecutionRegistry registry) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
        this.billing = new WorkflowBillingCoordinator(ids, json, registry);
    }

    @Override
    public WorkflowBillingReconciliationResult reconcile(
            WorkflowBillingReconciliationCommand command) {
        Objects.requireNonNull(command);
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LocalDateTime now = DatabaseTimestamp.now(clock);

            // 财务事务的全局锁序固定为 Run → Step → Reservation → User。
            Record run = transaction.fetchOne(
                    """
                    SELECT id, "userId", "novelId", status::text AS status
                    FROM public."WorkflowRun"
                    WHERE id = ? AND "engineVersion" = 2
                    FOR UPDATE
                    """,
                    command.runId());
            if (run == null) throw notFound();
            Record step = transaction.fetchOne(
                    """
                    SELECT id, "runId", status::text AS status, "usageJson", "modelProfile"
                    FROM public."WorkflowStep"
                    WHERE id = ? AND "runId" = ?
                    FOR UPDATE
                    """,
                    command.stepId(),
                    command.runId());
            if (step == null) throw notFound();
            Record reservation = transaction.fetchOne(
                    """
                    SELECT * FROM public."WorkflowBillingReservation"
                    WHERE "stepId" = ? AND "runId" = ?
                    FOR UPDATE
                    """,
                    command.stepId(),
                    command.runId());
            if (reservation == null) {
                throw conflict(
                        "WORKFLOW_BILLING_RECONCILIATION_RESERVATION_MISSING",
                        "Workflow Step 缺少计费预留");
            }
            requireIdentity(command, run, step, reservation);
            if (!TERMINAL_STEP_STATUSES.contains(step.get("status", String.class))) {
                throw conflict(
                        "WORKFLOW_BILLING_RECONCILIATION_STEP_NOT_TERMINAL",
                        "Workflow Step 尚未终结，不能对账");
            }

            // 无新增列时，以稳定 ID 的 advisory lock 串行化跨 reservation 唯一性检查。
            transaction.fetch(
                    "SELECT pg_advisory_xact_lock(hashtextextended(?, ?))",
                    command.reconciliationId(),
                    RECONCILIATION_LOCK_NAMESPACE);
            Record collision = transaction.fetchOne(
                    """
                    SELECT id FROM public."WorkflowBillingReservation"
                    WHERE id <> ?
                      AND "usageJson" IS NOT NULL
                      AND "usageJson"::jsonb #>> '{reconciliation,reconciliationId}' = ?
                    LIMIT 1
                    """,
                    reservation.get("id", String.class),
                    command.reconciliationId());
            if (collision != null) throw driftConflict();

            Record user = transaction.fetchOne(
                    """
                    SELECT id, "creditBalanceMicros"
                    FROM public."User" WHERE id = ? FOR UPDATE
                    """,
                    run.get("userId", String.class));
            if (user == null) {
                throw conflict(
                        "WORKFLOW_BILLING_RECONCILIATION_USER_MISSING",
                        "Workflow 计费用户不存在");
            }

            String status = reservation.get("status", String.class);
            if (!"reconciliation_required".equals(status)) {
                return duplicateOrConflict(command, reservation, status);
            }
            requireNoPriorAudit(reservation);
            WorkflowStepUsage requestedUsage = command.usage();
            try {
                requestedUsage.requireMonotonicAfter(
                        billing.reconciliationUsage(step.get("usageJson", String.class)));
                requestedUsage.requireMonotonicAfter(
                        billing.reconciliationUsage(
                                reservation.get("usageJson", String.class)));
            } catch (IllegalArgumentException | IllegalStateException exception) {
                throw conflict(
                        "WORKFLOW_BILLING_RECONCILIATION_USAGE_REGRESSION",
                        "计费对账用量与已冻结 Step 用量不一致");
            }
            requireDecisionUsage(command.decision(), requestedUsage);
            requireNoExistingChargeFacts(transaction, reservation);

            long balance = user.get("creditBalanceMicros", Long.class);
            long charge = "exact_usage".equals(command.decision())
                    ? billing.reconciliationCharge(reservation, requestedUsage)
                    : 0L;
            long reserved = reservation.get("reservedMicros", Long.class);
            if (charge > reserved) {
                throw conflict(
                        "WORKFLOW_BILLING_RECONCILIATION_LIMIT_EXCEEDED",
                        "精确用量金额超过用户已授权预留");
            }
            if (balance < charge) {
                throw conflict(
                        "WORKFLOW_BILLING_RECONCILIATION_BALANCE_INSUFFICIENT",
                        "用户余额不足以完成已预留用量结算");
            }
            long balanceAfter = Math.subtractExact(balance, charge);
            String targetStatus = "exact_usage".equals(command.decision())
                    ? "settled"
                    : "released";
            String auditedUsage = auditedUsage(
                    command, requestedUsage, charge, balanceAfter, now);

            if ("exact_usage".equals(command.decision())) {
                settleExact(
                        transaction,
                        run,
                        step,
                        reservation,
                        requestedUsage,
                        charge,
                        balanceAfter,
                        auditedUsage,
                        now);
            } else {
                int updated = transaction.execute(
                        """
                        UPDATE public."WorkflowBillingReservation"
                        SET status = 'released', "chargedMicros" = 0, "usageJson" = ?,
                            "settledAt" = ?, "updatedAt" = ?
                        WHERE id = ? AND status = 'reconciliation_required'
                        """,
                        auditedUsage,
                        now,
                        now,
                        reservation.get("id", String.class));
                if (updated != 1) throw concurrentConflict();
            }
            return new WorkflowBillingReconciliationResult(
                    command.reconciliationId(),
                    command.reservationRequestId(),
                    command.decision(),
                    targetStatus,
                    charge,
                    balanceAfter,
                    DatabaseTimestamp.api(now),
                    false);
        });
    }

    private void settleExact(
            DSLContext transaction,
            Record run,
            Record step,
            Record reservation,
            WorkflowStepUsage usage,
            long charge,
            long balanceAfter,
            String auditedUsage,
            LocalDateTime now) {
        String userId = run.get("userId", String.class);
        String requestId = reservation.get("requestId", String.class);
        int promptTokens = Math.toIntExact(usage.inputTokens());
        int cachedTokens = Math.toIntExact(usage.cachedTokens());
        int completionTokens = Math.toIntExact(usage.completionTokens());
        int totalTokens = Math.addExact(promptTokens, completionTokens);
        String model = billing.reconciliationModel(reservation);
        if (charge > 0) {
            int balanceUpdated = transaction.execute(
                    """
                    UPDATE public."User" SET "creditBalanceMicros" = ?
                    WHERE id = ?
                    """,
                    balanceAfter,
                    userId);
            if (balanceUpdated != 1) throw concurrentConflict();
            transaction.execute(
                    """
                    INSERT INTO public."CreditLedger" (
                      id, "userId", type, "amountMicros", "balanceAfterMicros", model,
                      "promptTokens", "completionTokens", "cachedTokens", "totalTokens",
                      "agentId", "novelId", "requestId", note, "createdAt"
                    ) VALUES (?, ?, 'ai_charge', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ids.next(),
                    userId,
                    -charge,
                    balanceAfter,
                    model,
                    promptTokens,
                    completionTokens,
                    cachedTokens,
                    totalTokens,
                    step.get("modelProfile", String.class),
                    run.get("novelId", String.class),
                    requestId,
                    "V2 Workflow 供应商账单对账",
                    now);
        }
        transaction.execute(
                """
                INSERT INTO public."TokenUsage" (
                  id, "userId", model, "promptTokens", "completionTokens", "cachedTokens",
                  "totalTokens", "agentId", "novelId", "createdAt", "requestId",
                  "taskId", "runId", "promptCacheMissTokens", "reasoningTokens"
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ids.next(),
                userId,
                model,
                promptTokens,
                completionTokens,
                cachedTokens,
                totalTokens,
                step.get("modelProfile", String.class),
                run.get("novelId", String.class),
                now,
                requestId,
                step.get("id", String.class),
                run.get("id", String.class),
                nullableInteger(usage.promptCacheMissTokens()),
                nullableInteger(usage.reasoningTokens()));
        int reservationUpdated = transaction.execute(
                """
                UPDATE public."WorkflowBillingReservation"
                SET status = 'settled', "chargedMicros" = ?, "usageJson" = ?,
                    "settledAt" = ?, "updatedAt" = ?
                WHERE id = ? AND status = 'reconciliation_required'
                """,
                charge,
                auditedUsage,
                now,
                now,
                reservation.get("id", String.class));
        if (reservationUpdated != 1) throw concurrentConflict();
    }

    private WorkflowBillingReconciliationResult duplicateOrConflict(
            WorkflowBillingReconciliationCommand command,
            Record reservation,
            String status) {
        Map<String, Object> usage = readObject(reservation.get("usageJson", String.class));
        Map<String, Object> audit = object(usage.get("reconciliation"), "reconciliation");
        String storedId = string(audit, "reconciliationId");
        if (!storedId.equals(command.reconciliationId())
                || !string(audit, "requestSha256").equals(command.requestSha256())) {
            throw driftConflict();
        }
        String decision = string(audit, "decision");
        String expectedStatus = "exact_usage".equals(decision) ? "settled" : "released";
        long charged = reservation.get("chargedMicros", Long.class);
        long storedCharge = integer(audit, "chargedMicros");
        LocalDateTime settledAt = reservation.get("settledAt", LocalDateTime.class);
        if (!expectedStatus.equals(status)
                || charged != storedCharge
                || settledAt == null
                || !string(audit, "reservationRequestId")
                        .equals(command.reservationRequestId())) {
            throw integrityConflict();
        }
        return new WorkflowBillingReconciliationResult(
                storedId,
                command.reservationRequestId(),
                decision,
                status,
                charged,
                integer(audit, "balanceAfterMicros"),
                DatabaseTimestamp.api(settledAt),
                true);
    }

    private String auditedUsage(
            WorkflowBillingReconciliationCommand command,
            WorkflowStepUsage usage,
            long charge,
            long balanceAfter,
            LocalDateTime now) {
        Map<String, Object> audit = new LinkedHashMap<>();
        audit.put("protocolVersion", command.protocolVersion());
        audit.put("reconciliationId", command.reconciliationId());
        audit.put("runId", command.runId());
        audit.put("novelId", command.novelId());
        audit.put("stepId", command.stepId());
        audit.put("reservationRequestId", command.reservationRequestId());
        audit.put("supplierEvidenceRef", command.supplierEvidenceRef());
        audit.put("supplierReportSha256", command.supplierReportSha256());
        audit.put("decision", command.decision());
        audit.put("requestSha256", command.requestSha256());
        audit.put("chargedMicros", charge);
        audit.put("balanceAfterMicros", balanceAfter);
        audit.put("settledAt", DatabaseTimestamp.api(now).toString());
        Map<String, Object> root = new LinkedHashMap<>(WorkflowCallbackValues.usageMap(usage));
        root.put("reconciliation", audit);
        return json.writeValueAsString(root);
    }

    private void requireNoPriorAudit(Record reservation) {
        Map<String, Object> usage = readObject(reservation.get("usageJson", String.class));
        if (usage.containsKey("reconciliation")) throw integrityConflict();
    }

    private static void requireIdentity(
            WorkflowBillingReconciliationCommand command,
            Record run,
            Record step,
            Record reservation) {
        boolean same = Objects.equals(command.novelId(), run.get("novelId", String.class))
                && Objects.equals(command.runId(), step.get("runId", String.class))
                && Objects.equals(command.runId(), reservation.get("runId", String.class))
                && Objects.equals(command.stepId(), reservation.get("stepId", String.class))
                && Objects.equals(run.get("userId", String.class),
                        reservation.get("userId", String.class));
        if (!same) {
            throw conflict(
                    "WORKFLOW_RESOURCE_MISMATCH",
                    "Workflow 计费对账资源身份不一致");
        }
        if (!Objects.equals(
                command.reservationRequestId(),
                reservation.get("requestId", String.class))) {
            throw conflict(
                    "WORKFLOW_BILLING_RECONCILIATION_REQUEST_MISMATCH",
                    "计费对账与预留请求标识不一致");
        }
    }

    private static void requireDecisionUsage(String decision, WorkflowStepUsage usage) {
        boolean exact = "exact_usage".equals(decision)
                && usage.usageStatus() == WorkflowUsageStatus.COMPLETE
                && usage.providerAttempts() > 0;
        boolean zero = "proven_zero".equals(decision)
                && usage.usageStatus() == WorkflowUsageStatus.UNKNOWN
                && usage.providerAttempts() == 0
                && usage.protocolCorrections() == 0;
        if (!exact && !zero) {
            throw conflict(
                    "WORKFLOW_BILLING_RECONCILIATION_USAGE_INVALID",
                    "计费对账决定与精确用量不一致");
        }
    }

    private static void requireNoExistingChargeFacts(
            DSLContext transaction, Record reservation) {
        Record facts = transaction.fetchOne(
                """
                SELECT
                  (SELECT count(*) FROM public."TokenUsage" WHERE "requestId" = ?) AS usages,
                  (SELECT count(*) FROM public."CreditLedger" WHERE "requestId" = ?) AS ledgers
                """,
                reservation.get("requestId", String.class),
                reservation.get("requestId", String.class));
        if (facts == null
                || facts.get("usages", Long.class) != 0L
                || facts.get("ledgers", Long.class) != 0L) {
            throw integrityConflict();
        }
    }

    private Map<String, Object> readObject(String value) {
        if (value == null) throw integrityConflict();
        try {
            return json.readValue(value, JSON_OBJECT);
        } catch (RuntimeException exception) {
            throw integrityConflict();
        }
    }

    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?> source)) throw integrityConflict();
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : source.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw integrityConflict();
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static String string(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String result)) throw integrityConflict();
        return result;
    }

    private static long integer(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Number result)) throw integrityConflict();
        return result.longValue();
    }

    private static Integer nullableInteger(Long value) {
        return value == null ? null : Math.toIntExact(value);
    }

    private static ApiException notFound() {
        return new ApiException(
                404,
                "WORKFLOW_BILLING_RECONCILIATION_NOT_FOUND",
                "Workflow 计费对账目标不存在");
    }

    private static ApiException driftConflict() {
        return conflict(
                "WORKFLOW_BILLING_RECONCILIATION_CONFLICT",
                "相同计费对账标识的请求载荷不一致");
    }

    private static ApiException integrityConflict() {
        return conflict(
                "WORKFLOW_BILLING_RECONCILIATION_INTEGRITY_ERROR",
                "Workflow 计费事实不完整或相互冲突");
    }

    private static ApiException concurrentConflict() {
        return conflict(
                "WORKFLOW_BILLING_RECONCILIATION_CONCURRENT_UPDATE",
                "Workflow 计费预留已被并发修改");
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(409, code, message);
    }
}

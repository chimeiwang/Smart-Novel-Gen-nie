package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.billing.domain.BillingPricing;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.workflows.application.WorkflowExecutionRejectedException;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import cn.inkforge.core.workflows.domain.WorkflowBudgetExceededException;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowRunBudget;
import cn.inkforge.core.workflows.domain.WorkflowRunBudgetCharge;
import cn.inkforge.core.workflows.domain.WorkflowStepBudget;
import cn.inkforge.core.workflows.domain.WorkflowStepUsage;
import cn.inkforge.core.workflows.domain.WorkflowUsageStatus;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * V2 Step 的积分预留、Run 累计预算和终报结算。
 *
 * <p>所有同时触及 V2 工作流与余额的事务固定按 Run → Step → BillingReservation → User 取行锁。V1
 * 计费只锁 User，随后用 MVCC 聚合 reservation 而不锁 Run/Step/Reservation 行，因此不存在反向 User → Run
 * 等待边。余额只保存已结算事实；同一用户的 {@code reserved} 与 {@code reconciliation_required} 行在 User
 * 行锁内占用可用余额。供应商成本 {@code costMicros} 与用户积分 charge 是两套事实：前者只进入 Step/Run
 * 预算，后者只由本类按冻结积分价格计算。
 */
final class WorkflowBillingCoordinator {

    private static final String CREDIT_PRICING_V1 = "credit-pricing.v1";

    private static final TypeReference<Map<String, Object>> JSON_OBJECT = new TypeReference<>() {};
    private static final List<String> TERMINAL_STEP_STATUSES =
            List.of("completed", "failed", "skipped");

    private final CuidV1Generator ids;
    private final ObjectMapper json;
    private final ExecutionRegistry registry;

    WorkflowBillingCoordinator(
            CuidV1Generator ids, ObjectMapper json, ExecutionRegistry registry) {
        this.ids = Objects.requireNonNull(ids);
        this.json = Objects.requireNonNull(json);
        this.registry = Objects.requireNonNull(registry);
    }

    void reserve(
            DSLContext transaction,
            String runId,
            String stepId,
            WorkflowResolvedModel resolved,
            LocalDateTime now) {
        Objects.requireNonNull(transaction);
        Objects.requireNonNull(resolved);
        ExecutionRegistry.AuthorizedDeployment deployment = authorizeReservation(resolved);
        Record run = transaction.fetchOne(
                """
                SELECT id, "userId", "novelId", status::text AS status, "budgetJson",
                       "cancelRequestedAt"
                FROM public."WorkflowRun"
                WHERE id = ? AND "engineVersion" = 2
                FOR UPDATE
                """,
                runId);
        Record step = transaction.fetchOne(
                """
                SELECT id, "runId", status::text AS status, purpose, "modelProfile",
                       "budgetJson", "resolvedModelJson"
                FROM public."WorkflowStep"
                WHERE id = ? AND "runId" = ?
                FOR UPDATE
                """,
                stepId,
                runId);
        if (run == null || step == null) {
            throw new WorkflowExecutionRejectedException("WORKFLOW_BILLING_SCOPE_INVALID");
        }
        if (isTerminalRun(run.get("status", String.class))
                || TERMINAL_STEP_STATUSES.contains(step.get("status", String.class))) {
            return;
        }
        if (run.get("cancelRequestedAt", LocalDateTime.class) != null) {
            throw new WorkflowExecutionRejectedException("RUN_CANCELLED");
        }
        Map<String, Object> resolvedMap = WorkflowCallbackValues.resolvedModelMap(resolved);
        String frozenResolved = step.get("resolvedModelJson", String.class);
        if (frozenResolved == null || !readObject(frozenResolved).equals(resolvedMap)) {
            throw new WorkflowExecutionRejectedException("MODEL_DEPLOYMENT_NOT_AUTHORIZED");
        }

        Record existing = lockReservation(transaction, stepId);
        Map<String, Object> pricing = pricingSnapshot(resolvedMap, deployment);
        WorkflowStepBudget stepBudget = stepBudget(step.get("budgetJson", String.class));
        long reservedMicros = deployment.billable()
                ? worstCreditCharge(stepBudget, pricing)
                : 0L;
        if (existing != null) {
            requireSameReservation(
                    existing, run, step, deployment.pricingVersion(), pricing, reservedMicros);
            return;
        }

        requireRunBudget(transaction, run, stepId);
        String userId = run.get("userId", String.class);
        Record user = transaction.fetchOne(
                """
                SELECT id, "creditBalanceMicros"
                FROM public."User"
                WHERE id = ?
                FOR UPDATE
                """,
                userId);
        if (user == null) {
            throw new WorkflowExecutionRejectedException("WORKFLOW_BILLING_SCOPE_INVALID");
        }
        long outstanding = outstandingReservations(transaction, userId);
        long balance = user.get("creditBalanceMicros", Long.class);
        if (reservedMicros > Math.subtractExact(balance, outstanding)) {
            throw new WorkflowExecutionRejectedException("INSUFFICIENT_CREDITS");
        }
        transaction.execute(
                """
                INSERT INTO public."WorkflowBillingReservation" (
                  id, "runId", "stepId", "userId", "requestId", "pricingVersion",
                  "pricingJson", "reservedMicros", "chargedMicros", status,
                  "createdAt", "updatedAt"
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'reserved', ?, ?)
                """,
                ids.next(),
                runId,
                stepId,
                userId,
                ids.next(),
                deployment.pricingVersion(),
                json.writeValueAsString(pricing),
                reservedMicros,
                now,
                now);
    }

    /** waiting_provider 必须看到 preparing 原子门已经建立的有效预留。 */
    void requireProviderGate(DSLContext transaction, String runId, String stepId) {
        Record value = transaction.fetchOne(
                """
                SELECT reservation.status, reservation."pricingVersion", reservation."pricingJson",
                       step."resolvedModelJson", run."cancelRequestedAt"
                FROM public."WorkflowRun" AS run
                JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                LEFT JOIN public."WorkflowBillingReservation" AS reservation
                  ON reservation."stepId" = step.id AND reservation."runId" = run.id
                WHERE run.id = ? AND step.id = ? AND run."engineVersion" = 2
                """,
                runId,
                stepId);
        if (value == null) {
            throw new ApiException(409, "WORKFLOW_BILLING_SCOPE_INVALID", "Workflow 计费范围无效");
        }
        if (value.get("cancelRequestedAt", LocalDateTime.class) != null) {
            throw new ApiException(409, "WORKFLOW_CANCEL_PENDING", "Workflow Run 正在停止");
        }
        if (value.get("status", String.class) == null
                || value.get("resolvedModelJson", String.class) == null) {
            // preparing 尚未完成或事务仍在提交时必须重试，不能放行无预留 Provider。
            throw new ApiException(
                    503,
                    "WORKFLOW_BILLING_RESERVATION_PENDING",
                    "Workflow 模型预留尚未完成");
        }
        if (!"reserved".equals(value.get("status", String.class))) {
            throw new ApiException(409, "WORKFLOW_BILLING_RESERVATION_INVALID", "Workflow 模型预留不可用");
        }
        Map<String, Object> pricing = readObject(value.get("pricingJson", String.class));
        Map<String, Object> resolved = readObject(value.get("resolvedModelJson", String.class));
        if (!resolved.equals(object(pricing.get("resolvedModel"), "resolvedModel"))) {
            throw new WorkflowExecutionRejectedException("MODEL_DEPLOYMENT_NOT_AUTHORIZED");
        }
        String pricingVersion = value.get("pricingVersion", String.class);
        requireSupportedPricing(pricingVersion);
        boolean billable = bool(pricing, "billable");
        if (!frozenPricingSnapshot(resolved, pricingVersion, billable).equals(pricing)) {
            throw new WorkflowExecutionRejectedException("WORKFLOW_BILLING_PRICING_DRIFT");
        }
    }

    /**
     * matching-fence 终报是唯一能在 running 后证明 providerAttempts=0 的事实；否则未知字段保留预留待对账。
     */
    WorkflowStepUsage settleTerminal(
            DSLContext transaction,
            String runId,
            String stepId,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        Objects.requireNonNull(usage);
        if (usage.providerAttempts() == 0
                && (usage.usageStatus() != WorkflowUsageStatus.UNKNOWN
                        || usage.protocolCorrections() != 0
                        || hasKnownProviderUsage(usage))) {
            throw new ApiException(
                    409,
                    "WORKFLOW_USAGE_ATTEMPT_MISMATCH",
                    "零供应商尝试不能携带供应商用量或协议纠正");
        }
        Record reservation = lockReservation(transaction, stepId);
        if (reservation == null) {
            if (usage.providerAttempts() == 0) return usage;
            throw new ApiException(
                    409,
                    "WORKFLOW_BILLING_RESERVATION_MISSING",
                    "已调用模型的 Workflow Step 缺少计费预留");
        }
        requireReservationScope(reservation, runId, stepId);
        validateFrozenPricing(reservation);
        String status = reservation.get("status", String.class);
        if (!"reserved".equals(status)) {
            throw new ApiException(
                    409,
                    "WORKFLOW_BILLING_RESERVATION_TERMINAL",
                    "Workflow Step 的计费预留已经结算");
        }
        String usageJson = json.writeValueAsString(WorkflowCallbackValues.usageMap(usage));
        if (usage.providerAttempts() == 0) {
            if (hasKnownProviderUsage(usage)) {
                throw new ApiException(
                        409,
                        "WORKFLOW_USAGE_ATTEMPT_MISMATCH",
                        "零供应商尝试不能携带供应商用量");
            }
            transaction.execute(
                    """
                    UPDATE public."WorkflowBillingReservation"
                    SET status = 'released', "chargedMicros" = 0, "usageJson" = ?,
                        "settledAt" = ?, "updatedAt" = ?
                    WHERE id = ? AND status = 'reserved'
                    """,
                    usageJson,
                    now,
                    now,
                    reservation.get("id", String.class));
            return usage;
        }
        if (!hasExactCreditUsage(usage)) {
            markReconciliation(transaction, reservation, usageJson, now);
            return usage;
        }
        settleExact(transaction, reservation, usage, usageJson, now);
        return usage;
    }

    /** pending Step 尚未进入执行器时取消，或确定性提交拒绝，才能无条件释放。 */
    void releaseUnstarted(
            DSLContext transaction, String runId, String stepId, LocalDateTime now) {
        releaseProvenNoProviderAttempt(
                transaction,
                runId,
                stepId,
                new WorkflowStepUsage(
                        WorkflowUsageStatus.UNKNOWN,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        null,
                        0,
                        0,
                        0),
                now);
    }

    /** matching-fence preparing/waiting_provider 的拒绝回执可精确证明尚未调用 Provider。 */
    void releaseProvenNoProviderAttempt(
            DSLContext transaction,
            String runId,
            String stepId,
            WorkflowStepUsage usage,
            LocalDateTime now) {
        if (usage.providerAttempts() != 0 || hasKnownProviderUsage(usage)) {
            throw new IllegalArgumentException("只有明确零 Provider attempt 才能释放预留");
        }
        Record reservation = lockReservation(transaction, stepId);
        if (reservation == null) return;
        requireReservationScope(reservation, runId, stepId);
        if (!"reserved".equals(reservation.get("status", String.class))) return;
        String usageJson = json.writeValueAsString(WorkflowCallbackValues.usageMap(usage));
        transaction.execute(
                """
                UPDATE public."WorkflowBillingReservation"
                SET status = 'released', "chargedMicros" = 0, "usageJson" = ?,
                    "settledAt" = ?, "updatedAt" = ?
                WHERE id = ? AND status = 'reserved'
                """,
                usageJson,
                now,
                now,
                reservation.get("id", String.class));
    }

    /**
     * running 租约过期只说明 Core 看不到 ACK，不能证明供应商未收到请求；即使最后快照 attempts=0 也保留额度。
     */
    void markExpiredRunningForReconciliation(
            DSLContext transaction,
            String runId,
            String stepId,
            String usageJson,
            LocalDateTime now) {
        Record reservation = lockReservation(transaction, stepId);
        if (reservation == null) {
            throw new IllegalStateException("running Workflow Step 缺少 BillingReservation");
        }
        requireReservationScope(reservation, runId, stepId);
        if (!"reserved".equals(reservation.get("status", String.class))) return;
        // 取消收敛器只会传入自己已验证/构造的 JSON 对象；这里再次解析，防止损坏快照污染财务事实。
        readObject(usageJson);
        markReconciliation(transaction, reservation, usageJson, now);
    }

    private void requireRunBudget(DSLContext transaction, Record run, String currentStepId) {
        WorkflowRunBudget budget = runBudget(run.get("budgetJson", String.class));
        List<Record> steps = transaction.fetch(
                """
                SELECT step.id, step.status::text AS status, step.purpose, step."budgetJson",
                       step."usageJson", reservation.status AS reservation_status
                FROM public."WorkflowStep" AS step
                LEFT JOIN public."WorkflowBillingReservation" AS reservation
                  ON reservation."stepId" = step.id
                WHERE step."runId" = ? AND step."budgetJson" IS NOT NULL
                ORDER BY step.ordinal, step.id
                """,
                run.get("id", String.class));
        List<WorkflowRunBudgetCharge> charges = new ArrayList<>();
        for (Record value : steps) {
            WorkflowStepBudget stepBudget = stepBudget(value.get("budgetJson", String.class));
            boolean correction = "protocol_correction".equals(value.get("purpose", String.class));
            String status = value.get("status", String.class);
            if ("pending".equals(status) || "running".equals(status)) {
                charges.add(WorkflowRunBudgetCharge.active(stepBudget, correction));
                continue;
            }
            String reservationStatus = value.get("reservation_status", String.class);
            if ("reconciliation_required".equals(reservationStatus)) {
                charges.add(WorkflowRunBudgetCharge.active(stepBudget, correction));
                continue;
            }
            String usageJson = value.get("usageJson", String.class);
            if (usageJson == null) continue;
            WorkflowStepUsage usage = usage(readObject(usageJson));
            if (usage.providerAttempts() == 0) {
                charges.add(new WorkflowRunBudgetCharge(
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        usage.wallTimeMillis(),
                        correction ? 1 : 0));
            } else {
                charges.add(WorkflowRunBudgetCharge.terminal(stepBudget, usage, correction));
            }
        }
        if (steps.stream().noneMatch(value -> currentStepId.equals(value.get("id", String.class)))) {
            throw new WorkflowExecutionRejectedException("WORKFLOW_RUN_BUDGET_INVALID");
        }
        try {
            budget.requireWithin(charges);
        } catch (WorkflowBudgetExceededException exception) {
            throw new WorkflowExecutionRejectedException("WORKFLOW_RUN_BUDGET_EXCEEDED");
        }
    }

    private void settleExact(
            DSLContext transaction,
            Record reservation,
            WorkflowStepUsage usage,
            String usageJson,
            LocalDateTime now) {
        Map<String, Object> pricing = readObject(reservation.get("pricingJson", String.class));
        boolean billable = bool(pricing, "billable");
        WorkflowResolvedModel resolved = resolvedModel(object(pricing.get("resolvedModel"), "resolvedModel"));
        int promptTokens = Math.toIntExact(usage.inputTokens());
        int cachedTokens = Math.toIntExact(usage.cachedTokens());
        int completionTokens = Math.toIntExact(usage.completionTokens());
        if (cachedTokens > promptTokens) {
            throw new ApiException(
                    409,
                    "WORKFLOW_USAGE_INVALID",
                    "缓存 token 不能超过输入 token");
        }
        int totalTokens = Math.addExact(promptTokens, completionTokens);
        long charge = billable
                ? creditCharge(pricing, promptTokens, cachedTokens, completionTokens)
                : 0L;
        long reserved = reservation.get("reservedMicros", Long.class);
        if (charge > reserved) {
            // 实际供应商用量已经发生，但用户只授权了冻结预留上限。保留完整
            // usage 并转人工对账；不能自动超扣，也不能拒绝终报导致无限回放。
            markReconciliation(transaction, reservation, usageJson, now);
            return;
        }
        String requestId = reservation.get("requestId", String.class);
        Record existingUsage = transaction.fetchOne(
                """
                SELECT id, "userId", model, "promptTokens", "cachedTokens",
                       "promptCacheMissTokens", "completionTokens", "reasoningTokens",
                       "totalTokens", "agentId", "novelId", "taskId", "runId"
                FROM public."TokenUsage" WHERE "requestId" = ?
                """,
                requestId);
        if (existingUsage != null) {
            throw new IllegalStateException("reserved 状态却已存在相同 requestId 的 TokenUsage");
        }
        String userId = reservation.get("userId", String.class);
        Record user = transaction.fetchOne(
                """
                SELECT id, "creditBalanceMicros" FROM public."User"
                WHERE id = ? FOR UPDATE
                """,
                userId);
        if (user == null) throw new IllegalStateException("Workflow 计费用户不存在");
        long balance = user.get("creditBalanceMicros", Long.class);
        long balanceAfter = Math.subtractExact(balance, charge);
        if (balanceAfter < 0) {
            throw new IllegalStateException("Workflow 已预留积分在结算前被其他链路透支");
        }
        Record scope = transaction.fetchOne(
                """
                SELECT run."novelId", step."modelProfile"
                FROM public."WorkflowRun" AS run
                JOIN public."WorkflowStep" AS step ON step."runId" = run.id
                WHERE run.id = ? AND step.id = ?
                """,
                reservation.get("runId", String.class),
                reservation.get("stepId", String.class));
        if (scope == null) throw new IllegalStateException("Workflow 计费范围已丢失");
        if (charge > 0) {
            transaction.execute(
                    """
                    UPDATE public."User" SET "creditBalanceMicros" = ?
                    WHERE id = ?
                    """,
                    balanceAfter,
                    userId);
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
                    resolved.model(),
                    promptTokens,
                    completionTokens,
                    cachedTokens,
                    totalTokens,
                    scope.get("modelProfile", String.class),
                    scope.get("novelId", String.class),
                    requestId,
                    "V2 Workflow 模型调用",
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
                resolved.model(),
                promptTokens,
                completionTokens,
                cachedTokens,
                totalTokens,
                scope.get("modelProfile", String.class),
                scope.get("novelId", String.class),
                now,
                requestId,
                reservation.get("stepId", String.class),
                reservation.get("runId", String.class),
                nullableInteger(usage.promptCacheMissTokens()),
                nullableInteger(usage.reasoningTokens()));
        transaction.execute(
                """
                UPDATE public."WorkflowBillingReservation"
                SET status = 'settled', "chargedMicros" = ?, "usageJson" = ?,
                    "settledAt" = ?, "updatedAt" = ?
                WHERE id = ? AND status = 'reserved'
                """,
                charge,
                usageJson,
                now,
                now,
                reservation.get("id", String.class));
    }

    private void markReconciliation(
            DSLContext transaction,
            Record reservation,
            String usageJson,
            LocalDateTime now) {
        transaction.execute(
                """
                UPDATE public."WorkflowBillingReservation"
                SET status = 'reconciliation_required', "chargedMicros" = 0,
                    "usageJson" = ?, "settledAt" = NULL, "updatedAt" = ?
                WHERE id = ? AND status = 'reserved'
                """,
                usageJson,
                now,
                reservation.get("id", String.class));
    }

    private Record lockReservation(DSLContext transaction, String stepId) {
        return transaction.fetchOne(
                """
                SELECT reservation.*, run."novelId", step."modelProfile"
                FROM public."WorkflowBillingReservation" AS reservation
                JOIN public."WorkflowRun" AS run ON run.id = reservation."runId"
                JOIN public."WorkflowStep" AS step ON step.id = reservation."stepId"
                WHERE reservation."stepId" = ?
                FOR UPDATE OF reservation
                """,
                stepId);
    }

    private static void requireReservationScope(
            Record reservation, String runId, String stepId) {
        if (!Objects.equals(reservation.get("runId", String.class), runId)
                || !Objects.equals(reservation.get("stepId", String.class), stepId)) {
            throw new ApiException(409, "WORKFLOW_BILLING_SCOPE_INVALID", "Workflow 计费范围无效");
        }
    }

    private void requireSameReservation(
            Record existing,
            Record run,
            Record step,
            String pricingVersion,
            Map<String, Object> pricing,
            long reservedMicros) {
        boolean same = Objects.equals(existing.get("runId", String.class), run.get("id", String.class))
                && Objects.equals(existing.get("stepId", String.class), step.get("id", String.class))
                && Objects.equals(existing.get("userId", String.class), run.get("userId", String.class))
                && pricingVersion.equals(existing.get("pricingVersion", String.class))
                && existing.get("reservedMicros", Long.class) == reservedMicros
                && readObject(existing.get("pricingJson", String.class)).equals(pricing);
        if (!same) {
            throw new WorkflowExecutionRejectedException("WORKFLOW_BILLING_PRICING_DRIFT");
        }
        if (!"reserved".equals(existing.get("status", String.class))) {
            throw new WorkflowExecutionRejectedException("WORKFLOW_BILLING_RESERVATION_TERMINAL");
        }
    }

    private ExecutionRegistry.AuthorizedDeployment authorizeReservation(
            WorkflowResolvedModel resolved) {
        try {
            ExecutionRegistry.AuthorizedDeployment deployment =
                    registry.requireAuthorizedDeployment(resolved);
            requireSupportedPricing(deployment.pricingVersion());
            return deployment;
        } catch (IllegalArgumentException | IllegalStateException exception) {
            throw new WorkflowExecutionRejectedException("MODEL_DEPLOYMENT_NOT_AUTHORIZED");
        }
    }

    private void validateFrozenPricing(Record reservation) {
        Map<String, Object> pricing = readObject(reservation.get("pricingJson", String.class));
        Map<String, Object> resolved = object(pricing.get("resolvedModel"), "resolvedModel");
        // preparing 已把当时授权的 resolved model、价格版本和整数费率冻结为不可变快照。
        // terminal 必须能跨镜像/registry 更新结算，不能再次依赖当前 allowlist；这里只校验快照
        // 自洽、fingerprint 与 Core 仍实现该价格算法。
        resolvedModel(resolved);
        String pricingVersion = reservation.get("pricingVersion", String.class);
        requireSupportedPricing(pricingVersion);
        boolean billable = bool(pricing, "billable");
        if (!frozenPricingSnapshot(resolved, pricingVersion, billable).equals(pricing)) {
            throw new ApiException(409, "WORKFLOW_BILLING_PRICING_DRIFT", "Workflow 冻结价格发生漂移");
        }
    }

    /** 对账入口只读冻结价格，不能重新查询当前 Registry 或信任请求自报金额。 */
    long reconciliationCharge(Record reservation, WorkflowStepUsage usage) {
        validateFrozenPricing(reservation);
        if (!hasExactCreditUsage(usage)) {
            throw new ApiException(
                    409,
                    "WORKFLOW_BILLING_RECONCILIATION_USAGE_INVALID",
                    "计费对账缺少精确 token 用量");
        }
        int promptTokens = Math.toIntExact(usage.inputTokens());
        int cachedTokens = Math.toIntExact(usage.cachedTokens());
        int completionTokens = Math.toIntExact(usage.completionTokens());
        if (cachedTokens > promptTokens) {
            throw new ApiException(
                    409,
                    "WORKFLOW_BILLING_RECONCILIATION_USAGE_INVALID",
                    "缓存 token 不能超过输入 token");
        }
        Map<String, Object> pricing = readObject(reservation.get("pricingJson", String.class));
        return bool(pricing, "billable")
                ? creditCharge(pricing, promptTokens, cachedTokens, completionTokens)
                : 0L;
    }

    String reconciliationModel(Record reservation) {
        validateFrozenPricing(reservation);
        Map<String, Object> pricing = readObject(reservation.get("pricingJson", String.class));
        return resolvedModel(object(pricing.get("resolvedModel"), "resolvedModel")).model();
    }

    WorkflowStepUsage reconciliationUsage(String usageJson) {
        return usage(readObject(usageJson));
    }

    private static Map<String, Object> pricingSnapshot(
            Map<String, Object> resolvedModel,
            ExecutionRegistry.AuthorizedDeployment deployment) {
        return frozenPricingSnapshot(
                resolvedModel, deployment.pricingVersion(), deployment.billable());
    }

    private static Map<String, Object> frozenPricingSnapshot(
            Map<String, Object> resolvedModel, String pricingVersion, boolean billable) {
        requireSupportedPricing(pricingVersion);
        Map<String, Object> rates = new LinkedHashMap<>();
        rates.put(
                "cachedInputMicrosPerToken",
                Math.toIntExact(BillingPricing.CACHED_INPUT_MICROS_PER_TOKEN));
        rates.put(
                "outputMicrosPerToken",
                Math.toIntExact(BillingPricing.OUTPUT_MICROS_PER_TOKEN));
        rates.put(
                "uncachedInputMicrosPerToken",
                Math.toIntExact(BillingPricing.UNCACHED_INPUT_MICROS_PER_TOKEN));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("billable", billable);
        result.put("currency", "credit_micros");
        result.put("pricingVersion", pricingVersion);
        result.put("rates", Collections.unmodifiableMap(rates));
        result.put("resolvedModel", Collections.unmodifiableMap(new LinkedHashMap<>(resolvedModel)));
        return Collections.unmodifiableMap(result);
    }

    private static void requireSupportedPricing(String pricingVersion) {
        if (!CREDIT_PRICING_V1.equals(pricingVersion)) {
            throw new IllegalArgumentException("Core 尚未实现 Deployment Profile 指定的积分价格版本");
        }
    }

    private static long worstCreditCharge(
            WorkflowStepBudget budget, Map<String, Object> pricing) {
        Map<String, Object> rates = object(pricing.get("rates"), "pricing rates");
        return Math.addExact(
                Math.multiplyExact(
                        budget.maxInputTokens(),
                        longInteger(rates, "uncachedInputMicrosPerToken")),
                Math.multiplyExact(
                        budget.maxCompletionTokens(),
                        longInteger(rates, "outputMicrosPerToken")));
    }

    private static long creditCharge(
            Map<String, Object> pricing,
            int promptTokens,
            int cachedTokens,
            int completionTokens) {
        Map<String, Object> rates = object(pricing.get("rates"), "pricing rates");
        long uncached = Math.subtractExact(promptTokens, cachedTokens);
        return Math.addExact(
                Math.addExact(
                        Math.multiplyExact(
                                uncached,
                                longInteger(rates, "uncachedInputMicrosPerToken")),
                        Math.multiplyExact(
                                cachedTokens,
                                longInteger(rates, "cachedInputMicrosPerToken"))),
                Math.multiplyExact(
                        completionTokens,
                        longInteger(rates, "outputMicrosPerToken")));
    }

    private static long outstandingReservations(DSLContext transaction, String userId) {
        BigDecimal value = transaction.fetchOne(
                        """
                        SELECT COALESCE(sum("reservedMicros"), 0)::numeric AS reserved
                        FROM public."WorkflowBillingReservation"
                        WHERE "userId" = ? AND status IN ('reserved', 'reconciliation_required')
                        """,
                        userId)
                .get("reserved", BigDecimal.class);
        return value.longValueExact();
    }

    private static boolean hasExactCreditUsage(WorkflowStepUsage usage) {
        return usage.inputTokens() != null
                && usage.cachedTokens() != null
                && usage.completionTokens() != null;
    }

    private static boolean hasKnownProviderUsage(WorkflowStepUsage usage) {
        return usage.inputTokens() != null
                || usage.cachedTokens() != null
                || usage.promptCacheMissTokens() != null
                || usage.completionTokens() != null
                || usage.reasoningTokens() != null
                || usage.visibleOutputTokens() != null
                || usage.costMicros() != null;
    }

    private WorkflowRunBudget runBudget(String value) {
        Map<String, Object> budget = readObject(value);
        return new WorkflowRunBudget(
                integer(budget, "maxModelCalls"),
                longInteger(budget, "maxInputTokens"),
                longInteger(budget, "maxPromptCacheMissTokens"),
                longInteger(budget, "maxCompletionTokens"),
                longInteger(budget, "maxReasoningTokens"),
                longInteger(budget, "maxVisibleOutputTokens"),
                longInteger(budget, "maxCostMicros"),
                longInteger(budget, "maxWallClockSeconds"),
                integer(budget, "maxProviderRetriesPerStep"),
                integer(budget, "maxProtocolCorrectionSteps"));
    }

    private WorkflowStepBudget stepBudget(String value) {
        Map<String, Object> wrapper = readObject(value);
        Map<String, Object> budget = object(wrapper.get("budget"), "Step budget");
        return new WorkflowStepBudget(
                integer(budget, "maxModelCalls"),
                longInteger(budget, "maxInputTokens"),
                longInteger(budget, "maxPromptCacheMissTokens"),
                longInteger(budget, "maxCompletionTokens"),
                longInteger(budget, "maxReasoningTokens"),
                longInteger(budget, "maxVisibleOutputTokens"),
                longInteger(budget, "maxCostMicros"),
                longInteger(budget, "maxWallClockSeconds"),
                integer(budget, "maxProviderRetries"),
                integer(budget, "maxProtocolCorrections"));
    }

    private static WorkflowStepUsage usage(Map<String, Object> value) {
        return new WorkflowStepUsage(
                WorkflowUsageStatus.fromWireValue(string(value, "usageStatus")),
                nullableLong(value, "inputTokens"),
                nullableLong(value, "cachedTokens"),
                nullableLong(value, "promptCacheMissTokens"),
                nullableLong(value, "completionTokens"),
                nullableLong(value, "reasoningTokens"),
                nullableLong(value, "visibleOutputTokens"),
                nullableLong(value, "costMicros"),
                integer(value, "providerAttempts"),
                integer(value, "protocolCorrections"),
                longInteger(value, "wallTimeMillis"));
    }

    private static WorkflowResolvedModel resolvedModel(Map<String, Object> value) {
        return new WorkflowResolvedModel(
                string(value, "deploymentProfileKey"),
                string(value, "deploymentFingerprint"),
                string(value, "provider"),
                string(value, "model"),
                string(value, "transportProfile"),
                string(value, "endpointProfile"),
                string(value, "structuredOutputRoute"),
                string(value, "capabilityVersion"),
                string(value, "reasoningMode"),
                bool(value, "supportsRequestIdempotency"));
    }

    private Map<String, Object> readObject(String value) {
        if (value == null) throw new IllegalStateException("Workflow JSON 快照不能为空");
        return json.readValue(value, JSON_OBJECT);
    }

    private static Map<String, Object> object(Object value, String label) {
        if (!(value instanceof Map<?, ?> source)) {
            throw new IllegalStateException(label + " 必须是 JSON 对象");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : source.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw new IllegalStateException(label + " key 必须是字符串");
            }
            result.put(key, entry.getValue());
        }
        return Collections.unmodifiableMap(result);
    }

    private static boolean bool(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Boolean result)) {
            throw new IllegalStateException(key + " 必须是布尔值");
        }
        return result;
    }

    private static String string(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String result)) {
            throw new IllegalStateException(key + " 必须是字符串");
        }
        return result;
    }

    private static int integer(Map<String, Object> value, String key) {
        return Math.toIntExact(longInteger(value, key));
    }

    private static long longInteger(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof Number result)) {
            throw new IllegalStateException(key + " 必须是整数");
        }
        return result.longValue();
    }

    private static Long nullableLong(Map<String, Object> value, String key) {
        return value.containsKey(key) ? longInteger(value, key) : null;
    }

    private static Integer nullableInteger(Long value) {
        return value == null ? null : Math.toIntExact(value);
    }

    private static boolean isTerminalRun(String status) {
        return List.of("completed", "failed", "cancelled").contains(status);
    }
}

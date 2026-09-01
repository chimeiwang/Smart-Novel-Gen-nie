package cn.inkforge.core.workflows.application;

import cn.inkforge.contracts.api.BillingReconciliationReceipt;
import cn.inkforge.contracts.api.BillingReconciliationRequest;
import cn.inkforge.contracts.api.StepUsage;
import cn.inkforge.core.billing.reconciliation.WorkflowBillingReconciliation;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.domain.WorkflowStepUsage;
import cn.inkforge.core.workflows.domain.WorkflowUsageStatus;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.regex.Pattern;
import org.openapitools.jackson.nullable.JsonNullable;

/** 校验共享 DTO、冻结 canonical 请求身份并委托 PostgreSQL 原子结算。 */
public final class WorkflowBillingReconciliationService
        implements WorkflowBillingReconciliation {

    private static final Pattern SHA256 = Pattern.compile("^[0-9a-f]{64}$");

    private final WorkflowBillingReconciliationRepository repository;

    public WorkflowBillingReconciliationService(
            WorkflowBillingReconciliationRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    @Override
    public BillingReconciliationReceipt reconcile(BillingReconciliationRequest request) {
        Objects.requireNonNull(request, "计费对账请求不能为空");
        String novelId = requiredNullable(request.getNovelId());
        String decision = requiredDecision(request);
        String evidenceRef = requireEvidence(request.getSupplierEvidenceRef());
        if (!"2.0".equals(request.getProtocolVersion())
                || !SHA256.matcher(Objects.requireNonNullElse(
                                request.getSupplierReportSha256(), ""))
                        .matches()) {
            throw validation();
        }
        WorkflowStepUsage usage;
        try {
            usage = usage(request.getUsage());
            requireDecisionUsage(decision, usage);
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw validation();
        }
        Map<String, Object> material = new LinkedHashMap<>();
        material.put("protocolVersion", request.getProtocolVersion());
        material.put("reconciliationId", request.getReconciliationId());
        material.put("runId", request.getRunId());
        material.put("novelId", novelId);
        material.put("stepId", request.getStepId());
        material.put("reservationRequestId", request.getReservationRequestId());
        material.put("supplierEvidenceRef", evidenceRef);
        material.put("supplierReportSha256", request.getSupplierReportSha256());
        material.put("decision", decision);
        material.put("usage", usageMap(usage));
        String requestSha256 = ExecutionCanonicalJson.sha256(material);
        WorkflowBillingReconciliationResult result = repository.reconcile(
                new WorkflowBillingReconciliationCommand(
                        request.getProtocolVersion(),
                        request.getReconciliationId(),
                        request.getRunId(),
                        novelId,
                        request.getStepId(),
                        request.getReservationRequestId(),
                        evidenceRef,
                        request.getSupplierReportSha256(),
                        decision,
                        usage,
                        requestSha256));
        BillingReconciliationReceipt response = new BillingReconciliationReceipt();
        response.setBalanceAfterMicros(result.balanceAfterMicros());
        response.setChargedMicros(result.chargedMicros());
        response.setDecision(
                BillingReconciliationReceipt.DecisionEnum.fromValue(result.decision()));
        response.setDuplicate(result.duplicate());
        response.setProtocolVersion("2.0");
        response.setReconciliationId(result.reconciliationId());
        response.setReservationRequestId(result.reservationRequestId());
        response.setReservationStatus(
                BillingReconciliationReceipt.ReservationStatusEnum.fromValue(
                        result.reservationStatus()));
        response.setSettledAt(result.settledAt());
        return response;
    }

    private static WorkflowStepUsage usage(StepUsage value) {
        Objects.requireNonNull(value, "usage 不能为空");
        return new WorkflowStepUsage(
                WorkflowUsageStatus.fromWireValue(value.getUsageStatus().getValue()),
                optionalLong(value.getInputTokens()),
                optionalLong(value.getCachedTokens()),
                optionalLong(value.getPromptCacheMissTokens()),
                optionalLong(value.getCompletionTokens()),
                optionalLong(value.getReasoningTokens()),
                optionalLong(value.getVisibleOutputTokens()),
                optionalLong(value.getCostMicros()),
                value.getProviderAttempts(),
                value.getProtocolCorrections(),
                value.getWallTimeMillis());
    }

    private static void requireDecisionUsage(String decision, WorkflowStepUsage usage) {
        if ("exact_usage".equals(decision)) {
            if (usage.usageStatus() != WorkflowUsageStatus.COMPLETE
                    || usage.providerAttempts() == 0) {
                throw new IllegalArgumentException("exact_usage 必须是完整的非零尝试用量");
            }
            return;
        }
        if (!"proven_zero".equals(decision)
                || usage.usageStatus() != WorkflowUsageStatus.UNKNOWN
                || usage.providerAttempts() != 0) {
            throw new IllegalArgumentException("proven_zero 必须是零尝试未知用量");
        }
    }

    private static Map<String, Object> usageMap(WorkflowStepUsage usage) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("usageStatus", usage.usageStatus().wireValue());
        putKnown(result, "inputTokens", usage.inputTokens());
        putKnown(result, "cachedTokens", usage.cachedTokens());
        putKnown(result, "promptCacheMissTokens", usage.promptCacheMissTokens());
        putKnown(result, "completionTokens", usage.completionTokens());
        putKnown(result, "reasoningTokens", usage.reasoningTokens());
        putKnown(result, "visibleOutputTokens", usage.visibleOutputTokens());
        putKnown(result, "costMicros", usage.costMicros());
        result.put("providerAttempts", usage.providerAttempts());
        result.put("protocolCorrections", usage.protocolCorrections());
        result.put("wallTimeMillis", usage.wallTimeMillis());
        return Collections.unmodifiableMap(result);
    }

    private static String requiredDecision(BillingReconciliationRequest request) {
        return request.getDecision() == null ? "" : request.getDecision().getValue();
    }

    private static String requireEvidence(String value) {
        String normalized = value == null ? "" : value.strip();
        if (normalized.isEmpty() || normalized.length() > 2_000) throw validation();
        return normalized;
    }

    private static <T> T requiredNullable(JsonNullable<T> value) {
        if (value == null || !value.isPresent()) throw validation();
        return value.get();
    }

    private static Long optionalLong(JsonNullable<Integer> value) {
        if (value == null || !value.isPresent() || value.get() == null) return null;
        return value.get().longValue();
    }

    private static void putKnown(Map<String, Object> target, String key, Long value) {
        if (value != null) target.put(key, value);
    }

    private static ApiException validation() {
        return new ApiException(422, "VALIDATION_ERROR", "请求参数校验失败");
    }
}

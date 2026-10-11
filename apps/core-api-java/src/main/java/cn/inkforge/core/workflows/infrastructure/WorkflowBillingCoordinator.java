package cn.inkforge.core.workflows.infrastructure;

import cn.inkforge.core.billing.domain.BillingPricing;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import cn.inkforge.core.workflows.domain.WorkflowStepUsage;
import cn.inkforge.core.workflows.domain.WorkflowUsageStatus;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.Record;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 仅按冻结价格读取历史预留并计算对账金额；不再创建预留或执行模型调用。
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

    private final ObjectMapper json;

    WorkflowBillingCoordinator(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
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

    private static boolean hasExactCreditUsage(WorkflowStepUsage usage) {
        return usage.inputTokens() != null
                && usage.cachedTokens() != null
                && usage.completionTokens() != null;
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

}

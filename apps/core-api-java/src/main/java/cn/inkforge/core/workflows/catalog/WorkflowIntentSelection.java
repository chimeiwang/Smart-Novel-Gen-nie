package cn.inkforge.core.workflows.catalog;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

/** Core 已完成 intent_selection 控制 Step 的完整不可变输入；不保存模型推测的资源身份。 */
public record WorkflowIntentSelection(
        String runId,
        String operationKey,
        String operationPlanSha256,
        String resolverStepId,
        String resolverResultHash,
        String intentEvidenceBundleId,
        String targetType,
        String targetId,
        String scopeKind) {

    public static final String SCHEMA = "durable.intent-selection.v1";
    private static final Set<String> FIELDS = Set.of(
            "schema", "runId", "operationKey", "operationPlanSha256", "resolverStepId",
            "resolverResultHash", "intentEvidenceBundleId", "targetType", "targetId", "scopeKind");

    public WorkflowIntentSelection {
        runId = text(runId, "runId");
        operationKey = text(operationKey, "operationKey");
        operationPlanSha256 = hash(operationPlanSha256, "operationPlanSha256");
        resolverStepId = text(resolverStepId, "resolverStepId");
        resolverResultHash = hash(resolverResultHash, "resolverResultHash");
        intentEvidenceBundleId = text(intentEvidenceBundleId, "intentEvidenceBundleId");
        targetId = text(targetId, "targetId");
        if (!"chapter".equals(targetType) || !"chapter".equals(scopeKind)) {
            throw invalid("自然选择只能绑定当前章目标与范围");
        }
    }

    public static WorkflowIntentSelection fromStored(Map<String, Object> input, String inputHash) {
        if (input == null || !input.keySet().equals(FIELDS) || !SCHEMA.equals(input.get("schema"))) {
            throw invalid("intent_selection 输入字段或 schema 无效");
        }
        if (!ExecutionCanonicalJson.sha256(input).equals(hash(inputHash, "inputHash"))) {
            throw invalid("intent_selection inputHash 与完整输入不一致");
        }
        return new WorkflowIntentSelection(
                text(input.get("runId"), "runId"), text(input.get("operationKey"), "operationKey"),
                text(input.get("operationPlanSha256"), "operationPlanSha256"),
                text(input.get("resolverStepId"), "resolverStepId"), text(input.get("resolverResultHash"), "resolverResultHash"),
                text(input.get("intentEvidenceBundleId"), "intentEvidenceBundleId"), text(input.get("targetType"), "targetType"),
                text(input.get("targetId"), "targetId"), text(input.get("scopeKind"), "scopeKind"));
    }

    public Map<String, Object> stored() {
        Map<String, Object> input = new LinkedHashMap<>();
        input.put("schema", SCHEMA);
        input.put("runId", runId);
        input.put("operationKey", operationKey);
        input.put("operationPlanSha256", operationPlanSha256);
        input.put("resolverStepId", resolverStepId);
        input.put("resolverResultHash", resolverResultHash);
        input.put("intentEvidenceBundleId", intentEvidenceBundleId);
        input.put("targetType", targetType);
        input.put("targetId", targetId);
        input.put("scopeKind", scopeKind);
        return Map.copyOf(input);
    }

    public String inputHash() { return ExecutionCanonicalJson.sha256(stored()); }

    private static String text(Object value, String label) {
        if (!(value instanceof String text) || text.isBlank()) throw invalid(label + " 不能为空");
        return text;
    }

    private static String hash(String value, String label) {
        if (value == null || !value.matches("^[0-9a-f]{64}$")) throw invalid(label + " 必须为小写 SHA-256");
        return value;
    }

    private static IllegalStateException invalid(String message) { return new IllegalStateException(message); }
}

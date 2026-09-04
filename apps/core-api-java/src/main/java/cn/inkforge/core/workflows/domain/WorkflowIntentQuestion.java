package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Map;
import java.util.Set;

/** 一次解析产生的完整问题与不可变来源；Step ID 由持久化层作为决定身份分配。 */
public record WorkflowIntentQuestion(String runId, String resolverStepId, String resolverResultHash,
        String intentEvidenceBundleId, String clarificationCode, String prompt) {
    public static final String SCHEMA = "durable.intent-clarification.v1";
    private static final Set<String> FIELDS = Set.of("schema", "runId", "resolverStepId", "resolverResultHash",
            "intentEvidenceBundleId", "clarificationCode", "prompt");

    public WorkflowIntentQuestion {
        id(runId);
        id(resolverStepId);
        id(intentEvidenceBundleId);
        if (resolverResultHash == null || !resolverResultHash.matches("[0-9a-f]{64}")) throw invalid();
        new DurableIntentDecision.Clarification(clarificationCode, prompt);
    }

    public Map<String, Object> stored() {
        return Map.of("schema", SCHEMA, "runId", runId, "resolverStepId", resolverStepId,
                "resolverResultHash", resolverResultHash, "intentEvidenceBundleId", intentEvidenceBundleId,
                "clarificationCode", clarificationCode, "prompt", prompt);
    }

    public String inputHash() { return ExecutionCanonicalJson.sha256(stored()); }

    public static WorkflowIntentQuestion fromStored(Map<String, Object> input, String hash) {
        if (input == null || !input.keySet().equals(FIELDS) || !SCHEMA.equals(input.get("schema"))
                || !ExecutionCanonicalJson.sha256(input).equals(hash)) throw invalid();
        return new WorkflowIntentQuestion(text(input, "runId"), text(input, "resolverStepId"),
                text(input, "resolverResultHash"), text(input, "intentEvidenceBundleId"),
                text(input, "clarificationCode"), text(input, "prompt"));
    }

    private static String text(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String text)) throw invalid();
        return text;
    }

    private static void id(String value) {
        if (value == null || value.length() > 128 || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]*")) throw invalid();
    }

    private static IllegalArgumentException invalid() { return new IllegalArgumentException("澄清问题的完整材料或来源指纹无效"); }
}

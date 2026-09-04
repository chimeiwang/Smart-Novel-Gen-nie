package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.text.TextLength;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 已受理澄清回答的不可变输入；回执另存 output，不混入请求身份或重复保存哈希。 */
public record WorkflowIntentAnswer(String runId, String clientRequestId, int expectedRevision,
        String decisionStepId, String userMessage) {

    public static final String SCHEMA = "durable.intent-clarification-answer.v1";
    private static final Set<String> FIELDS = Set.of(
            "schema", "runId", "clientRequestId", "expectedRevision", "decisionStepId", "userMessage");

    public WorkflowIntentAnswer {
        id(runId);
        id(decisionStepId);
        if (clientRequestId == null || clientRequestId.length() < 16 || clientRequestId.length() > 128
                || clientRequestId.isBlank() || expectedRevision < 1 || expectedRevision == Integer.MAX_VALUE
                || userMessage == null || TextLength.count(userMessage) == 0) throw invalid();
    }

    public Map<String, Object> stored() {
        return Map.of("schema", SCHEMA, "runId", runId, "clientRequestId", clientRequestId,
                "expectedRevision", expectedRevision, "decisionStepId", decisionStepId, "userMessage", userMessage);
    }

    public String inputHash() { return ExecutionCanonicalJson.sha256(stored()); }

    public static WorkflowIntentAnswer fromStored(Map<String, Object> input, String inputHash) {
        if (input == null || !input.keySet().equals(FIELDS) || !SCHEMA.equals(input.get("schema"))
                || !ExecutionCanonicalJson.sha256(input).equals(inputHash)) throw invalid();
        return new WorkflowIntentAnswer(text(input, "runId"), text(input, "clientRequestId"), integer(input.get("expectedRevision")),
                text(input, "decisionStepId"), text(input, "userMessage"));
    }

    /** 回放受理当时的完整快照，不能随当前运行进度改写；完整 DTO Schema 由写入入口验证。 */
    public void requireReceipt(Map<String, Object> receipt, String resultHash) {
        if (receipt == null || !ExecutionCanonicalJson.sha256(receipt).equals(resultHash)
                || integer(receipt.get("engineVersion")) != 2 || !runId.equals(receipt.get("runId"))
                || !runId.equals(receipt.get("taskId")) || integer(receipt.get("revision")) != expectedRevision + 1
                || !"pending".equals(receipt.get("status")) || receipt.get("operation") != null
                || receipt.get("clarification") != null || receipt.get("artifact") != null || receipt.get("error") != null
                || !(receipt.get("activeSteps") instanceof List<?> steps) || steps.size() != 1
                || !(steps.getFirst() instanceof Map<?, ?> step) || !Objects.equals(receipt.get("currentStep"), step)
                || !"resolve_intent".equals(step.get("purpose")) || !"interactive".equals(step.get("lane"))
                || !"pending".equals(step.get("status")) || !(step.get("stepId") instanceof String stepId)) throw invalid();
        id(stepId);
    }

    private static String text(Map<String, Object> value, String key) {
        if (!(value.get(key) instanceof String text)) throw invalid();
        return text;
    }

    private static int integer(Object value) {
        if (!(value instanceof Integer || value instanceof Long)) throw invalid();
        long number = ((Number) value).longValue();
        if (number < Integer.MIN_VALUE || number > Integer.MAX_VALUE) throw invalid();
        return (int) number;
    }

    private static void id(String value) {
        if (value == null || value.length() > 128 || !value.matches("[A-Za-z0-9][A-Za-z0-9._:-]*")) throw invalid();
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("澄清回答的完整输入、身份或冻结回执无效");
    }
}

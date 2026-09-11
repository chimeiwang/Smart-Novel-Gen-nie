package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.platform.text.TextLength;
import java.math.BigDecimal;
import java.util.Map;
import java.util.Set;

/** Core 对模型提议的确定性裁决；不补造目标、不执行作品写入，也不自动追加模型调用。 */
public record DurableIntentDecision(
        String operationKey, BigDecimal confidence, Clarification clarification, String errorCode) {
    private static final BigDecimal MIN_CONFIDENCE = new BigDecimal("0.85");
    private static final Set<String> FIELDS = Set.of("workflow", "operation", "confidence",
            "targetType", "targetId", "scopeKind", "arguments", "clarification");

    public DurableIntentDecision {
        if ((operationKey == null ? 0 : 1) + (clarification == null ? 0 : 1) + (errorCode == null ? 0 : 1) != 1) {
            throw invalid();
        }
        confidence = confidence(confidence);
    }

    /** 将模型意图结果收敛为唯一获准操作，置信度不足时生成有界澄清问题。 */
    public static DurableIntentDecision resolve(Map<String, Object> proposed, String workflow,
            Set<String> allowedOperationKeys, int answeredClarifications, int maxClarifications) {
        protocolCode(workflow);
        if (proposed == null || !FIELDS.containsAll(proposed.keySet()) || !proposed.containsKey("confidence")
                || allowedOperationKeys == null || allowedOperationKeys.isEmpty()
                || maxClarifications != 2 || answeredClarifications < 0 || answeredClarifications > maxClarifications) {
            throw invalid();
        }
        if (proposed.get("targetType") != null || proposed.get("targetId") != null
                || proposed.get("scopeKind") != null) throw invalid();
        Object arguments = proposed.getOrDefault("arguments", Map.of());
        if (!(arguments instanceof Map<?, ?> map) || !map.isEmpty()) throw invalid();
        BigDecimal confidence = confidence(proposed.get("confidence"));
        Object rawWorkflow = proposed.get("workflow");
        Object rawOperation = proposed.get("operation");
        if ((rawWorkflow == null) != (rawOperation == null)) throw invalid();
        Object rawClarification = proposed.get("clarification");
        if ((rawWorkflow != null) == (rawClarification != null)) throw invalid();

        Clarification clarification;
        if (rawWorkflow != null) {
            String resolvedWorkflow = protocolCode(rawWorkflow);
            String operation = protocolCode(rawOperation);
            String key = resolvedWorkflow + "." + operation;
            if (!workflow.equals(resolvedWorkflow) || !allowedOperationKeys.contains(key)) throw invalid();
            if (confidence.compareTo(MIN_CONFIDENCE) >= 0) {
                return new DurableIntentDecision(key, confidence, null, null);
            }
            clarification = new Clarification("intent_low_confidence", "请明确本次希望执行的操作和目标；当前指令尚不足以确定。");
        } else {
            if (!(rawClarification instanceof Map<?, ?> value)
                    || !value.keySet().equals(Set.of("code", "prompt"))) throw invalid();
            clarification = new Clarification(protocolCode(value.get("code")), prompt(value.get("prompt")));
        }
        return answeredClarifications == maxClarifications
                ? new DurableIntentDecision(null, confidence, null, "INTENT_UNRESOLVED")
                : new DurableIntentDecision(null, confidence, clarification, null);
    }

    private static BigDecimal confidence(Object raw) {
        if (!(raw instanceof Number)) throw invalid();
        BigDecimal value;
        try {
            value = raw instanceof BigDecimal decimal ? decimal : new BigDecimal(raw.toString());
        } catch (NumberFormatException exception) {
            throw invalid();
        }
        if (value.compareTo(BigDecimal.ZERO) < 0 || value.compareTo(BigDecimal.ONE) > 0) throw invalid();
        return value;
    }

    private static String protocolCode(Object raw) {
        if (!(raw instanceof String text) || text.length() > 128 || !text.matches("[a-z][a-z0-9_.-]*")) throw invalid();
        return text;
    }

    private static String prompt(Object raw) {
        if (!(raw instanceof String text) || text.codePointCount(0, text.length()) > 2000
                || TextLength.count(text) == 0) throw invalid();
        return text;
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("意图提议不符合冻结的操作、范围或澄清契约");
    }

    public record Clarification(String code, String prompt) {
        public Clarification {
            code = protocolCode(code);
            prompt = DurableIntentDecision.prompt(prompt);
        }
    }
}

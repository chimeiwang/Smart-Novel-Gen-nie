package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class WorkflowIntentAnswerTest {

    @Test
    void 回答只冻结六字段并完整保留原文及独立回执哈希() {
        WorkflowIntentAnswer answer = answer();
        assertThat(answer.stored()).containsOnlyKeys("schema", "runId", "clientRequestId", "expectedRevision", "decisionStepId", "userMessage");
        assertThat(answer.userMessage()).isEqualTo("  请生成正文😀\r\n保留所有原文。  ");
        assertThat(WorkflowIntentAnswer.fromStored(answer.stored(), answer.inputHash())).isEqualTo(answer);
        Map<String, Object> receipt = receipt();
        answer.requireReceipt(receipt, ExecutionCanonicalJson.sha256(receipt));
        assertThatThrownBy(() -> WorkflowIntentAnswer.fromStored(answer.stored(), "b".repeat(64)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"schema", "runId", "clientRequestId", "expectedRevision", "decisionStepId", "userMessage", "extra"})
    void 字段缺失或额外字段不能成为完整回答(String field) {
        Map<String, Object> value = new LinkedHashMap<>(answer().stored());
        if ("extra".equals(field)) value.put("requestHash", "a".repeat(64));
        else value.remove(field);
        assertThatThrownBy(() -> WorkflowIntentAnswer.fromStored(value, ExecutionCanonicalJson.sha256(value)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"runId", "taskId", "revision", "status", "engineVersion", "operation", "currentStep", "activeSteps"})
    void 回执哈希自洽也不能变更回答受理的Run版本状态或解析步骤(String field) {
        Map<String, Object> value = receipt();
        value.put(field, switch (field) {
            case "engineVersion" -> 1;
            case "revision" -> 99;
            case "currentStep" -> Map.of("stepId", "other", "purpose", "resolve_intent");
            case "activeSteps" -> List.of();
            default -> "other";
        });
        assertThatThrownBy(() -> answer().requireReceipt(value, ExecutionCanonicalJson.sha256(value)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 回执必须匹配完整原文哈希而不是仅有Run身份() {
        Map<String, Object> value = receipt();
        assertThatThrownBy(() -> answer().requireReceipt(value, "b".repeat(64)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @ParameterizedTest
    @ValueSource(strings = {"\uFEFF", "\u0085", " \uFEFF\r\n\u0085\t"})
    void 全Unicode空白回答必须拒绝且不能靠BOM绕过(String whitespace) {
        assertThatThrownBy(() -> new WorkflowIntentAnswer("run-1", "clarification-answer-request-1", 4, "question-1", whitespace))
                .isInstanceOf(IllegalArgumentException.class);
    }

    private static WorkflowIntentAnswer answer() {
        return new WorkflowIntentAnswer("run-1", "clarification-answer-request-1", 4, "question-1", "  请生成正文😀\r\n保留所有原文。  ");
    }

    private static Map<String, Object> receipt() {
        Map<String, Object> step = Map.of("stepId", "resolver-2", "purpose", "resolve_intent", "lane", "interactive", "status", "pending");
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("engineVersion", 2);
        value.put("runId", "run-1");
        value.put("taskId", "run-1");
        value.put("revision", 5);
        value.put("status", "pending");
        value.put("operation", null);
        value.put("clarification", null);
        value.put("artifact", null);
        value.put("error", null);
        value.put("activeSteps", List.of(step));
        value.put("currentStep", step);
        return value;
    }
}

package cn.inkforge.core.workflows.protocol;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class WorkflowOutputValidatorTest {

    private static final ExecutionRegistry REGISTRY =
            ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);

    @Test
    void 真实意图Schema接受无资源身份且参数为空的命令() {
        var schema = REGISTRY.resolveSystemPurpose("resolve_intent").outputSchema();
        assertThatCode(() -> WorkflowOutputValidator.validate(schema, intentCommand()))
                .doesNotThrowAnyException();
    }

    @Test
    void 真实意图Schema接受完整澄清问题() {
        var schema = REGISTRY.resolveSystemPurpose("resolve_intent").outputSchema();
        Map<String, Object> clarification = intentCommand();
        clarification.put("workflow", null);
        clarification.put("operation", null);
        clarification.put("confidence", 0.3);
        clarification.put("clarification", Map.of(
                "code", "intent_ambiguous", "prompt", "请确认是讨论本章，还是生成待审核的正文草案？\n作者原文不会被截断。"));
        assertThatCode(() -> WorkflowOutputValidator.validate(schema, clarification))
                .doesNotThrowAnyException();
    }

    @ParameterizedTest
    @ValueSource(strings = {"targetType", "targetId", "scopeKind", "nonempty_arguments", "null_arguments", "extra_field"})
    void 真实意图Schema拒绝模型身份参数与额外字段(String invalidField) {
        var schema = REGISTRY.resolveSystemPurpose("resolve_intent").outputSchema();
        Map<String, Object> output = intentCommand();
        switch (invalidField) {
            case "nonempty_arguments" -> output.put("arguments", Map.of("targetWordCount", 8000));
            case "null_arguments" -> output.put("arguments", null);
            case "extra_field" -> output.put("unrequested", "额外输出");
            default -> output.put(invalidField, "模型不得填写");
        }
        assertThatThrownBy(() -> WorkflowOutputValidator.validate(schema, output))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("结构化输出不符合冻结 Schema");
    }

    @Test
    void maxProperties独立限制已声明属性数量而不是依赖未知字段规则() {
        Map<String, Object> schema = Map.of(
                "type", "object", "maxProperties", 1, "additionalProperties", false,
                "properties", Map.of("first", Map.of("type", "string"), "second", Map.of("type", "string")));
        assertThatCode(() -> WorkflowOutputValidator.validate(schema, Map.of("first", "甲")))
                .doesNotThrowAnyException();
        assertThatThrownBy(() -> WorkflowOutputValidator.validate(schema, Map.of("first", "甲", "second", "乙")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("属性数量超过上限");
    }

    @Test
    void maxProperties必须为非负整数且在非对象输入时也先验证Schema() {
        for (Object invalid : List.of(-1, 1.5, "1")) {
            Map<String, Object> schema = Map.of("maxProperties", invalid);
            assertThatThrownBy(() -> WorkflowOutputValidator.validate(schema, "普通文本"))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("maxProperties 必须为非负整数");
        }
    }

    @Test
    void 章节选区模型输出只允许replacement且拒绝系统派生字段() {
        var schema = REGISTRY.resolve("long_serial.rewrite_chapter_selection", false)
                .outputSchema();
        Map<String, Object> valid = Map.of("replacement", "雨夜重写");

        assertThatCode(() -> WorkflowOutputValidator.validate(schema, valid))
                .doesNotThrowAnyException();
        assertThatThrownBy(() -> WorkflowOutputValidator.validate(
                        schema, Map.of()))
                .hasMessageContaining("缺少字段");
        assertThatThrownBy(() -> WorkflowOutputValidator.validate(
                        schema,
                        Map.of(
                                "replacement", "正文",
                                "contentSha256", "b".repeat(64))))
                .hasMessageContaining("结构化输出不符合");
        assertThatThrownBy(() -> WorkflowOutputValidator.validate(
                        schema,
                        Map.of(
                                "replacement", "正文",
                                "reasoning", "不应持久化")))
                .hasMessageContaining("禁止持久化");
    }

    @Test
    void Reviewer条件Schema要求问题结论必须有证据化Finding() {
        var schema = REGISTRY.resolve("long_serial.rewrite_chapter_selection", false)
                .reviewerOutputSchema();
        Map<String, Object> pass = Map.of("contentVerdict", "pass", "findings", List.of());
        Map<String, Object> issueWithoutFinding =
                Map.of("contentVerdict", "issues_found", "findings", List.of());
        Map<String, Object> finding = new LinkedHashMap<>();
        finding.put("dimension", "consistency");
        finding.put("severity", "warning");
        finding.put("claim", "冲突");
        finding.put("candidateRange", null);
        finding.put("evidence", List.of());
        finding.put("suggestion", "修正");
        finding.put("confidence", 0.8);
        Map<String, Object> passWithFinding = Map.of(
                "contentVerdict",
                "pass",
                "findings",
                List.of(finding));

        assertThatCode(() -> WorkflowOutputValidator.validate(schema, pass))
                .doesNotThrowAnyException();
        assertThatThrownBy(() -> WorkflowOutputValidator.validate(schema, issueWithoutFinding))
                .hasMessageContaining("项数小于下限");
        assertThatThrownBy(() -> WorkflowOutputValidator.validate(schema, passWithFinding))
                .hasMessageContaining("项数超过上限");
    }

    private static Map<String, Object> intentCommand() {
        Map<String, Object> output = new LinkedHashMap<>();
        output.put("workflow", "long_serial");
        output.put("operation", "plan_chapter");
        output.put("targetType", null);
        output.put("targetId", null);
        output.put("scopeKind", null);
        output.put("arguments", Map.of());
        output.put("confidence", 0.95);
        output.put("clarification", null);
        return output;
    }
}

package cn.inkforge.core.workflows.protocol;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WorkflowOutputValidatorTest {

    private static final ExecutionRegistry REGISTRY =
            ExecutionRegistry.loadClasspath(ExecutionRegistry.Environment.TEST);

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
}

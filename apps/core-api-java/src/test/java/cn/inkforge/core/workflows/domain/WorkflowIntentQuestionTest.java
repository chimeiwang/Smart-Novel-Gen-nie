package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WorkflowIntentQuestionTest {
    @Test
    void 问题绑定解析来源并完整保留原文() {
        var question = new WorkflowIntentQuestion("run-1", "resolver-1", "a".repeat(64), "intent-1",
                "ambiguous_intent", "  请选择😀\r\n处理方式  ");
        assertThat(WorkflowIntentQuestion.fromStored(question.stored(), question.inputHash())).isEqualTo(question);
        assertThat(question.prompt()).isEqualTo("  请选择😀\r\n处理方式  ");
    }

    @Test
    void 问题拒绝损坏指纹额外字段与空白内容() {
        var question = new WorkflowIntentQuestion("run-1", "resolver-1", "a".repeat(64), "intent-1",
                "ambiguous_intent", "请明确操作");
        assertThatThrownBy(() -> WorkflowIntentQuestion.fromStored(question.stored(), "b".repeat(64)))
                .isInstanceOf(IllegalArgumentException.class);
        Map<String, Object> changed = new LinkedHashMap<>(question.stored());
        changed.put("operation", "write_chapter");
        assertThatThrownBy(() -> WorkflowIntentQuestion.fromStored(changed, question.inputHash()))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new WorkflowIntentQuestion("run-1", "resolver-1", "a".repeat(64), "intent-1",
                "ambiguous_intent", "\uFEFF \r\n"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class DurableIntentDecisionTest {
    private static final Set<String> ALLOWED = Set.of(
            "long_serial.answer_question", "long_serial.plan_chapter", "long_serial.write_chapter");

    @Test
    void 只有已授权高置信操作能被选择且不提供模型目标() {
        var decision = decide(command("write_chapter", new BigDecimal("0.85")), 0);
        assertThat(decision.operationKey()).isEqualTo("long_serial.write_chapter");
        assertThat(decision.clarification()).isNull();
        assertThat(decision.errorCode()).isNull();
        assertThat(decision.confidence()).isEqualByComparingTo("0.85");
    }

    @Test
    void 低置信度不是默认问答而是明确澄清() {
        var decision = decide(command("write_chapter", 0.849), 0);
        assertThat(decision.operationKey()).isNull();
        assertThat(decision.clarification().code()).isEqualTo("intent_low_confidence");
        assertThat(decision.clarification().prompt()).contains("明确");
        assertThat(decision.errorCode()).isNull();
    }

    @Test
    void 原始问题保留空格换行与Unicode且最后一次解析仍可成功() {
        String prompt = "  请说明😀\r\n是规划还是写正文？  ";
        var result = decide(clarification(prompt), 1);
        assertThat(result.clarification().prompt()).isEqualTo(prompt);
        assertThat(decide(command("plan_chapter", 1), 2).operationKey())
                .isEqualTo("long_serial.plan_chapter");
    }

    @Test
    void 两次回答后仍不确定明确终结而不追加隐式调用() {
        for (Map<String, Object> value : java.util.List.of(
                command("write_chapter", 0.2), clarification("需要什么？"))) {
            var result = decide(value, 2);
            assertThat(result.operationKey()).isNull();
            assertThat(result.clarification()).isNull();
            assertThat(result.errorCode()).isEqualTo("INTENT_UNRESOLVED");
        }
    }

    @Test
    void 不接受未授权操作或模型指定资源参数() {
        assertThatThrownBy(() -> decide(command("create_lore", 0.99), 0))
                .isInstanceOf(IllegalArgumentException.class);
        for (String field : Set.of("targetType", "targetId", "scopeKind")) {
            var value = command("write_chapter", 0.99);
            value.put(field, "chapter");
            assertThatThrownBy(() -> decide(value, 0)).isInstanceOf(IllegalArgumentException.class);
        }
        var value = command("write_chapter", 0.99);
        value.put("arguments", Map.of("userInstruction", "替换作者请求"));
        assertThatThrownBy(() -> decide(value, 0)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 拒绝混合分支错误工作流额外字段和非法置信度() {
        var mixed = command("write_chapter", 0.99);
        mixed.put("clarification", Map.of("code", "question", "prompt", "为什么？"));
        assertThatThrownBy(() -> decide(mixed, 0)).isInstanceOf(IllegalArgumentException.class);
        var wrongWorkflow = command("write_chapter", 0.99);
        wrongWorkflow.put("workflow", "video");
        assertThatThrownBy(() -> decide(wrongWorkflow, 0)).isInstanceOf(IllegalArgumentException.class);
        var unknown = command("write_chapter", 0.99);
        unknown.put("rawResponse", "不允许模型原文诊断");
        assertThatThrownBy(() -> decide(unknown, 0)).isInstanceOf(IllegalArgumentException.class);
        for (Object confidence : java.util.List.of("0.9", true, -0.01, 1.01, Double.NaN, Double.POSITIVE_INFINITY)) {
            assertThatThrownBy(() -> decide(command("write_chapter", confidence), 0))
                    .isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void 拒绝空白或超长问题及无效解析次数() {
        for (String prompt : java.util.List.of(" \r\n", "\uFEFF", "😀".repeat(2001))) {
            assertThatThrownBy(() -> decide(clarification(prompt), 0)).isInstanceOf(IllegalArgumentException.class);
        }
        for (int round : new int[] {-1, 3}) {
            assertThatThrownBy(() -> decide(command("write_chapter", 0.99), round))
                    .isInstanceOf(IllegalArgumentException.class);
        }
        var empty = new LinkedHashMap<String, Object>(Map.of("confidence", 1, "arguments", Map.of()));
        assertThatThrownBy(() -> decide(empty, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThat(decide(clarification("\u001c"), 0).clarification().prompt()).isEqualTo("\u001c");
    }

    private static DurableIntentDecision decide(Map<String, Object> value, int answers) {
        return DurableIntentDecision.resolve(value, "long_serial", ALLOWED, answers, 2);
    }

    private static Map<String, Object> command(String operation, Object confidence) {
        return new LinkedHashMap<>(Map.of("workflow", "long_serial", "operation", operation,
                "confidence", confidence, "arguments", Map.of()));
    }

    private static Map<String, Object> clarification(String prompt) {
        return new LinkedHashMap<>(Map.of("confidence", 0.5, "arguments", Map.of(),
                "clarification", Map.of("code", "ambiguous_intent", "prompt", prompt)));
    }
}

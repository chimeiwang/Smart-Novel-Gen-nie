package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShortMediumSegmentsTest {
    @ParameterizedTest
    @CsvSource({"6000,1", "15000,1", "15001,2", "80000,6"})
    void 正文段数只来自冻结目标字数(int target, int expected) {
        assertThat(ShortMediumSegments.segmentCount("generate_manuscript", context("generate_manuscript", target)))
                .isEqualTo(expected);
        assertThat(ShortMediumSegments.segmentCount("generate_outline", context("generate_outline", target))).isEqualTo(1);
    }

    @Test
    void 分段输入严格且不能改变原分段数或越界() {
        var context = context("generate_manuscript", 15001);
        assertThat(ShortMediumSegments.index("generate_manuscript", context, Map.of("segmentIndex", 1, "segmentCount", 2))).isEqualTo(1);
        for (Map<String, Object> input : List.of(
                Map.<String, Object>of("segmentIndex", 0, "segmentCount", 1),
                Map.<String, Object>of("segmentIndex", 2, "segmentCount", 2),
                Map.<String, Object>of("segmentIndex", -1, "segmentCount", 2),
                Map.<String, Object>of("segmentIndex", 0.0, "segmentCount", 2),
                Map.<String, Object>of("segmentIndex", 0, "segmentCount", 2, "extra", true))) {
            assertThatThrownBy(() -> ShortMediumSegments.index("generate_manuscript", context, input))
                    .isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void 完整段按原顺序无额外分隔符拼接并保留Unicode与空白() {
        var first = segment("step-1", 0, "  开头😀\r\n");
        var second = segment("step-2", 1, "尾部🚀\n ");
        assertThat(ShortMediumSegments.join(List.of(first, second), 2)).isEqualTo("  开头😀\r\n尾部🚀\n ");
        assertThat(ShortMediumSegments.join(List.of(), 0)).isEmpty();
        assertThatThrownBy(() -> ShortMediumSegments.join(List.of(second, first), 2)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> ShortMediumSegments.join(List.of(first), 2)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> ShortMediumSegments.join(List.of(first, segment("step-1", 1, "尾")), 2))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new ShortMediumSegments.Segment("step-3", 0, "实际正文", "0".repeat(64), "1".repeat(64)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 模型只生成语义文本且派生哈希绑定完整原文() {
        for (String operation : List.of("generate_outline", "generate_manuscript", "replace_selection", "full_check")) {
            String key = ShortMediumSegments.textKey(operation);
            String value = "  完整内容😀\r\n";
            Map<String, Object> schema = Map.of("type", "object", "additionalProperties", false,
                    "properties", Map.of(key, Map.of("type", "string", "minLength", 1)), "required", List.of(key));
            Map<String, Object> output = Map.of(key, value, key + "Sha256", ShortMediumSegments.sha256(value));
            assertThat(ShortMediumSegments.output(operation, output, schema)).isEqualTo(value);
            assertThatThrownBy(() -> ShortMediumSegments.output(operation, Map.of(key, value, key + "Sha256", "0".repeat(64)), schema))
                    .isInstanceOf(IllegalArgumentException.class);
            assertThatThrownBy(() -> ShortMediumSegments.output(operation, Map.of(key, value, key + "Sha256", ShortMediumSegments.sha256(value), "state", "completed"), schema))
                    .isInstanceOf(IllegalArgumentException.class);
        }
    }

    private static ShortMediumSegments.Segment segment(String id, int index, String content) {
        return new ShortMediumSegments.Segment(id, index, content, ShortMediumSegments.sha256(content), "1".repeat(64));
    }

    private static Map<String, Object> context(String operation, int target) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String key : Set.of("workflow", "operation", "documentType", "chapterId", "baseVersionId", "baseContent",
                "baseContentHash", "sourceOutlineVersionId", "sourceOutlineContent", "sourceOutlineContentHash",
                "selectionStart", "selectionEnd", "selectedText", "selectedTextHash", "contextBefore", "contextAfter",
                "userInstruction", "targetTotalWordCount", "sourceKind", "sourceText")) result.put(key, null);
        result.put("workflow", "short_medium");
        result.put("operation", operation);
        result.put("documentType", operation.equals("generate_outline") ? "outline" : "manuscript");
        result.put("targetTotalWordCount", target);
        return result;
    }
}

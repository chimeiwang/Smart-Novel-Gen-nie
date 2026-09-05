package cn.inkforge.core.workflows.domain;

import cn.inkforge.core.workflows.protocol.WorkflowOutputValidator;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 中短篇模型 Step 的纯分段规则；正文采用和产品校验仍由中短篇领域负责。 */
public final class ShortMediumSegments {
    public static final String MANIFEST_SCHEMA = "durable.short-medium-manifest.v1";
    public static final String MANIFEST_PURPOSE = "short_medium_manifest";
    private static final Set<String> CONTEXT_FIELDS = Set.of("workflow", "operation", "documentType", "chapterId",
            "baseVersionId", "baseContent", "baseContentHash", "sourceOutlineVersionId", "sourceOutlineContent",
            "sourceOutlineContentHash", "selectionStart", "selectionEnd", "selectedText", "selectedTextHash",
            "contextBefore", "contextAfter", "userInstruction", "targetTotalWordCount", "sourceKind", "sourceText");

    private ShortMediumSegments() {}

    public static int segmentCount(String operation, Map<String, Object> context) {
        textKey(operation);
        if (context == null || !context.keySet().equals(CONTEXT_FIELDS)
                || !"short_medium".equals(context.get("workflow")) || !operation.equals(context.get("operation"))) {
            throw invalid("冻结上下文字段或操作不一致");
        }
        if (!"generate_manuscript".equals(operation)) return 1;
        int target = integer(context.get("targetTotalWordCount"));
        if (target < 6000 || target > 80000) throw invalid("冻结目标字数不在现有范围内");
        return (target + 14999) / 15000;
    }

    public static int index(String operation, Map<String, Object> context, Map<String, Object> input) {
        if (input == null || !input.keySet().equals(Set.of("segmentIndex", "segmentCount"))) {
            throw invalid("Step 分段输入字段无效");
        }
        int count = segmentCount(operation, context);
        int index = integer(input.get("segmentIndex"));
        if (integer(input.get("segmentCount")) != count || index < 0 || index >= count) {
            throw invalid("Step 段数或序号不匹配冻结来源");
        }
        return index;
    }

    public static String textKey(String operation) {
        return switch (operation) {
            case "generate_outline", "generate_manuscript" -> "content";
            case "replace_selection" -> "replacement";
            case "full_check" -> "text";
            default -> throw invalid("不支持的操作");
        };
    }

    public static String output(String operation, Map<String, Object> output, Map<String, Object> providerSchema) {
        String key = textKey(operation);
        if (output == null || !output.keySet().equals(Set.of(key, key + "Sha256"))
                || !(output.get(key) instanceof String content) || content.isEmpty()
                || !sha256(content).equals(output.get(key + "Sha256"))) {
            throw invalid("完整文本或派生哈希无效");
        }
        WorkflowOutputValidator.validate(providerSchema, Map.of(key, content));
        return content;
    }

    public static String join(List<Segment> segments, int expectedCount) {
        if (expectedCount < 0 || expectedCount > 6 || segments.size() != expectedCount) {
            throw invalid("已完成段的数量不一致");
        }
        Set<String> ids = new HashSet<>();
        StringBuilder text = new StringBuilder();
        for (int index = 0; index < segments.size(); index++) {
            Segment segment = segments.get(index);
            if (segment.index() != index || !ids.add(segment.stepId())) throw invalid("分段重复、乱序或缺失");
            text.append(segment.content());
        }
        return text.toString();
    }

    public static int integer(Object value) {
        if (!(value instanceof Integer || value instanceof Long || value instanceof BigInteger)) {
            throw invalid("序号必须是严格整数");
        }
        try {
            return new BigInteger(value.toString()).intValueExact();
        } catch (ArithmeticException exception) {
            throw invalid("序号超出整数范围");
        }
    }

    public static String sha256(String content) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("JVM 缺少 SHA-256", exception);
        }
    }

    public record Segment(String stepId, int index, String content, String contentSha256, String resultHash) {
        public Segment {
            if (stepId == null || stepId.isBlank() || index < 0 || index > 5 || content == null || content.isEmpty()
                    || !sha256(content).equals(contentSha256) || resultHash == null || !resultHash.matches("[0-9a-f]{64}")) {
                throw invalid("已完成段的身份、文本或哈希无效");
            }
        }

        public Map<String, Object> reference() {
            return Map.of("index", index, "stepId", stepId, "contentSha256", contentSha256, "resultHash", resultHash);
        }
    }

    private static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException("中短篇耐久分段：" + message);
    }
}

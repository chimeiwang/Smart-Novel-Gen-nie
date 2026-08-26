package cn.inkforge.core.writing.domain;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.Collections;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 长篇写作 Graph 快照的共享反序列化与资源归属校验。 */
public final class WritingGraphSnapshot {

    private static final Set<String> RUNTIME_ONLY_FIELDS = Set.of(
            "runtime", "novelData", "streamCallbacks", "eventCallbacks", "controlEvents");
    private static final Set<String> OPERATIONS = Set.of(
            "answer_question",
            "create_lore",
            "revise_lore",
            "create_outline",
            "revise_outline",
            "plan_chapter",
            "write_chapter",
            "rewrite_scene",
            "rewrite_chapter_selection",
            "rewrite_outline_selection",
            "review_chapter",
            "sync_lore",
            "manage_foreshadowing");

    private WritingGraphSnapshot() {}

    public static Parsed parse(
            String serialized,
            ObjectMapper json,
            String expectedTaskId,
            String expectedUserId,
            String expectedNovelId,
            String expectedChapterId) {
        Map<String, Object> values = object(serialized, json);
        if (values.keySet().stream().anyMatch(RUNTIME_ONLY_FIELDS::contains)) {
            throw invalid("写作任务快照包含无效字段");
        }
        Map<String, String> identities = new LinkedHashMap<>();
        for (String key : List.of("taskId", "userId", "novelId", "chapterId")) {
            Object value = values.get(key);
            if (!(value instanceof String text) || text.isEmpty()) {
                throw invalid("写作任务快照缺少资源身份");
            }
            identities.put(key, text);
        }
        if (!matches(identities.get("taskId"), expectedTaskId)
                || !matches(identities.get("userId"), expectedUserId)
                || !matches(identities.get("novelId"), expectedNovelId)
                || !matches(identities.get("chapterId"), expectedChapterId)) {
            throw invalid("写作任务快照资源归属不匹配");
        }
        if (!integral(values.get("targetWordCount"))
                || !(values.get("conversationHistory") instanceof List<?>)) {
            throw invalid("写作任务快照缺少任务输入");
        }
        Map<String, Object> operation = null;
        Object rawOperation = values.get("currentOperation");
        if (rawOperation != null) {
            if (!(rawOperation instanceof Map<?, ?> map)) {
                throw invalid("写作任务快照的创作操作无效");
            }
            operation = Collections.unmodifiableMap(stringMap(map));
            if (!(operation.get("kind") instanceof String kind)
                    || !OPERATIONS.contains(kind)) {
                throw invalid("写作任务快照的创作操作无效");
            }
        }
        String stage = null;
        Object rawStage = values.get("operationStage");
        if (rawStage != null) {
            if (!(rawStage instanceof String text)) {
                throw invalid("写作任务快照的操作阶段无效");
            }
            stage = text;
        }
        String artifactId = null;
        Object rawReview = values.get("artifactReview");
        if (rawReview != null) {
            if (!(rawReview instanceof Map<?, ?> map)) {
                throw invalid("写作任务快照的草案状态无效");
            }
            Object candidate = map.get("activeArtifactId");
            if (candidate != null && !(candidate instanceof String)) {
                throw invalid("写作任务快照的草案标识无效");
            }
            artifactId = (String) candidate;
        }
        if (artifactId == null) {
            Object legacy = values.get("activeArtifactId");
            if (legacy != null && !(legacy instanceof String)) {
                throw invalid("写作任务快照的兼容草案标识无效");
            }
            artifactId = (String) legacy;
        }
        return new Parsed(
                values,
                identities.get("taskId"),
                identities.get("userId"),
                identities.get("novelId"),
                identities.get("chapterId"),
                operation,
                stage,
                artifactId);
    }

    public static int eventSequence(String serialized, ObjectMapper json) {
        Map<String, Object> values = object(serialized, json);
        Object value = values.getOrDefault("eventSequence", 0);
        if (!integral(value) || ((Number) value).longValue() < 0
                || ((Number) value).longValue() > Integer.MAX_VALUE) {
            throw invalid("持久写作快照事件序号无效");
        }
        return ((Number) value).intValue();
    }

    private static Map<String, Object> object(String serialized, ObjectMapper json) {
        if (serialized == null) throw invalid("写作任务快照不是有效 JSON");
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) {
                throw invalid("写作任务快照格式无效");
            }
            return stringMap(map);
        } catch (IllegalArgumentException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw invalid("写作任务快照不是有效 JSON");
        }
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) {
                throw invalid("写作任务快照 JSON key 无效");
            }
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static boolean integral(Object value) {
        return value instanceof Number
                && !(value instanceof Double)
                && !(value instanceof Float);
    }

    private static boolean matches(String actual, String expected) {
        return expected == null || Objects.equals(actual, expected);
    }

    private static IllegalArgumentException invalid(String message) {
        return new IllegalArgumentException(message);
    }

    public record Parsed(
            Map<String, Object> values,
            String taskId,
            String userId,
            String novelId,
            String chapterId,
            Map<String, Object> currentOperation,
            String operationStage,
            String activeArtifactId) {}
}

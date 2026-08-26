package cn.inkforge.core.writing.application;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * 写作命令持久载荷的唯一解析入口。
 *
 * <p>兼容命令直接把根对象交给 Agent；版本化命令必须是严格的
 * {@code _inkforgeCommand + job} 信封。损坏的耐久数据应阻断后台 worker，不能降级猜测。
 */
public final class WritingCommandPayload {

    private static final Set<String> ENVELOPE_FIELDS = Set.of(
            "schemaVersion",
            "clientRequestId",
            "commandKind",
            "resourceIdentity",
            "normalizedBody",
            "requestFingerprint");

    private WritingCommandPayload() {}

    public static Parsed parse(
            String persistedKind, String serialized, ObjectMapper json) {
        Objects.requireNonNull(json);
        Map<String, Object> payload = object(serialized, json);
        if (!payload.containsKey("_inkforgeCommand")) {
            if (persistedKind == null || persistedKind.isBlank()) {
                throw invalid();
            }
            return new Parsed(
                    persistedKind,
                    Collections.unmodifiableMap(payload),
                    Collections.unmodifiableMap(new LinkedHashMap<>(payload)));
        }
        if (!payload.keySet().equals(Set.of("_inkforgeCommand", "job"))
                || !(payload.get("_inkforgeCommand") instanceof Map<?, ?> rawMetadata)
                || !(payload.get("job") instanceof Map<?, ?> rawJob)) {
            throw invalid();
        }
        Map<String, Object> metadata = stringMap(rawMetadata);
        Map<String, Object> job = stringMap(rawJob);
        if (metadata == null
                || job == null
                || !metadata.keySet().equals(ENVELOPE_FIELDS)
                || !Integer.valueOf(1).equals(metadata.get("schemaVersion"))
                || !(metadata.get("clientRequestId") instanceof String requestId)
                || requestId.isEmpty()
                || requestId.length() > 128
                || !(metadata.get("commandKind") instanceof String commandKind)
                || commandKind.isBlank()
                || !(metadata.get("resourceIdentity") instanceof Map<?, ?> resource)
                || stringMap(resource) == null
                || !(metadata.get("normalizedBody") instanceof Map<?, ?> body)
                || stringMap(body) == null
                || !(metadata.get("requestFingerprint") instanceof String fingerprint)
                || !fingerprint.matches("[0-9a-f]{64}")) {
            throw invalid();
        }
        return new Parsed(
                commandKind,
                Collections.unmodifiableMap(payload),
                Collections.unmodifiableMap(job));
    }

    private static Map<String, Object> object(String serialized, ObjectMapper json) {
        if (serialized == null) throw invalid();
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) throw invalid();
            Map<String, Object> result = stringMap(map);
            if (result == null) throw invalid();
            return result;
        } catch (RuntimeException exception) {
            throw invalid();
        }
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) return null;
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static IllegalStateException invalid() {
        return new IllegalStateException("写作命令持久载荷无效");
    }

    public record Parsed(
            String logicalKind,
            Map<String, Object> payload,
            Map<String, Object> job) {}
}

package cn.inkforge.core.writing.domain;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 严格的 base64url JSON 写作运行游标，只携带创建时间与任务 ID。 */
public final class WritingRunCursor {

    private final ObjectMapper json;

    public WritingRunCursor(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    public String encode(OffsetDateTime createdAt, String taskId) {
        OffsetDateTime utc = Objects.requireNonNull(createdAt).withOffsetSameInstant(ZoneOffset.UTC);
        String payload = json.writeValueAsString(Map.of(
                "createdAt", utc.toString(),
                "id", requireId(taskId)));
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(payload.getBytes(StandardCharsets.UTF_8));
    }

    public Position decode(String value) {
        if (value == null || value.isEmpty() || value.indexOf('=') >= 0) {
            throw invalid();
        }
        try {
            byte[] raw = Base64.getUrlDecoder().decode(value);
            String canonical = Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
            if (!canonical.equals(value)) throw invalid();
            Object parsed = json.readValue(
                    new String(raw, StandardCharsets.UTF_8), new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)
                    || map.size() != 2
                    || !map.keySet().equals(java.util.Set.of("createdAt", "id"))
                    || !(map.get("createdAt") instanceof String createdAt)
                    || !(map.get("id") instanceof String id)
                    || id.isEmpty()) {
                throw invalid();
            }
            return new Position(OffsetDateTime.parse(createdAt), id);
        } catch (RuntimeException exception) {
            throw invalid();
        }
    }

    private static String requireId(String value) {
        if (value == null || value.isEmpty()) throw invalid();
        return value;
    }

    private static IllegalArgumentException invalid() {
        return new IllegalArgumentException("任务游标格式无效");
    }

    public record Position(OffsetDateTime createdAt, String taskId) {}
}

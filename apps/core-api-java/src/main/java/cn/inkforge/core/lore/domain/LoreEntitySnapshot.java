package cn.inkforge.core.lore.domain;

import java.time.OffsetDateTime;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** 设定实体的公共可观察快照。 */
public record LoreEntitySnapshot(
        LoreEntityKind kind,
        String id,
        Map<String, Object> fields,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {

    public LoreEntitySnapshot {
        Objects.requireNonNull(kind);
        Objects.requireNonNull(id);
        Objects.requireNonNull(fields);
        Objects.requireNonNull(createdAt);
        Objects.requireNonNull(updatedAt);
        fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields));
    }
}

package cn.inkforge.core.lore.domain;

import java.time.OffsetDateTime;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** ReviewArtifact 内单条设定实体命令；名称解析只用于兼容已冻结草案。 */
public record EntityMutation(
        MutationAction action,
        LoreEntityKind kind,
        Map<String, Object> fields,
        String entityId,
        String clientRequestId,
        OffsetDateTime expectedUpdatedAt,
        String lookupField,
        String lookupValue,
        String errorLabel) {

    public EntityMutation {
        Objects.requireNonNull(action);
        Objects.requireNonNull(kind);
        Objects.requireNonNull(fields);
        fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields));
        errorLabel = errorLabel == null ? "设定实体" : errorLabel;
    }
}
